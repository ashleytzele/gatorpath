"""The web app's AI helper (ARCHITECTURE §7.7, D34): Haiku picks and changes courses, and the engine decides. Web only: the
MCP server stays free of LLM calls (golden rule 4). The record stays on this side: tools run with it, so the model never
holds a name, ID, grade or GPA, and can't mistype one, which is what Haiku got wrong most in the evals (2026-11-06)."""

import json
import re

import anthropic

from gatorpath import server

MODEL = "claude-haiku-5-5"
ROUNDS = 40  # model calls for one request; filling a whole plan takes about ten
HISTORY = 12  # messages of the chat kept for the model
LONGEST = 2000  # characters of one message
PRIVATE = re.compile(r"\s*\((?:have [^)]*|(?:SF State GPA )?\d\.\d+)\)")  # engine text can quote a grade or GPA
FILL = "Fill every open slot in this plan for my goal."
SYSTEM = """You are GatorPath's planning helper on a website for SF State students. You help one student with their degree plan.

Every course, prerequisite and requirement comes from your tools: never name one they didn't return. The student's record is already held by the tools, so don't ask for it, and never guess a grade.

change_plan is the only way to change the plan. It runs GatorPath's checks and refuses a change that makes the plan worse. A refused change did not happen: try another course, or tell the student it didn't work. Never say a change happened unless change_plan applied it, and give only the reason it gave: never work out a reason yourself.

Filling a slot means replacing it, so remove and add go in the same change: {"term": "2028-spring", "remove": "ge_6", "add": "AA S 106"}. Adding a course without removing its slot counts both, and the term goes over its units. Remove a 0-unit slot once a course you chose covers it.

To fill a plan:
1. Call ge_options once. Put the courses of its first way into the plan: one course can cover several requirements, so remove the slots it covers.
2. For each other group with open slots, call list_options once, with the term of the group's first slot. Pick by the student's goal, 'ready' options first. Respect the group's minimum units in a subject.
3. A slot named "elective" takes any course of about those units that fits the goal: find one with search_courses.
4. Send the changes to change_plan together, then fix what it reports. Stop when no slots are left, or when the rest can't be filled, and say which.

To change a class: find what they want with get_course, search_courses or list_options, then use change_plan (remove the old one and add the new one in the same change). To move a class, remove it from one term and add it to another.

Reply in two to four plain sentences: what changed, and any problem or warning they should know. Don't list the whole plan: they can see it. Never say a plan is verified, approved or official. For anything the tools can't settle (whether a requirement applies, overloads, visas, exceptions), send them to an advisor: https://sfsu.campus.eab.com/ (Navigator). Only help with this student's SF State plan."""

TOOLS = [
    {"name": "ge_options", "description": "Ways to finish the open GE, SF State Studies and American Institutions requirements, "
     "fewest courses first. Each part names what one course covers, with example courses.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_options", "description": "The courses that can fill one requirement group, ranked ready-first, with "
     "readiness at that term, what else each covers, its description and when it ran.",
     "input_schema": {"type": "object", "properties": {
         "group_id": {"type": "string", "description": "The slot's name, e.g. senior_electives or ge_4ud"},
         "term": {"type": "string", "description": "The slot's term, e.g. 2028-fall"}}, "required": ["group_id", "term"]}},
    {"name": "search_courses", "description": "Keyword search over Bulletin course codes, titles and descriptions.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "subject": {"type": "string"}},
                      "required": ["query"]}},
    {"name": "get_course", "description": "One course: description, prerequisites, when it runs, what it counts for.",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "get_sections", "description": "Class Search sections of courses in one term, with a clash-free set.",
     "input_schema": {"type": "object", "properties": {"term": {"type": "string"}, "codes": {"type": "array", "items": {"type": "string"}}},
                      "required": ["term", "codes"]}},
    {"name": "change_plan", "description": "Change the plan, all changes together. Each removes a slot or course from a "
     "term, adds a course to it, or both: {\"term\": \"2028-spring\", \"remove\": \"ge_6\", \"add\": \"AA S 106\"} fills a "
     "slot. GatorPath's checks run on the result: applied is false if it refuses, and then nothing changed. Returns the "
     "errors and the slots still open.",
     "input_schema": {"type": "object", "required": ["changes"], "properties": {"changes": {"type": "array", "items": {
         "type": "object", "required": ["term"], "properties": {
             "term": {"type": "string"}, "remove": {"type": "string", "description": "A slot name or course code in that term"},
             "add": {"type": "string", "description": "A course code"}}}}}}},
]


class NotConnected(Exception):
    """The site still plans without AI: this says the helper can't answer now."""


def connect() -> anthropic.Anthropic:
    return anthropic.Anthropic(max_retries=4, timeout=120.0)


def scrub(text: str) -> str:
    return PRIVATE.sub("", text)


def open_slots(state: dict) -> list[dict]:
    return [{"term": s["term"], "slot": c["slot"], "title": state["titles"].get(c["slot"], "any course"), "units": c["units"]}
            for s in state["semesters"] for c in s["courses"] if isinstance(c, dict)]


def change_plan(state: dict, changes: list[dict]) -> dict:
    """Applies the changes to a copy, and keeps it only if the plan is no worse: check_plan decides, never the model."""
    semesters = json.loads(json.dumps(state["semesters"]))
    picks, added, problems = [dict(p) for p in state["picks"]], [], []
    for change in changes:
        term = next((s for s in semesters if s["term"] == change.get("term")), None)
        if term is None:
            problems.append(f"{change.get('term')} isn't a term in this plan")
            continue
        at, gone = len(term["courses"]), None
        if change.get("remove"):
            names = [c["slot"] if isinstance(c, dict) else c for c in term["courses"]]
            if change["remove"] not in names:
                problems.append(f"{change['remove']} isn't in {term['term']}")
                continue
            at = names.index(change["remove"])
            gone = term["courses"].pop(at)
        if change.get("add"):
            code = server.norm_code(change["add"])
            term["courses"].insert(at, code)
            group = gone["slot"] if isinstance(gone, dict) else next((p["group"] for p in picks if p["code"] == gone), None)
            if group:
                added.append({"group": group, "term": term["term"], "code": code, "covers": []})
    result = server.check_plan(state["student"], {"semesters": semesters})
    errors = [e["message"] for e in result["errors"]]
    if problems or len(errors) > len(state["errors"]):
        return {"applied": False, "problems": problems, "errors": errors, "open_slots": open_slots(state)}
    where = {c: s["term"] for s in semesters for c in s["courses"] if isinstance(c, str)}
    kept = [p | {"term": where[p["code"]]} for p in picks if p["code"] in where]
    state |= {"semesters": semesters, "errors": errors, "changed": True,
              "picks": [p for p in kept if p["code"] not in {a["code"] for a in added}] + added}
    return {"applied": True, "valid": result["valid"], "errors": errors, "open_slots": open_slots(state),
            "warnings": [w for w in result["warnings"] if "can't check" not in w][:6]}


def run_tool(state: dict, name: str, args: dict) -> dict:
    student, plan = state["student"], {"semesters": state["semesters"]}
    if name == "change_plan":
        return change_plan(state, args["changes"])
    if name == "list_options":
        return server.list_eligible_electives(student, args["group_id"], plan, args["term"])
    if name == "ge_options":
        return {k: v for k, v in server.ge_combinations(student, plan).items() if k in ("open", "ways", "warnings")}
    if name == "search_courses":
        return server.search_courses(args["query"], args.get("subject"))
    if name == "get_course":
        return server.get_course(args["code"])
    if name == "get_sections":
        return server.get_sections(args["term"], args["codes"])
    return {"error": f"no tool named {name}"}


def context(state: dict) -> str:
    """All the model is told about the student: the plan and the choices that shape it, never the record."""
    s = state["student"]
    known = {k: s[k] for k in ("program", "catalog_year", "goal", "f1", "max_units_per_term", "include_summer", "graduate_by") if k in s}
    plan = [{"term": t["term"], **({"max_units": t["max_units"]} if "max_units" in t else {}),
             "courses": [c for c in t["courses"] if isinstance(c, str)]} for t in state["semesters"]]
    return json.dumps({"student": known, "plan": plan, "open_slots": open_slots(state), "problems": state["errors"]})


def ask(student: dict, plan: dict, picks: list[dict], messages: list[dict]) -> dict:
    """One student request, or filling the plan when `messages` is empty. A failed call changes nothing."""
    start = server.check_plan(student, plan)
    state = {"student": student, "semesters": plan["semesters"], "picks": picks, "changed": False,
             "errors": [e["message"] for e in start["errors"]],
             "titles": {g["id"]: g["title"] for g in server.audit_progress(student)["groups"]}}
    recent = [m | {"content": m["content"][:LONGEST]} for m in messages[-HISTORY:]] or [{"role": "user", "content": FILL}]
    while recent[0]["role"] != "user":
        recent = recent[1:]
    history = recent[:-1] + [{"role": "user", "content": f"{context(state)}\n\n{recent[-1]['content']}"}]
    reply = "I ran out of steps before finishing. Check your plan, or ask an advisor in Navigator: https://sfsu.campus.eab.com/"
    try:
        client = connect()
        for _ in range(ROUNDS):
            r = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM, tools=TOOLS, messages=history,
                                       cache_control={"type": "ephemeral"})  # each round re-sends the whole history
            history.append({"role": "assistant", "content": r.content})
            if r.stop_reason != "tool_use":
                reply = "".join(b.text for b in r.content if b.type == "text") or "I can't help with that one. Please ask an advisor in Navigator: https://sfsu.campus.eab.com/"
                break
            results = []
            for b in (b for b in r.content if b.type == "tool_use"):
                try:
                    out, failed = run_tool(state, b.name, b.input), False
                except (KeyError, TypeError, ValueError, AttributeError) as e:
                    out, failed = {"error": f"bad arguments: {e!r}"}, True
                results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": failed,
                                "content": scrub(json.dumps(out, ensure_ascii=False, default=str))})
            history.append({"role": "user", "content": results})
    except anthropic.APIError as e:
        raise NotConnected("The AI helper didn't answer, so your plan is unchanged. Try again in a moment.") from e
    except TypeError as e:  # the SDK's "Could not resolve authentication method"
        if "authentication" not in str(e):
            raise
        raise NotConnected("The AI helper isn't connected yet (no Anthropic API key), so you can choose your courses yourself.") from e
    final = server.check_plan(student, {"semesters": state["semesters"]})
    return {"reply": reply, "changed": state["changed"], "semesters": state["semesters"], "picks": state["picks"], "check": final}
