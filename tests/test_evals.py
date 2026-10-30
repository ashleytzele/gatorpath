"""evals/run_evals.py scoring, on canned transcripts (no AI client). Needs the real catalog.db, like the scenario tests."""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "data/catalog.db").exists(), reason="catalog.db not built (git-ignored)")


@pytest.fixture(scope="module")
def ev():
    sys.path.insert(0, str(ROOT / "evals"))
    import run_evals
    return run_evals


def turn(answer, *calls):
    return {"calls": [{"tool": t, "args": a, "result": r} for t, a, r in calls], "answer": answer, "error": None}


def test_every_question_renders_and_its_facts_compute(ev):
    spec = yaml.safe_load((ROOT / "evals/questions.yaml").read_text())
    assert 30 <= len(spec["questions"]) <= 50 and len({q["id"] for q in spec["questions"]}) == len(spec["questions"])
    for q in spec["questions"]:
        profile = ev.shift(ev.load_profile(q.get("profile"))) if q.get("profile") else None
        assert q["ask"] in ev.first_message(q, profile)
        assert not q.get("goal") or q["goal"] in spec["goals"]
        for kind, arg in (q.get("expect", {}).get("mention") or {}).items():
            assert ev.fact(kind, arg, profile), (q["id"], kind)


def test_shift_puts_the_student_in_fall_2026(ev):
    p = ev.shift(ev.load_profile("p06"))  # its terms run to 2028-spring
    assert max((r["term"] for r in p["completed"]), key=ev.term_key) == "2026-spring"


def test_unknown_codes_count_unless_a_tool_or_the_question_named_them(ev):
    assert ev.hallucinated("Take CSC 653 and CSC 777 next, then CSC 210.", "CSC 210 is not in the 2026-27 Bulletin") == ["CSC 777"]
    assert ev.hallucinated("PHYS 220 meets in HSS 154.", '{"where": "HSS Building 154"}') == []  # a room, not a course
    assert ev.hallucinated("PHIL 110 meets in HUM 384.", '{"where":"Humanities Building 384"}') == []
    assert ev.hallucinated("Take HUM 384.", '{"where":"Humanities Building 118"}') == ["HUM 384"]  # not that room


def test_profile_must_match_what_the_student_said(ev):
    want = {"program": "bs-cs", "transfer_units": 60, "completed": [{"code": "CSC 101", "grade": "B", "transfer": True}]}
    assert ev.profile_diff(want, want | {"first_time": False}) == []  # transfer units already make a transfer student
    assert ev.profile_diff(want, want | {"completed": []}) == ["completed: missing [('CSC 101', 'T')], extra []"]


def test_a_plan_counts_only_if_valid_for_the_student_in_the_question(ev):
    q = {"id": "t", "profile": "scenario: new freshman, QR 1/2", "goal": "cybersecurity", "ask": "Plan it.",
         "expect": {"plan_valid": True}}
    profile = ev.shift(ev.load_profile(q["profile"]))
    plan = ev.server.build_plan(profile)
    good = ev.score(q, [turn("Here's your plan.", ("check_plan", {"profile": profile, "plan": plan}, ""))], {})
    assert good["scores"]["plan_valid"] and good["scores"]["profile_faithful"]
    # A plan built for a profile the client invented (CSC 101 already done) passes its own check_plan, not this one
    wrong = profile | {"completed": [{"code": "CSC 101", "grade": "A", "term": "2026-spring"}]}
    theirs = ev.server.build_plan(wrong)
    assert ev.server.check_plan(wrong, theirs)["valid"]
    bad = ev.score(q, [turn("Here's your plan.", ("check_plan", {"profile": wrong, "plan": theirs}, ""))], {})
    assert not bad["scores"]["plan_valid"] and not bad["scores"]["profile_faithful"]


def test_shorthand_code_lists_are_read_as_codes(ev):
    # Codex wrote "CSC 230, 256, 300GW, 317, 340, 413"; Claude "PHYS 220, 222, 230 and 232"
    assert ev.codes_in("Core: CSC 230, 256, 300GW and 340; PHYS 220/222.") == {
        "CSC 230", "CSC 256", "CSC 300GW", "CSC 340", "PHYS 220", "PHYS 222"}
    assert ev.codes_in("CSC 300GW, 120 units total") == {"CSC 300GW"}
    # left-p09 (claude): a note in parentheses inside the list
    assert ev.codes_in("Core: CSC 256, 300GW (C or better), 317, 340 (C or better), 413.") == {
        "CSC 256", "CSC 300GW", "CSC 317", "CSC 340", "CSC 413"}


def test_the_presented_plan_is_the_checked_one_the_answer_lists(ev):
    # Trial plan-p03 (claude): check 1 valid with CSC 685; check 2 took it out to test "optional" (units_short); the
    # answer kept check 1's plan
    q = {"id": "t", "profile": "scenario: new freshman, QR 1/2", "ask": "Plan it.", "expect": {"plan_valid": True}}
    profile = ev.shift(ev.load_profile(q["profile"]))
    plan = ev.server.build_plan(profile)
    codes = ev.plan_codes(plan)
    smaller = {"semesters": [s | {"courses": [c for c in s["courses"] if c != codes[-1]]} for s in plan["semesters"]]}
    answer = "Your plan: " + ", ".join(codes)
    calls = [("check_plan", {"profile": profile, "plan": plan}, ""), ("check_plan", {"profile": profile, "plan": smaller}, "")]
    assert ev.score(q, [turn(answer, *calls)], {})["scores"]["plan_valid"]


def test_a_course_level_is_not_a_course_code(ev):
    # left-p06 (claude): "Only one CSC 700-level course can count" was flagged as a made-up CSC 700
    assert ev.codes_in("Only one CSC 700-level course, any CSC 600+ or CSC 600s course, and CSC 869.") == {"CSC 869"}


def test_a_follow_up_is_scored_on_the_plan_it_checked(ev):
    # plan-part-time (claude): turn 2's summer plan had one course fewer than turn 1's, and the answer named both plans'
    # courses, so turn 1's plan "fit" the answer better
    q = {"id": "t", "profile": "scenario: part-time with a deadline", "ask": "Plan it.",
         "followup": {"ask": "With summers?", "expect": {"summer_tried": True}}}
    profile = ev.shift(ev.load_profile(q["profile"]))
    plan = ev.server.build_plan(profile)
    *rest, last = plan["semesters"]
    drop = next(c for c in reversed(last["courses"]) if isinstance(c, str))
    summer = {"semesters": rest + [{"term": last["term"][:5] + "summer", "courses": [c for c in last["courses"] if c != drop]}]}
    answer = "Plan: " + ", ".join(ev.plan_codes(plan))
    turns = [turn(answer, ("check_plan", {"profile": profile, "plan": plan}, "")),
             turn(answer, ("check_plan", {"profile": profile, "plan": summer}, ""))]
    assert ev.score(q, turns, {})["scores"]["followup.summer_tried"]


def test_on_a_tie_the_presented_plan_is_the_one_the_client_saw_pass(ev):
    # plan-p01 (claude): check 1 passed; check 2 had the same courses with free-elective units taken out (units_short)
    q = {"id": "t", "profile": "scenario: new freshman, QR 1/2", "ask": "Plan it.", "expect": {"plan_valid": True}}
    profile = ev.shift(ev.load_profile(q["profile"]))
    plan = ev.server.build_plan(profile)
    lean = {"semesters": [s | {"courses": [c for c in s["courses"] if isinstance(c, str)]} for s in plan["semesters"]]}
    calls = [("check_plan", {"profile": profile, "plan": plan}, '{"valid": true}'),
             ("check_plan", {"profile": profile, "plan": lean}, '{"valid": false}')]
    assert ev.score(q, [turn("Plan: " + ", ".join(ev.plan_codes(plan)), *calls)], {})["scores"]["plan_valid"]


def test_a_client_without_prompts_gets_the_students_words_and_must_fetch_the_steps(ev):
    # Codex CLI has no MCP prompts: its student just asks, and a good run fetches get_planning_steps, then plans
    q = {"id": "t", "profile": "p03", "prompt": True, "goal": "cybersecurity", "ask": "Plan it.", "expect": {}}
    plain = ev.first_message(q, ev.shift(ev.load_profile("p03")), paste=False)
    assert plain.endswith("Plan it.") and ev.server.plan_my_degree()[:60] not in plain
    asked_back = ev.score(q, [turn("What's your goal?", ("load_profile", {}, ""))], {}, plain, pasted=False)
    planned = ev.score(q, [turn("Your plan.", ("get_planning_steps", {}, ""), ("check_plan", {}, ""))], {}, plain, False)
    assert not asked_back["scores"]["planning_steps"] and planned["scores"]["planning_steps"]
    assert (asked_back["ux"]["planned_first"], planned["ux"]["planned_first"]) == (False, True)
    assert "planning_steps" not in ev.score(q, [turn("Your plan.")], {})["scores"]  # pasted: nothing to fetch
    table = ev.ux_table({("codex", "a"): asked_back, ("codex", "b"): planned}, ["codex"])
    assert "| Plan in the first reply (nothing asked back) | 1/2 |" in table
    assert "| Median tool calls, plan questions | 1.5 |" in table
