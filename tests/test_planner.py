"""check_plan over the eval catalog snapshot + real Bulletin prereq strings (tests/fixtures/catalog_rows.json)."""

import json
from pathlib import Path

import pytest
import yaml

from gatorpath.engine.planner import check_plan
from gatorpath.engine.prereq import parse_prereq
from gatorpath.engine.rules import load_rules

ROOT = Path(__file__).parents[1]
CATALOG = json.loads((ROOT / "evals/catalog-2026-27.json").read_text())
PREREQS = {r["code"]: {"raw_text": r["prereq_text"], **parse_prereq(r["prereq_text"])}
           for r in json.loads((ROOT / "tests/fixtures/catalog_rows.json").read_text())}
PROGRAM, UNIVERSITY = load_rules("2026-27", "bs-cs")
FRESHMAN = {"catalog_year": "2026-27", "program": "bs-cs", "qr_pathway": "1/2",
            "completed": [{"code": "CSC 101", "grade": "A", "term": "2026-fall"},
                          {"code": "MATH 226", "grade": "B", "term": "2026-fall"}]}


def check(profile, *semesters):
    plan = {"semesters": [{"term": t, "courses": list(cs)} for t, cs in semesters]}
    return check_plan(profile, plan, PROGRAM, UNIVERSITY, CATALOG, PREREQS)


def errors(result, kind=None):
    return [e for e in result["errors"] if e["error"] != "requirement_not_covered" and e["error"] != "units_short"
            and (kind is None or e["error"] == kind)]


def test_prereq_must_come_in_an_earlier_term():
    got = check(FRESHMAN, ("2027-spring", ["CSC 215", "CSC 220"]))
    [e] = errors(got)
    assert (e["error"], e["course"]) == ("prereq_not_met", "CSC 220")
    assert "CSC 215" in e["message"] and e["raw_text"].startswith("CSC 210 or CSC 215")
    assert errors(check(FRESHMAN, ("2027-spring", ["CSC 215"]), ("2027-fall", ["CSC 220"]))) == []


def test_corequisites_and_may_be_taken_concurrently():
    # PHYS 220 <-> PHYS 222 "concurrent enrollment"; CSC 230: "MATH 227 (may be taken concurrently)"
    got = check(FRESHMAN, ("2027-spring", ["CSC 215", "MATH 227", "PHYS 220", "PHYS 222"]),
                ("2027-fall", ["CSC 230"]))
    assert errors(got) == []
    got = check(FRESHMAN, ("2027-spring", ["CSC 215"]), ("2027-fall", ["CSC 230", "MATH 227"]))
    assert errors(got) == []
    [e] = errors(check(FRESHMAN, ("2027-spring", ["PHYS 222"])))
    assert e["course"] == "PHYS 222"


def test_standing_gpa_and_permission():
    early = check(FRESHMAN | {"gpa": 3.5}, ("2027-spring", ["CSC 653"]))
    [e] = errors(early)
    assert "upper standing" in e["message"] and "or instructor permission" in e["message"]
    # A GPA below the bar can't be fixed by ordering: the course needs instructor permission -> warning, not error
    low_gpa = check(FRESHMAN | {"gpa": 2.5, "transfer_units": 60}, ("2027-spring", ["CSC 415"]), ("2027-fall", ["CSC 653"]))
    assert not any(e["course"] == "CSC 653" for e in errors(low_gpa))
    assert any("CSC 653 in 2027-fall: GatorPath can't check GPA 3.0 or higher (have 2.5)" in w and "permission" in w
               for w in low_gpa["warnings"])
    transfer_only = [r | {"transfer": True} for r in FRESHMAN["completed"]]  # no SF State grades -> no GPA to fall back on
    no_gpa = check(FRESHMAN | {"transfer_units": 60, "completed": transfer_only},
                   ("2027-spring", ["CSC 415"]), ("2027-fall", ["CSC 653"]))
    assert not any(e["course"] == "CSC 653" for e in errors(no_gpa))
    assert any("CSC 653 in 2027-fall: GatorPath can't check GPA 3.0" in w for w in no_gpa["warnings"])
    # no `gpa` given, but SF State grades exist: their GPA is used, and said so
    graded = FRESHMAN | {"transfer_units": 60, "completed": FRESHMAN["completed"] + [{"code": "CSC 415", "grade": "C", "term": "2026-fall"}]}
    got = check(graded, ("2027-spring", ["CSC 653"]))
    assert errors(got) == [] and any("SF State GPA (3.0)" in w for w in got["warnings"])  # (12 + 12 + 6) / 10


def test_restricted_to_major_and_standing():
    # CSC 300GW: "Restricted to upper-division Computer Science majors and minors; GE Area 1A; CSC 210 or CSC 215"
    p = FRESHMAN | {"ge_done": ["1A"]}
    [e] = errors(check(p, ("2027-spring", ["CSC 215"]), ("2027-fall", ["CSC 300GW"])))
    assert "restricted to upper-division Computer Science" in e["message"]
    assert errors(check(p | {"transfer_units": 60}, ("2027-spring", ["CSC 215"]), ("2027-fall", ["CSC 300GW"]))) == []


def test_repeats_duplicates_cap_and_terms():
    got = check(FRESHMAN, ("2027-spring", ["CSC 101", "CSC 215"]), ("2027-fall", ["CSC 215"]))
    assert [e["error"] for e in errors(got)] == ["already_passed", "duplicate"]
    assert [e["error"] for e in errors(check(FRESHMAN, ("2027-spring", ["CSC 215", "CSC 215"])))] == ["duplicate", "duplicate"]
    retake = FRESHMAN | {"completed": FRESHMAN["completed"] + [{"code": "CSC 215", "grade": "D", "term": "2026-fall"}]}
    assert errors(check(retake, ("2027-spring", ["CSC 215"]), ("2027-fall", ["CSC 220"]))) == []
    heavy = ["CSC 215", "MATH 227", "PHYS 220", "PHYS 222", "ENG 114", "COMM 150"]  # 4+4+3+1+3+3 = 18
    assert [e["error"] for e in errors(check(FRESHMAN, ("2027-spring", heavy)))] == ["over_cap"]
    ok18 = check(FRESHMAN | {"max_units_per_term": 18}, ("2027-spring", heavy))
    assert errors(ok18) == [] and any("above the normal load of 15 (p.2390, p.2393)" in w for w in ok18["warnings"])
    bad = check(FRESHMAN, ("Fall 2027", ["CSC 215"]), ("2026-fall", ["CSC 999"]))
    assert [e["error"] for e in errors(bad)] == ["bad_term", "term_in_past", "unknown_course"]


def test_complete_plan_for_adt_transfer_is_valid():
    profile = yaml.safe_load((ROOT / "evals/profiles/p07-adt-transfer.yaml").read_text())["profile"]
    got = check(profile,
                ("2027-fall", ["CSC 648", "CSC 653", "CSC 665", {"slot": "ge_ud_sci", "units": 3}, {"slot": "ge_4ud", "units": 3}]),
                ("2028-spring", ["CSC 671", "CSC 620", {"slot": "senior_electives", "units": 3},
                                 {"slot": "elective", "units": 3}, {"slot": "elective", "units": 3}]),
                ("2028-fall", [{"slot": "elective", "units": 3}]))
    assert got["valid"], got["errors"]
    assert got["terms"][0] == {"term": "2027-fall", "units": 15, "units_before": 87}
    assert any("6 slot(s) still to fill" in w for w in got["warnings"])
    short = check(profile, ("2027-fall", ["CSC 648", "CSC 653"]))
    assert {e["group"] for e in short["errors"] if e["error"] == "requirement_not_covered"} == {"senior_electives", "ge_ud_sci", "ge_4ud"}
    assert {e["total"] for e in short["errors"] if e["error"] == "units_short"} == {"units"}


ROADMAP = yaml.safe_load((ROOT / "rules/roadmaps/2026-27/bs-cs.yaml").read_text())


def plan_for(profile):
    from gatorpath.engine.planner import build_plan
    return build_plan(profile, PROGRAM, UNIVERSITY, ROADMAP, CATALOG, PREREQS)


def eval_profile(path):
    profile = yaml.safe_load(path.read_text())["profile"]
    profile.setdefault("qr_pathway", "1/2")
    if not any("term" in r for r in profile.get("completed", [])):
        profile["start_term"] = "2027-spring"
    return profile


@pytest.mark.parametrize("path", sorted((ROOT / "evals/profiles").glob("*.yaml")), ids=lambda p: p.stem)
def test_build_plan_passes_check_plan(path):
    profile = eval_profile(path)
    got = plan_for(profile)
    recheck = check_plan(profile, {"semesters": got["semesters"]}, PROGRAM, UNIVERSITY, CATALOG, PREREQS)
    assert recheck["valid"] == got["check"]["valid"]
    if path.stem == "p05-cr-grades":
        # MATH 226 and CSC 101 passed with CR: the major doesn't accept CR, and CR courses can't be repeated (p.2392)
        assert not got["check"]["valid"] and got["est_graduation_term"] is None
        assert {e["group"] for e in got["check"]["errors"]} == {"math_physics", "core_cs"}
        assert sum("passed with CR" in w and "see an advisor" in w for w in got["warnings"]) == 2
        first = got["see_advisor"][0]
        assert first["role"] == "substitutions" and first["who"] == "CS Senior Advisor" and len(first["why"]) == 2
        return
    assert got["check"]["valid"], got["check"]["errors"]
    assert all(s["units"] <= 15 for s in got["semesters"])


def test_build_plan_qr_3_4_takes_the_math_path_first():
    freshman = {"catalog_year": "2026-27", "program": "bs-cs", "qr_pathway": "3/4", "start_term": "2027-fall"}
    got = plan_for(freshman)
    assert got["variant"] == "qr-3-4" and got["check"]["valid"], got["check"]["errors"]
    term_of = {c: n for n, s in enumerate(got["semesters"]) for c in s["courses"] if isinstance(c, str)}
    assert term_of["MATH 197"] < term_of["MATH 198"] < term_of["MATH 226"] < term_of["MATH 227"]
    assert term_of["CSC 101"] < term_of["CSC 215"] < term_of["CSC 220"] < term_of["CSC 340"] < term_of["CSC 415"]
    assert term_of["PHYS 220"] == term_of["PHYS 222"]  # corequisites together


def test_build_plan_needs_inputs_and_pace():
    assert plan_for({"catalog_year": "2026-27", "program": "bs-cs", "start_term": "2027-fall"})["needs_input"] == "qr_pathway"
    assert plan_for({"catalog_year": "2026-27", "program": "bs-cs", "qr_pathway": "1/2"})["needs_input"] == "start_term"
    profile = eval_profile(ROOT / "evals/profiles/p03-sophomore-qr34.yaml")
    normal, light = plan_for(profile), plan_for(profile | {"max_units_per_term": 12})
    assert light["check"]["valid"] and all(s["units"] <= 12 for s in light["semesters"])
    assert len(light["semesters"]) > len(normal["semesters"])


def test_build_plan_explains_itself_and_its_pace():
    profile = eval_profile(ROOT / "evals/profiles/p01-first-semester.yaml")  # QR 1/2, first semester in progress
    got = plan_for(profile)
    why = {c: w for s in got["semesters"] for c, w in s["why"].items()}
    assert "CSC 215 → CSC 220 → CSC 317 → CSC 413 → CSC 648" in why["CSC 215"] and "no slack" in why["CSC 215"]
    assert why["PHYS 222"].startswith("Corequisite of PHYS 220")
    assert "Needed before CSC 648" in why["CSC 413"]
    assert got["pace"]["min_terms_by_prereqs"] == 5 and got["pace"]["longest_chain"][-1] == "CSC 648"
    # 3 years from a fall 2026 start = spring 2029: 5 terms left, but ~104 units at 15/term need 7
    late = plan_for(profile | {"graduate_by": "2029-spring"})["pace"]
    assert late["on_time"] is False and late["terms_available"] == 5
    assert any("units at 15 per term needs 7 terms" in w for w in late["why_not"])
    # by spring 2028 even the prereq chain can't fit
    soon = plan_for(profile | {"graduate_by": "2028-spring"})["pace"]
    assert any(w.startswith("the prereq chain alone needs 5 terms") for w in soon["why_not"])
    on_time = plan_for(profile | {"graduate_by": "2030-spring"})["pace"]
    assert on_time["on_time"] is True and "why_not" not in on_time


def test_see_advisor_for_permission_and_overload():
    heavy = ["CSC 415", "MATH 227", "PHYS 220", "PHYS 222", "ENG 114", "COMM 150"]  # 3+4+3+1+3+3 = 17
    got = check(FRESHMAN | {"gpa": 2.5, "transfer_units": 60, "max_units_per_term": 18},
                ("2027-spring", heavy), ("2027-fall", ["CSC 653"]))
    advisor = next(a for a in got["see_advisor"] if a["role"] == "major_advisor")
    assert advisor["link"] == "https://cs.sfsu.edu/undergrads/advising" and "Navigator" in advisor["how_to_book"]
    assert any(w.startswith("CSC 653 in 2027-fall: GPA 3.0 or higher (have 2.5)") for w in advisor["why"])
    assert any("17 units is above the normal load of 15" in w for w in advisor["why"])
    assert any(a["role"] == "dpr" for a in got["see_advisor"])


def test_semester_unit_maximum_and_part_time_note():
    # p.2392: max 19 units fall/spring, 14 summer; more needs a cumulative SF State GPA of 3.0+ and a petition
    twenty = ["CSC 215", "MATH 227", "PHYS 220", "PHYS 222", "ENG 114", "COMM 150", "ERTH 112"]
    units = sum(CATALOG[c]["units_min"] for c in twenty)
    assert units > 19
    roomy = FRESHMAN | {"max_units_per_term": 25}
    got = check(roomy, ("2027-spring", twenty))  # SF State GPA 3.43 (A in CSC 101, B in MATH 226)
    assert not errors(got, "over_max_units") and any("Exceed Maximum Units Petition" in w for w in got["warnings"])
    low = roomy | {"completed": [{"code": "CSC 101", "grade": "C", "term": "2026-fall"}, {"code": "MATH 226", "grade": "C", "term": "2026-fall"}]}
    assert errors(check(low, ("2027-spring", twenty)), "over_max_units")
    # p.2393: "the normal academic load for undergraduates is 12 to 15 units"
    light = check(FRESHMAN, ("2027-spring", ["CSC 215", "MATH 227"]))
    assert any("8 units is below the normal 12-15 load" in w for w in light["warnings"])


def test_incomplete_blocks_a_retake():
    # p.2392: "A student cannot repeat a course that has a grade of I (Incomplete) unless the I grade has been converted"
    inc = FRESHMAN | {"completed": FRESHMAN["completed"] + [{"code": "CSC 215", "grade": "I", "term": "2026-fall"}]}
    assert [e["error"] for e in errors(check(inc, ("2027-spring", ["CSC 215"])))] == ["incomplete"]


def test_upper_division_ge_waits_for_ge_1a_1b_1c_2():
    # p.2319: upper-division GE courses "have a prerequisite of English Composition (1A), Critical Thinking (1B), Oral
    # Communication (1C), and Mathematical Concepts and Quantitative Reasoning (2)"
    senior = FRESHMAN | {"transfer_units": 60}
    early = check(senior, ("2027-spring", [{"slot": "ge_4ud", "units": 3}]))
    assert any("GE 4UD" in w and "require GE 1A, 1B, 1C and 2" in w for w in early["warnings"])
    ready = check(senior | {"ge_done": ["1A", "1B", "1C", "2"]}, ("2027-spring", [{"slot": "ge_4ud", "units": 3}]))
    assert not any("require GE 1A, 1B, 1C and 2" in w for w in ready["warnings"])
    # build_plan never puts a UD GE slot before those areas are done or slotted
    for path in sorted((ROOT / "evals/profiles").glob("*.yaml")):
        got = plan_for(eval_profile(path))
        assert not any("require GE 1A, 1B, 1C and 2" in w for w in got["warnings"]), path.stem


def test_upper_division_is_300_to_699():
    from gatorpath.engine.planner import upper_only
    groups = {g["id"]: g for g in PROGRAM["groups"] + UNIVERSITY["groups"]}
    assert upper_only(groups["senior_electives"]) and upper_only(groups["ge_4ud"]) and not upper_only(groups["ge_4"])
    assert not upper_only({"from": {"subject": "CSC", "level": "700+"}})  # graduate courses aren't upper division (p.2391)


def test_major_courses_older_than_seven_years_are_flagged():
    # p.2393: departments may require retaking a major course "taken more than seven years prior to graduation"
    old = FRESHMAN | {"completed": [{"code": "CSC 101", "grade": "A", "term": "2018-fall"}, {"code": "MATH 226", "grade": "B", "term": "2018-fall"}]}
    got = check(old, ("2027-spring", ["CSC 215"]))
    assert any(w.startswith("CSC 101, MATH 226: taken more than 7 years before graduation") for w in got["warnings"])
    assert not any("7 years" in w for w in check(FRESHMAN, ("2027-spring", ["CSC 215"]))["warnings"])
