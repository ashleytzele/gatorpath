"""The web's chat (ARCHITECTURE §7.7, D34, D35): Claude Code with this server, for students with no AI app. Haiku gets the
MCP server's tools, and the engine checks every change. Web only: the MCP server stays free of LLM calls (golden rule 4).
The record stays on this side: tools run with it, so the model never holds a name, ID, grade or GPA, and can't mistype
one, which is what Haiku got wrong most in the evals (2026-11-06)."""

import asyncio
import functools
import inspect
import json
import re

import anthropic

from gatorpath import server
from gatorpath.engine.planner import TERM, term_key
from gatorpath.engine.rules import GRADE_SYMBOLS

MODEL = "claude-haiku-5-5"
PACE = ("graduate_by", "max_units_per_term", "include_summer", "include_winter")  # what replan can change
RECORD = ("goal", "f1", "qr_pathway", "transfer_units", "first_time", "ge_certified", "adt", "prior_bachelors", "catalog_year",
          "not_on_dpr", "permissions", "overload_approved", "in_progress")  # what update_record sets as given
BACKEND_FILLS = ("profile", "plan")  # the model never holds these
# Not offered: build_plan (replan commits it), paths on the server's disk, and the steps a client without a prompt needs
NOT_HERE = ("build_plan", "save_profile", "load_profile", "import_dpr", "import_transcript", "get_planning_steps")
SHORTER = {"ge_combinations": ("open", "ways", "warnings")}  # its courses_that_fit and overlaps run to 20K characters
ROUNDS = 40  # model calls for one request; filling a whole plan takes about ten
HISTORY = 12  # messages of the chat kept for the model
LONGEST = 2000  # characters of one message
PRIVATE = re.compile(r"\s*\((?:have [^)]*|(?:SF State GPA )?\d\.\d+)\)")  # engine text can quote a grade or GPA
FILL = "Fill every open slot in this plan for my goal."
SYSTEM = """You are GatorPath, a degree-planning assistant for SF State students, on a website. The chat is how the student does everything: ask about their degree, change their plan, or correct their record. The page beside you only shows the result and updates by itself, so don't repeat the whole plan.

Every course, prerequisite and requirement comes from your tools: never name one they didn't return. Cite the Bulletin page when a tool gives one. The student's record and plan are already held by the tools, so don't ask for them, and never guess a grade. To say what's done or left use audit_progress; for what a course needs, get_prereq_chain or get_course; for another major, compare_programs.

Three tools change things, and nothing else does. Never say a change happened unless the tool applied it, and when one is refused give only the reason it gave: never work out a reason yourself.

change_plan changes classes. It runs GatorPath's checks and refuses a change that makes the plan worse.
- Filling a slot means replacing it, so remove and add go in the same change: {"term": "2028-spring", "remove": "ge_6", "add": "AA S 106"}. Adding a course without removing its slot counts both, and the term goes over its units. Remove a 0-unit slot once a course you chose covers it.
- To swap a class, remove the old one and add the new one in the same change. To move one, remove it from one term and add it to another. A later term that isn't in the plan yet is created when you add to it, and a term left empty goes away.
- If a change is refused because a term would fall under a minimum (an F-1 student needs 12 units in every fall and spring but the last), rebalance before giving up: move other classes from heavier terms into the light one, in the same call. Try this at least twice.
- The student has the last word on their own plan. If they've heard why a change was refused and still want it, call change_plan again with force: true, then say plainly that the plan now fails GatorPath's checks and that they should see an advisor. Never force a change they didn't insist on.

replan changes the pace: an earlier or different graduation date, fewer or more units a term, summers or Winter Session. It refuses a date it can't reach and leaves the plan alone: say why_not. When it applies, it rebuilds the plan and clears the courses chosen so far, so fill its open slots again and tell the student. If they only want to finish later, or want a class in a later term, don't replan: move classes with change_plan, which keeps their choices.

update_record corrects the record when the student tells you something: a grade, a course taken or not, transfer units, F-1, math placement, a requirement that doesn't apply to them. Pass only what they said, and never change the record on your own. If it changes what the plan needs, say so, and offer to replan.

Act when the student asks: never answer that nothing needs changing. If they don't name a class, choose one of their electives yourself, do it, say which, and tell them they can pick another.

To fill a plan:
1. Call ge_combinations once. Put the courses of its first way into the plan: one course can cover several requirements, so remove the slots it covers.
2. For each other group with open slots, call list_eligible_electives once, with by_term the group's first slot's term. Pick by the student's goal, 'ready' options first. Respect the group's minimum units in a subject.
3. A slot named "elective" takes any course of about those units that fits the goal: find one with search_courses.
4. Send the changes to change_plan together, then fix what it reports. Stop when no slots are left, or when the rest can't be filled, and say which.

Reply in two to four plain sentences: what you found or changed, and any problem or warning they should know. Never say a plan is verified, approved or official: GatorPath's checks aren't an advisor. For anything the tools can't settle (whether a requirement applies, overloads, visas, exceptions), send them to an advisor: https://sfsu.campus.eab.com/ (Navigator). Only help with this student's SF State degree."""

OWN_TOOLS = [
    {"name": "change_plan", "description": "Change the plan, all changes together. Each removes a slot or course from a "
     "term, adds a course to it, or both: {\"term\": \"2028-spring\", \"remove\": \"ge_6\", \"add\": \"AA S 106\"} fills a "
     "slot. GatorPath's checks run on the result: applied is false if it refuses, and then nothing changed. Returns the "
     "errors and the slots still open. force: true keeps a change that fails the checks, only when the student has heard "
     "the problem and insists.",
     "input_schema": {"type": "object", "required": ["changes"], "properties": {"force": {"type": "boolean"}, "changes": {"type": "array", "items": {
         "type": "object", "required": ["term"], "properties": {
             "term": {"type": "string"}, "remove": {"type": "string", "description": "A slot name or course code in that term"},
             "add": {"type": "string", "description": "A course code"}}}}}}},
    {"name": "replan", "description": "Rebuild the whole plan at another pace: the date to graduate by, the most units a "
     "term, summers, Winter Session. Pass only what changes. Clears the courses chosen so far and returns the open slots to "
     "fill again. A date it can't reach is refused with why_not, and nothing changes.",
     "input_schema": {"type": "object", "properties": {
         "graduate_by": {"type": "string", "description": "e.g. 2028-spring"}, "max_units_per_term": {"type": "number"},
         "include_summer": {"type": "boolean"}, "include_winter": {"type": "boolean"}}}},
    {"name": "update_record", "description": "Correct the student's record with what they just told you. Pass only what "
     "they said. grades sets a course's grade, or adds a completed course; drop takes a course off the record; not_on_dpr "
     "lists requirements (group ids from audit_progress) that don't apply to them, and passing it replaces the list.",
     "input_schema": {"type": "object", "properties": {
         "grades": {"type": "array", "items": {"type": "object", "required": ["code", "grade"], "properties": {
             "code": {"type": "string"}, "grade": {"type": "string"}, "term": {"type": "string", "description": "e.g. 2025-fall"}}}},
         "drop": {"type": "array", "items": {"type": "string"}}, "in_progress": {"type": "array", "items": {"type": "string"}},
         "goal": {"type": "string"}, "f1": {"type": "boolean"}, "qr_pathway": {"type": "string", "description": "1/2 or 3/4"},
         "transfer_units": {"type": "number"}, "first_time": {"type": "boolean"}, "ge_certified": {"type": "boolean"},
         "adt": {"type": "boolean"}, "prior_bachelors": {"type": "boolean"}, "catalog_year": {"type": "string"},
         "not_on_dpr": {"type": "array", "items": {"type": "string"}}, "permissions": {"type": "array", "items": {"type": "string"}},
         "overload_approved": {"type": "array", "items": {"type": "string"}}}}},
]


@functools.cache
def tools() -> list[dict]:
    """The MCP server's tools, the same as Claude Code gets, with what the backend fills in taken out, and the web's own."""
    def web(tool) -> dict:
        schema = {k: v for k, v in tool.input_schema.items() if k != "$defs"}
        schema["properties"] = {k: v for k, v in schema.get("properties", {}).items() if k not in BACKEND_FILLS}
        schema["required"] = [k for k in schema.get("required", []) if k not in BACKEND_FILLS]
        return {"name": tool.name, "description": tool.description, "input_schema": schema}
    return [web(t) for t in asyncio.run(server.mcp.list_tools()) if t.name not in NOT_HERE] + OWN_TOOLS


class NotConnected(Exception):
    """The site still plans without AI: this says the helper can't answer now."""


def connect() -> anthropic.Anthropic:
    return anthropic.Anthropic(max_retries=4, timeout=120.0)


def scrub(text: str) -> str:
    return PRIVATE.sub("", text)


def open_slots(state: dict) -> list[dict]:
    return [{"term": s["term"], "slot": c["slot"], "title": state["titles"].get(c["slot"], "any course"), "units": c["units"]}
            for s in state["semesters"] for c in s["courses"] if isinstance(c, dict)]


def later_term(term: object, semesters: list[dict]) -> bool:
    return bool(TERM.fullmatch(str(term))) and term_key(str(term)) > term_key(semesters[0]["term"])


def replan(state: dict, change: dict) -> dict:
    """build_plan at another pace, so the engine says what's reachable. It's a new plan: nothing chosen carries over."""
    options = {k: change[k] for k in PACE if k in change}
    student = state["student"] | options
    plan = server.build_plan(student)
    if "semesters" not in plan:
        return {"applied": False, "needs_input": plan.get("needs_input"), "warnings": plan.get("warnings", [])}
    if plan["pace"].get("on_time") is False:  # checked here, not left to the model: a date out of reach costs no choices
        return {"applied": False, "why_not": plan["pace"].get("why_not"), "note": "Refused: the plan is as it was"}
    state |= {"student": student, "semesters": plan["semesters"], "picks": [], "changed": True, "rebuilt": plan,
              "options": state["options"] | options, "errors": [e["message"] for e in plan["check"]["errors"]]}
    pace = plan["pace"]
    return {"applied": True, "est_graduation_term": plan["est_graduation_term"], "terms": len(plan["semesters"]),
            "errors": state["errors"], "open_slots": open_slots(state),
            "note": "This is a new plan: the courses chosen before are gone, so fill the open slots again"}


def update_record(state: dict, args: dict) -> dict:
    """What the student just said about their record. The plan isn't rebuilt: the checks run on it and report what moved."""
    changed = {k: args[k] for k in RECORD if k in args}
    grades = args.get("grades") or []
    if bad := [g["grade"] for g in grades if str(g["grade"]).upper() not in GRADE_SYMBOLS]:
        return {"applied": False, "problems": [f"{', '.join(map(str, bad))} isn't an SF State grade"]}
    if grades or args.get("drop"):
        rows = [r for r in state["student"].get("completed", []) if r["code"] not in map(server.norm_code, args.get("drop") or [])]
        for g in grades:
            code, grade = server.norm_code(g["code"]), g["grade"].upper()
            if any(r["code"] == code for r in rows):
                rows = [r | {"grade": grade} if r["code"] == code else r for r in rows]
            else:
                rows.append({"code": code, "grade": grade} | ({"term": g["term"]} if g.get("term") else {}))
        changed["completed"] = rows
    if not changed:
        return {"applied": False, "problems": ["nothing to change"]}
    student = state["student"] | changed
    result = server.check_plan(student, {"semesters": state["semesters"]})
    errors = [e["message"] for e in result["errors"]]
    state |= {"student": student, "changed": True, "options": state["options"] | changed, "errors": errors}
    return {"applied": True, "valid": result["valid"], "errors": errors}


def change_plan(state: dict, changes: list[dict], force: bool = False) -> dict:
    """Applies the changes to a copy, and keeps it only if the plan is no worse, unless the student insisted (force): then
    it stays, with its errors on the page. check_plan's verdict is never hidden. A change that makes no sense never lands."""
    semesters = json.loads(json.dumps(state["semesters"]))
    picks, added, problems = [dict(p) for p in state["picks"]], [], []
    for change in changes:
        term = next((s for s in semesters if s["term"] == change.get("term")), None)
        if term is None and change.get("add") and not change.get("remove") and later_term(change.get("term"), semesters):
            term = {"term": change["term"], "courses": []}
            semesters = sorted([*semesters, term], key=lambda s: term_key(s["term"]))
        if term is None:
            problems.append(f"{change.get('term')} isn't a term in this plan or a later one")
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
    semesters = [s for s in semesters if s["courses"]]
    result = server.check_plan(state["student"], {"semesters": semesters})
    errors = [e["message"] for e in result["errors"]]
    if problems or (len(errors) > len(state["errors"]) and not force):
        return {"applied": False, "problems": problems, "errors": errors, "open_slots": open_slots(state)}
    where = {c: s["term"] for s in semesters for c in s["courses"] if isinstance(c, str)}
    kept = [p | {"term": where[p["code"]]} for p in picks if p["code"] in where]
    state |= {"semesters": semesters, "errors": errors, "changed": True,
              "picks": [p for p in kept if p["code"] not in {a["code"] for a in added}] + added}
    return {"applied": True, "valid": result["valid"], "errors": errors, "open_slots": open_slots(state),
            "warnings": [w for w in result["warnings"] if "can't check" not in w][:6]}


def hide(out):
    """A GPA is the student's: audit totals carry them, and the model doesn't need one."""
    if isinstance(out, dict):
        return {k: hide(v) for k, v in out.items() if "gpa" not in k.lower()}
    return [hide(v) for v in out] if isinstance(out, list) else out


def run_tool(state: dict, name: str, args: dict) -> dict:
    if name == "change_plan":
        return change_plan(state, args["changes"], bool(args.get("force")))
    if name == "replan":
        return replan(state, args)
    if name == "update_record":
        return update_record(state, args)
    if name not in {t["name"] for t in tools()}:
        return {"error": f"no tool named {name}"}
    tool = getattr(server, name)
    held = {"profile": state["student"], "plan": {"semesters": state["semesters"]}}
    out = tool(**args, **{k: v for k, v in held.items() if k in inspect.signature(tool).parameters})
    return hide({k: v for k, v in out.items() if k in SHORTER[name]} if name in SHORTER else out)


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
    state = {"student": student, "semesters": plan["semesters"], "picks": picks, "changed": False, "rebuilt": None, "options": {},
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
            r = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM, tools=tools(), messages=history,
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
    final = server.check_plan(state["student"], {"semesters": state["semesters"]})
    return {"reply": reply, "changed": state["changed"], "semesters": state["semesters"], "picks": state["picks"], "check": final,
            "rebuilt": state["rebuilt"], "options": state["options"]}
