"""The web's AI helper with a scripted model: the loop, the tools and the engine are real, only the replies are canned."""

import json
import sys
import types

import pytest
from fastapi.testclient import TestClient
from test_server import SCENARIOS, fixture_db, use_fixture_db  # noqa: F401  (the fixtures apply here too)

from gatorpath import api, assistant, server

STUDENT = SCENARIOS["sophomore"] | {"gpa": 3.123, "goal": "Cybersecurity"}
block = lambda **k: types.SimpleNamespace(**k)
usage = block(input_tokens=1, output_tokens=1)


def plan_of(student=STUDENT) -> dict:
    return {"semesters": server.build_plan(student)["semesters"]}


def slot_in(plan: dict, group: str = "senior_electives") -> tuple[str, str]:
    return next((s["term"], c["slot"]) for s in plan["semesters"] for c in s["courses"]
                if isinstance(c, dict) and c["slot"] == group)


def say(text: str):
    return block(stop_reason="end_turn", usage=usage, content=[block(type="text", text=text)])


def use(name: str, **args):
    return block(stop_reason="tool_use", usage=usage, content=[block(type="tool_use", id=name, name=name, input=args)])


@pytest.fixture
def model(monkeypatch):
    """Scripts the replies and keeps what the model was sent."""
    seen = []

    def script(*replies):
        queue = list(replies)

        def create(**k):
            seen.append(k | {"messages": list(k["messages"])})
            return queue.pop(0)

        monkeypatch.setattr(assistant, "connect", lambda: block(messages=block(create=create)))
        return seen

    return script


def result_of(seen: list, turn: int) -> dict:
    return json.loads(seen[turn]["messages"][-1]["content"][0]["content"])


def test_a_good_change_lands_and_a_worse_one_is_refused(model):
    plan = plan_of()
    term, slot = slot_in(plan)
    required = next(c for c in plan["semesters"][0]["courses"] if isinstance(c, str))
    first = plan["semesters"][0]["term"]
    seen = model(use("change_plan", changes=[{"term": term, "remove": slot, "add": "CSC 652"}]),
                 use("change_plan", changes=[{"term": first, "remove": required}]),
                 say("CSC 652 is in."))
    got = assistant.ask(STUDENT, plan, [], [{"role": "user", "content": "Add CSC 652"}])
    assert result_of(seen, 1)["applied"] is True
    assert result_of(seen, 2)["applied"] is False and result_of(seen, 2)["errors"]  # dropping a required course
    assert got["changed"] and got["reply"] == "CSC 652 is in."
    terms = {s["term"]: s["courses"] for s in got["semesters"]}
    assert "CSC 652" in terms[term] and required in terms[first]
    assert got["picks"] == [{"group": slot, "term": term, "code": "CSC 652", "covers": []}]
    assert "CSC 652" in got["check"]["courses"]


def test_a_refused_request_leaves_the_plan_exactly_as_it_was(model):
    plan = plan_of()
    model(use("change_plan", changes=[{"term": "1999-fall", "add": "CSC 652"}]), say("I couldn't."))
    got = assistant.ask(STUDENT, plan, [], [{"role": "user", "content": "Add CSC 652"}])
    assert not got["changed"] and got["semesters"] == plan["semesters"] and got["picks"] == []


def test_swapping_a_pick_keeps_its_requirement(model):
    plan = plan_of()
    term, slot = slot_in(plan)
    model(use("change_plan", changes=[{"term": term, "remove": slot, "add": "CSC 652"}]), say("Done."))
    first = assistant.ask(STUDENT, plan, [], [{"role": "user", "content": "Add CSC 652"}])
    model(use("change_plan", changes=[{"term": term, "remove": "CSC 652", "add": "CSC 645"}]), say("Swapped."))
    got = assistant.ask(STUDENT, {"semesters": first["semesters"]}, first["picks"], [{"role": "user", "content": "Use CSC 645"}])
    assert [(p["group"], p["code"]) for p in got["picks"]] == [(slot, "CSC 645")]


def state_of(student=STUDENT) -> dict:
    plan = plan_of(student)
    return {"student": student, "semesters": plan["semesters"], "picks": [], "changed": False, "errors": [], "titles": {},
            "rebuilt": None, "options": {}, "sections": {}}


def test_a_class_can_move_into_a_term_the_plan_doesnt_have_yet():
    """"I still want a class in spring": the term is made, and a term left empty goes, so the end date moves with it."""
    state = state_of()
    last = state["semesters"][-1]
    year, season = last["term"].split("-")
    later = f"{int(year) + 1}-fall" if season == "fall" else f"{year}-fall"
    slot = next(c["slot"] for c in last["courses"] if isinstance(c, dict))
    got = assistant.change_plan(state, [{"term": last["term"], "remove": slot}, {"term": later, "add": "CSC 652"}])
    assert got["applied"] and state["semesters"][-1]["term"] == later and state["semesters"][-1]["courses"] == ["CSC 652"]
    terms = [s["term"] for s in state["semesters"]]
    assert terms == sorted(terms, key=assistant.term_key)

    moved = [{"term": later, "remove": "CSC 652"}, {"term": last["term"], "add": "CSC 652"}]
    assert assistant.change_plan(state, moved)["applied"] and state["semesters"][-1]["term"] == last["term"]


def test_a_class_chosen_for_being_online_is_remembered():
    state = state_of()
    term, slot = slot_in({"semesters": state["semesters"]})
    assert assistant.change_plan(state, [{"term": term, "remove": slot, "add": "CSC 652", "online": True}])["applied"]
    assert state["picks"] == [{"group": slot, "term": term, "code": "CSC 652", "covers": [], "online": True}]


def test_the_chat_can_choose_a_section_and_the_rest_fit_around_it(monkeypatch):
    """"Put me in the Tuesday section": the Schedule shows what the chat chose, or nothing changes when it can't fit."""
    state = state_of()
    first = state["semesters"][0]
    a, b = [c for c in first["courses"] if isinstance(c, str)][:2]
    row = lambda nbr, days: {"section": f"0{nbr}", "component": "LEC", "mode": "In-Person", "class_nbr": nbr,
                             "seats_open": 9, "meetings": [{"days": days, "time": "9:00 AM - 10:15 AM"}]}
    monkeypatch.setattr(server.db, "sections", lambda db, term, codes: (
        {a: [row("1", "Mo We"), row("2", "Tu Th")], b: [row("3", "Mo We")]}, {c.rsplit(" ", 1)[0]: "2026-10-26" for c in (a, b)}))
    refused = assistant.run_tool(state, "choose_section", {"term": first["term"], "class_nbr": "1"})
    assert refused["applied"] is False and refused["always_clash"] and state["sections"] == {} and not state["changed"]
    assert assistant.run_tool(state, "choose_section", {"term": first["term"], "class_nbr": "9"})["applied"] is False
    got = assistant.run_tool(state, "choose_section", {"term": first["term"], "class_nbr": "2"})
    assert got["applied"] and got["schedule"] == {a: ["2"], b: ["3"]} and state["sections"] == {first["term"]: ["2"]}


def test_a_slot_another_course_covers_keeps_its_units_as_an_elective():
    """A course that covers two GE areas frees a slot, but its units still count toward 120 and toward minimums like
    CSC 300GW's 59 units before it: a new student's whole AI fill was refused for that (2026-11-07)."""
    state = state_of()
    term, slot = next((s["term"], c) for s in state["semesters"] for c in s["courses"]
                      if isinstance(c, dict) and c["units"] and c["slot"].startswith("ge_"))
    units = lambda: sum(c["units"] for s in state["semesters"] if s["term"] == term for c in s["courses"] if isinstance(c, dict))
    before = units()
    # (forced: here no course covers the area, so the checks would refuse it)
    assert assistant.change_plan(state, [{"term": term, "remove": slot["slot"]}], force=True)["applied"]
    after = next(s for s in state["semesters"] if s["term"] == term)["courses"]
    assert slot not in after and {"slot": "elective", "units": slot["units"]} in [
        {k: c[k] for k in ("slot", "units")} for c in after if isinstance(c, dict)] and units() == before
    zero = next((s["term"], c["slot"]) for s in state["semesters"] for c in s["courses"] if isinstance(c, dict) and not c["units"])
    assert assistant.change_plan(state, [{"term": zero[0], "remove": zero[1]}], force=True)["applied"]  # 0 units: just gone
    assert all(c.get("slot") != "elective" or c["units"] for s in state["semesters"] for c in s["courses"] if isinstance(c, dict))


def test_a_new_term_has_to_be_a_real_later_term():
    state = state_of()
    for term in ("whenever", "1999-fall"):
        got = assistant.change_plan(state, [{"term": term, "add": "CSC 652"}])
        assert got["applied"] is False and got["problems"]
    assert assistant.change_plan(state, [{"term": "2099-fall", "remove": "CSC 652"}])["applied"] is False  # nothing to add


def test_replan_changes_the_pace_and_the_page_gets_it(model):
    client = TestClient(api.app)
    plan = plan_of()
    seen = model(use("replan", max_units_per_term=12, nonsense=True), say("Rebuilt."))
    got = client.post("/api/assist", json={"profile": STUDENT, "plan": plan, "messages": [{"role": "user", "content": "12 units"}]}).json()
    told = result_of(seen, 1)
    assert told["open_slots"] and told["est_graduation_term"] and "note" in told
    assert got["options"] == {"max_units_per_term": 12} and got["changed"] and got["rebuilt"]["pace"]["load"] == "max_units_per_term"
    assert len(got["semesters"]) > len(plan["semesters"]) and got["picks"] == []
    assert "nonsense" not in got["options"]


def test_replan_says_when_a_date_cant_be_reached(model):
    seen = model(use("replan", graduate_by="2027-fall"), say("Not reachable."))
    plan = plan_of()
    got = assistant.ask(STUDENT, plan, [], [{"role": "user", "content": "Finish next fall"}])
    told = result_of(seen, 1)
    assert told["applied"] is False and told["why_not"]
    assert not got["changed"] and got["semesters"] == plan["semesters"] and got["options"] == {}  # a date out of reach changes nothing


def tool_named(name: str) -> dict:
    return next(t for t in assistant.tools() if t["name"] == name)


def test_the_chat_has_the_mcp_servers_tools_with_the_record_kept_out_of_them():
    names = {t["name"] for t in assistant.tools()}
    assert {"audit_progress", "get_prereq_chain", "compare_programs", "get_roadmap", "check_plan", "search_courses",
            "list_eligible_electives", "ge_combinations", "get_sections", "change_plan", "replan", "update_record"} <= names
    assert not names & {"save_profile", "load_profile", "import_dpr", "import_transcript"}  # paths on the server's disk
    for tool in assistant.tools():
        assert not {"profile", "plan"} & set(tool["input_schema"].get("properties", {})), tool["name"]
        assert "$defs" not in tool["input_schema"]


def test_a_tool_runs_with_the_record_and_never_shows_a_gpa():
    state = state_of()
    audit = assistant.run_tool(state, "audit_progress", {})
    assert audit["groups"] and "3.123" not in json.dumps(audit) and "gpa" not in json.dumps(audit["totals"])
    assert assistant.run_tool(state, "check_plan", {})["valid"] is True
    assert assistant.run_tool(state, "compare_programs", {"target": "bs-applied-math"})["target"]
    assert "ways" in assistant.run_tool(state, "ge_combinations", {})
    assert "error" in assistant.run_tool(state, "save_profile", {"path": "/tmp/x"})  # a tool that isn't offered doesn't run


def test_the_student_can_correct_their_record_from_the_chat(model):
    client = TestClient(api.app)
    code = STUDENT["completed"][0]["code"]
    seen = model(use("update_record", grades=[{"code": code, "grade": "F"}, {"code": "CSC 215", "grade": "A"}],
                     transfer_units=12, goal="Data Science", not_on_dpr=["ge_6"]), say("Updated."))
    got = client.post("/api/assist", json={"profile": STUDENT, "plan": plan_of(), "messages": [{"role": "user", "content": "My grade was wrong"}]}).json()
    assert result_of(seen, 1)["applied"] is True and got["changed"]
    rows = {r["code"]: r["grade"] for r in got["options"]["completed"]}
    assert rows[code] == "F" and rows["CSC 215"] == "A"
    assert got["options"]["transfer_units"] == 12 and got["options"]["goal"] == "Data Science" and got["options"]["not_on_dpr"] == ["ge_6"]


def test_a_record_change_checks_what_it_is_given():
    state = state_of()
    assert assistant.update_record(state, {"grades": [{"code": "CSC 101", "grade": "great"}]})["applied"] is False
    assert assistant.update_record(state, {})["applied"] is False
    gone = STUDENT["completed"][0]["code"]
    assert assistant.update_record(state, {"drop": [gone]})["applied"] is True
    assert gone not in {r["code"] for r in state["student"]["completed"]}


def test_the_student_can_insist_and_the_plan_still_says_it_has_a_problem():
    state = state_of()
    first = state["semesters"][0]
    required = next(c for c in first["courses"] if isinstance(c, str))
    change = [{"term": first["term"], "remove": required}]
    assert assistant.change_plan(state, change)["applied"] is False
    got = assistant.change_plan(state, change, force=True)
    assert got["applied"] is True and got["valid"] is False and got["errors"]
    assert required not in state["semesters"][0]["courses"] and state["errors"]
    bad = assistant.change_plan(state, [{"term": "someday", "add": "CSC 652"}], force=True)
    assert bad["applied"] is False  # force skips the plan's checks, not sense


def test_the_model_never_gets_the_record(model):
    """Name, ID, grades and GPA stay here: the tools run with them, and their text is scrubbed."""
    seen = model(say("Hello."))
    assistant.ask(STUDENT | {"name": "Zzfake"}, plan_of(), [], [{"role": "user", "content": "Hi"}])
    sent = json.dumps(seen[0]["messages"]) + json.dumps(seen[0]["system"])
    assert "Zzfake" not in sent and "3.123" not in sent and '"grade"' not in sent and '"completed"' not in sent
    assert assistant.scrub("MATH 226 with C or better (have C-)") == "MATH 226 with C or better"
    assert "3.2" not in assistant.scrub("over the limit (SF State GPA 3.215); checked with your SF State GPA (3.2)")


def test_the_model_knows_what_each_chosen_class_is_for():
    state = state_of() | {"picks": [{"group": "ge_6", "term": "2028-spring", "code": "AIS 160", "covers": []}],
                          "titles": {"ge_6": "GE 6 Ethnic Studies"}}
    assert {"code": "AIS 160", "term": "2028-spring", "for": "GE 6 Ethnic Studies"} in json.loads(assistant.context(state))["chosen"]


def test_a_filled_plan_starts_from_the_fill_instruction_and_history_stays_short(model):
    seen = model(say("Filled."))
    assistant.ask(STUDENT, plan_of(), [], [])
    assert assistant.FILL in seen[0]["messages"][-1]["content"]
    seen = model(say("Sure."))
    many = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"line {i}" * 900} for i in range(41)]
    assistant.ask(STUDENT, plan_of(), [], many)
    assert len(seen[-1]["messages"]) <= assistant.HISTORY and len(seen[-1]["messages"][0]["content"]) <= assistant.LONGEST
    assert seen[-1]["messages"][0]["role"] == "user"


def test_the_dpr_notes_reach_the_chat_once(model):
    """What the DPR import found (a GE area left out, transfer grades recorded at the minimum) is said in the chat's
    first reply: Review no longer shows it. Later replies don't repeat it."""
    notes = ["Not found on this DPR: GE F Ethnic Studies. Left out of the plan", "Met by transfer credit: MATH 226"]
    seen = model(say("From your DPR: ..."))
    assistant.ask(STUDENT, plan_of(), [], [], notes=notes)
    sent = seen[0]["messages"][-1]["content"]
    assert json.loads(sent.split("\n\n")[0])["dpr_notes"] == notes and "dpr_notes" in seen[0]["system"]
    seen = model(say("Sure."))
    assistant.ask(STUDENT, plan_of(), [], [{"role": "user", "content": "Hi"}])
    assert "dpr_notes" not in seen[-1]["messages"][-1]["content"]


def test_the_model_cant_run_forever_or_crash_on_bad_input(model):
    seen = model(*[use("get_course") for _ in range(assistant.ROUNDS)])
    got = assistant.ask(STUDENT, plan_of(), [], [{"role": "user", "content": "Go"}])
    assert "advisor" in got["reply"].lower() and len(seen) == assistant.ROUNDS
    assert "error" in result_of(seen, 1)  # a missing argument goes back to the model as an error


def test_the_route_returns_the_change_and_says_when_ai_isnt_connected(model, monkeypatch):
    client = TestClient(api.app)
    plan = plan_of()
    model(say("Hello."))
    got = client.post("/api/assist", json={"profile": STUDENT, "plan": plan, "messages": [{"role": "user", "content": "Hi"}],
                                           "sections": {"2027-spring": ["5331"]}})
    assert got.status_code == 200 and got.json()["reply"] == "Hello."
    assert got.json()["sections"] == {"2027-spring": ["5331"]}  # the Schedule's choices come back as they went

    def nothing():
        raise assistant.NotConnected("not connected")

    monkeypatch.setattr(assistant, "connect", nothing)
    assert client.post("/api/assist", json={"profile": STUDENT, "plan": plan}).status_code == 503


def test_no_key_at_all_reads_as_not_connected(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    fake = types.SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(TypeError("Could not resolve authentication method")))
    monkeypatch.setattr(assistant.anthropic, "Anthropic", lambda **_: types.SimpleNamespace(messages=fake))
    with pytest.raises(assistant.NotConnected):
        assistant.ask(STUDENT, plan_of(), [], [])


def test_the_mcp_server_never_imports_the_ai():
    """Golden rule 4: the helper is the web's. A fresh interpreter, so another test's import can't hide it."""
    import subprocess

    code = "import sys, gatorpath.server; print('anthropic' in sys.modules or 'gatorpath.assistant' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip() == "False"
