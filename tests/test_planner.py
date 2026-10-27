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



def test_an_itep_student_takes_credential_courses_by_permission():
    # BA Early Childhood Studies: Special Education ITEP (p.612) "blends a bachelor's degree … with an Education
    # Specialist … preliminary credential": its SPED 7xx courses are "Graduate standing or permission of the instructor"
    # and "Restricted to graduate and education credential students". An ITEP undergraduate takes them by permission
    # (D27): planned, flagged for an advisor. Any other program still can't plan them
    from gatorpath.engine.planner import NO, UNVERIFIED, evaluate
    itep = {"title": "Bachelor of Arts in Early Childhood Studies: Concentration in Special Education Integrated Teacher "
                     "Education Program", "global": {"itep": True, "source": "p.612"}}
    ctx = {"done": set(), "same_term": set(), "grades": {}, "units": 90, "profile": {}, "gpa": None, "ge_done": set(),
           "catalog": {}, "class_level": {"upper": 60, "senior": 90}, "program": itep}
    grad = parse_prereq("Graduate standing or permission of the instructor.")["expr"]
    staff = parse_prereq("Restricted to graduate and education credential students.")["expr"]
    assert evaluate(grad, ctx) == (UNVERIFIED, ["needs instructor permission"])
    assert evaluate(staff, ctx)[0] == UNVERIFIED
    other = ctx | {"program": {"title": "Bachelor of Science in Computer Science"}}
    assert evaluate(grad, other)[0] == NO and evaluate(staff, other)[0] == NO
    # Only what no order of courses can fix: GE areas still to take wait for them, as in any program (SPED 671, PK-3 ITEP)
    ge_first = parse_prereq("GE Areas 1A/A2*, 1B/A3*, 1C/A1*, and 2/B4* all with grades of C- or better; or permission of the instructor.")["expr"]
    assert evaluate(ge_first, ctx)[0] == NO


def test_a_group_after_others_waits_for_their_courses():
    # BS Kinesiology ITEP p.725: students "apply to the Single Subject Physical Education Credential program when in the
    # final semester of completing unit requirements" (prerequisites, core, concentration). Its credential courses' only
    # prereq is being a credential student, which GatorPath can't check, so a new student's plan had KIN 750, S ED 701
    # and S ED 720 in the first term
    name = "bs-kinesiology-integrated-teacher-education-program-in-physical-education"
    program, university, _ = rules_for({"program": name})
    got = plan_for({"catalog_year": "2026-27", "program": name, "start_term": "2027-fall", "completed": []})
    assert got["check"]["valid"]
    when = {c: i for i, s in enumerate(got["semesters"]) for c in s["courses"] if isinstance(c, str)}
    groups = {g["id"]: g for g in program["groups"]}
    codes = lambda g: g.get("all_of", []) + [c for o in g.get("one_of", []) for c in o]
    credential = [c for c in codes(groups["credential"]) if c in when]
    before = [c for a in groups["credential"]["after"] for c in codes(groups[a]) if c in when]
    assert credential and before and min(when[c] for c in credential) > max(when[c] for c in before)
    plan = {"semesters": [{"term": "2027-fall", "courses": ["KIN 750"]}, {"term": "2028-spring", "courses": ["KIN 240"]}]}
    bad = check_plan({"catalog_year": "2026-27", "program": name, "completed": []}, plan, program, university, CATALOG, PREREQS)
    [e] = [e for e in bad["errors"] if e["error"] == "order"]
    assert e["course"] == "KIN 750" and "KIN 240" in e["message"] and "p.725" in e["message"]

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


def rules_for(profile):
    """(program, university, roadmap) for the profile's own program (bs-cs unless it says otherwise)."""
    name = profile.get("program", "bs-cs")
    return (*load_rules("2026-27", name), yaml.safe_load((ROOT / f"rules/roadmaps/2026-27/{name}.yaml").read_text()))


def plan_for(profile):
    from gatorpath.engine.planner import build_plan
    program, university, roadmap = rules_for(profile)
    return build_plan(profile, program, university, roadmap, CATALOG, PREREQS)


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
    recheck = check_plan(profile, {"semesters": got["semesters"]}, *rules_for(profile)[:2], CATALOG, PREREQS)
    assert recheck["valid"] == got["check"]["valid"]
    if path.stem == "p05-cr-grades":
        # MATH 226 and CSC 101 passed with CR: the major doesn't accept CR, and CR courses can't be repeated (p.2392)
        assert not got["check"]["valid"] and got["est_graduation_term"] is None
        assert {e["group"] for e in got["check"]["errors"]} == {"math_physics", "core_cs"}
        assert sum("passed with CR" in w and "see an advisor" in w for w in got["warnings"]) == 2
        first = got["see_advisor"][0]
        assert first["role"] == "substitutions" and first["contact"].startswith("cs-dept@sfsu.edu") and len(first["why"]) == 2
        return
    assert got["check"]["valid"], got["check"]["errors"]
    # D24: each spring/fall term within its roadmap semester's printed load
    assert all("roadmap" in s and s["units"] <= s["max_units"] == s["roadmap"]["units"]
               for s in got["semesters"] if s["term"][5:] in ("spring", "fall"))


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
    # 3 years from a fall 2026 start = spring 2029: 5 terms left, and ~104 units need 6 even at the 19-unit maximum
    late = plan_for(profile | {"graduate_by": "2029-spring"})["pace"]
    assert late["on_time"] is False and late["terms_available"] == 5 and late["load"] == "roadmap"
    assert any(w.startswith("104 units need 6 terms even at 19 a term") for w in late["why_not"])
    # by spring 2028 even the prereq chain can't fit
    soon = plan_for(profile | {"graduate_by": "2028-spring"})["pace"]
    assert any(w.startswith("the prereq chain alone needs 5 terms") for w in soon["why_not"])
    on_time = plan_for(profile | {"graduate_by": "2030-spring"})["pace"]
    assert on_time["on_time"] is True and "why_not" not in on_time


def test_a_light_last_term_folds_into_one_heavier_term():
    profile = eval_profile(ROOT / "evals/profiles/p04-repeats-below-c.yaml")
    got = plan_for(profile)
    sem, fold = got["semesters"], got["pace"]["fold_last_term"]
    # at the roadmap's loads, a 2-unit elective is left past the roadmap's last semester (13 units): into that 13-unit
    # term, one 15-unit term, a term sooner, inside the normal load
    into = next(s for s in sem if s["term"] == fold["term"])
    assert (into["units"], sem[-1]["units"], fold["units"]) == (13, 2, 15)
    assert fold["terms"] == len(sem) - 1 and fold["est_graduation_term"] == sem[-2]["term"]
    assert "see an advisor" not in fold["note"] and fold["note"].endswith(f"In the moved plan {into['term']} has max_units: 15")
    moved = {"semesters": [s | {"courses": s["courses"] + sem[-1]["courses"], "max_units": 15} if s is into else s
                           for s in sem[:-1]]}
    assert check_plan(profile, moved, PROGRAM, UNIVERSITY, CATALOG, PREREQS)["valid"]
    # a 12-unit last term doesn't fit in any term under the 19-unit maximum
    p03 = plan_for(eval_profile(ROOT / "evals/profiles/p03-sophomore-qr34.yaml"))
    assert p03["semesters"][-1]["units"] == 12 and "fold_last_term" not in p03["pace"]
    # check_plan can't see that senior electives wait for a ready option (D19): a transfer's last three don't fold into
    # their first term, the only one with room
    transfer = {"catalog_year": "2026-27", "program": "bs-cs", "start_term": "2027-fall", "qr_pathway": "1/2",
                "ge_certified": True, "first_time": False, "transfer_units": 62,
                "completed": [{"code": c, "grade": "B", "transfer": True}
                              for c in ("CSC 101", "CSC 215", "MATH 226", "MATH 227", "PHYS 220", "PHYS 222")]}
    got = plan_for(transfer)
    assert [x["slot"] for x in got["semesters"][-1]["courses"] if isinstance(x, dict) and x["units"]] == ["senior_electives"] * 3
    assert "fold_last_term" not in got["pace"]


def test_see_advisor_for_permission_and_overload():
    heavy = ["CSC 415", "MATH 227", "PHYS 220", "PHYS 222", "ENG 114", "COMM 150"]  # 3+4+3+1+3+3 = 17
    got = check(FRESHMAN | {"gpa": 2.5, "transfer_units": 60, "max_units_per_term": 18},
                ("2027-spring", heavy), ("2027-fall", ["CSC 653"]))
    advisor = next(a for a in got["see_advisor"] if a["role"] == "major_advisor")
    assert advisor["link"] == "https://cs.sfsu.edu/undergrads/advising" and "Navigator" in advisor["how_to_book"]
    assert any(w.startswith("CSC 653 in 2027-fall: GPA 3.0 or higher (have 2.5)") for w in advisor["why"])
    assert any("17 units is above the normal load of 15" in w for w in advisor["why"])
    assert any(a["role"] == "dpr" for a in got["see_advisor"])


FRESH = {"program": "bs-cs", "catalog_year": "2026-27", "start_term": "2027-fall", "qr_pathway": "1/2", "completed": []}


def test_a_new_freshman_follows_the_roadmap_loads():
    # D24: BS CS QR 1/2 prints 16, 15, 16, 15, 15, 15, 15, 13 units (pp.1908-1909); each term's cap is its semester's
    road = rules_for(FRESH)[2]["variants"]["qr-1-2"]["semesters"]
    got = plan_for(FRESH)
    assert got["check"]["valid"] and got["pace"]["load"] == "roadmap" and "units_per_term" not in got["pace"]
    assert [s["max_units"] for s in got["semesters"]] == [x["units"] for x in road]
    assert all(s["units"] <= s["max_units"] for s in got["semesters"]) and got["semesters"][0]["units"] == 16
    # above 15 as on the roadmap: a note, not an advisor
    assert "2027-fall: 16 units, above the normal 15, as on the Bulletin roadmap (p.1908)" in got["warnings"]
    assert not any("2027-fall" in w for a in got["see_advisor"] for w in a["why"])
    # the normal 15 is the lighter option
    light = got["pace"]["normal_load"]
    assert light["max_units_per_term"] == 15 and light["terms"] >= len(got["semesters"])


def test_roadmap_loads_follow_the_students_units_and_their_own_cap_wins():
    from gatorpath.engine.planner import build_plan
    # a 62-unit transfer: the nearest semester end is 63 (after semester 4), so the plan starts on semester 5's load
    transfer = FRESH | {"ge_certified": True, "first_time": False, "transfer_units": 62,
                        "completed": [{"code": c, "grade": "B", "transfer": True} for c in ("CSC 101", "MATH 226")]}
    assert plan_for(transfer)["semesters"][0]["roadmap"] == {"units": 15, "source": "p.1909"}
    # past the roadmap's last semester, its load (13)
    p04 = plan_for(eval_profile(ROOT / "evals/profiles/p04-repeats-below-c.yaml"))
    assert [s["max_units"] for s in p04["semesters"][-2:]] == [13, 13]
    # F-1: a lighter roadmap semester (Applied Math's ADT roadmap ends 7, 4, 2 units, p.2137) doesn't go under 12
    program, university, roadmap = rules_for({"program": "bs-applied-math"})
    adt = transfer | {"program": "bs-applied-math", "adt": True, "transfer_units": 60, "completed": [
        {"code": c, "grade": "B", "transfer": True} for c in ("MATH 226", "MATH 227", "MATH 228")]}
    light = build_plan(adt, program, university, roadmap, CATALOG, PREREQS)
    f1 = build_plan(adt | {"f1": True}, program, university, roadmap, CATALOG, PREREQS)
    assert min(s["max_units"] for s in light["semesters"]) < 12 <= min(s["max_units"] for s in f1["semesters"])
    assert f1["check"]["valid"], f1["check"]["errors"]
    # the student's max_units_per_term overrides the roadmap; summer keeps its own limit (8, p.2393)
    mine = plan_for(FRESH | {"max_units_per_term": 18, "include_summer": True})
    assert mine["pace"]["load"] == "max_units_per_term" and mine["pace"]["units_per_term"] == 18
    assert {s["max_units"] for s in mine["semesters"]} == {18, 8}
    assert all(s["max_units"] == 8 for s in mine["semesters"] if s["term"].endswith("summer"))


def test_a_choice_whose_options_only_need_an_audition_is_planned():
    # BM Composition's ensembles (MUS 370-390, p.1549) all read "Audition.": nothing to wait for, so the slots go in at
    # upper-division standing like an advisor's pick. Here Applied Math's major electives stand in for them.
    from gatorpath.engine.planner import build_plan
    program, university, roadmap = rules_for({"program": "bs-applied-math"})
    options = next(g for g in program["groups"] if g["id"] == "major_electives")["from"]["list"]
    audition = PREREQS | {c: {"raw_text": "Audition.", **parse_prereq("Audition.")} for c in options}
    fresh = FRESH | {"program": "bs-applied-math"}
    got = build_plan(fresh, program, university, roadmap, CATALOG, audition)
    assert got["check"]["valid"], got["check"]["errors"]
    assert sum(1 for s in got["semesters"] for x in s["courses"] if isinstance(x, dict) and x["slot"] == "major_electives") == 2


def test_an_approval_beside_a_printed_list_keeps_the_list():
    # BS Business Administration: Finance p.153: Select Three from a list; "Other appropriate courses may be selected with
    # prior written consent of an advisor." The list's courses are the options; only a group with no list is the
    # advisor's pick alone (Applied Math's application electives)
    from gatorpath.engine.planner import eligible_options
    program, university, roadmap = rules_for({"program": "bs-applied-math"})
    note = "Other appropriate courses may be selected with prior written consent of an advisor."
    groups = [g | {"approval": note, "from": [g["from"], {"approved": True}]} if g["id"] == "major_electives" else g
              for g in program["groups"]]
    fresh = FRESH | {"program": "bs-applied-math"}
    got = eligible_options(fresh, "major_electives", program | {"groups": groups}, university, CATALOG, PREREQS,
                           by_term="2029-fall")
    assert got["total_options"] >= 9 and any(note in w for w in got["warnings"])
    assert eligible_options(fresh, "application_electives", program, university, CATALOG, PREREQS)["options"] == []


def test_a_prereq_outside_the_requirements_and_roadmap_is_added():
    # BS Physics: PHYS 330 needs MATH 376, which the major doesn't list; the plan stalled. Here Applied Math without MATH
    # 226 on its list or roadmap: MATH 227 still needs it, so the plan adds it
    from gatorpath.engine.planner import build_plan
    program, university, roadmap = rules_for({"program": "bs-applied-math"})
    groups = [g | {"all_of": [c for c in g["all_of"] if c != "MATH 226"]} if g["id"] == "required" else g for g in program["groups"]]
    road = roadmap | {"variants": {k: v | {"semesters": [x | {"items": [i for i in x["items"] if i != "MATH 226"]}
                                                         for x in v["semesters"]]} for k, v in roadmap["variants"].items()}}
    got = build_plan(FRESH | {"program": "bs-applied-math"}, program | {"groups": groups}, university, road, CATALOG, PREREQS)
    assert got["check"]["valid"], got["check"]["errors"]
    why = {c: w for s in got["semesters"] for c, w in s["why"].items()}
    assert "MATH 226" in why and "MATH 227" in why["MATH 226"]


def test_loads_fit_the_graduation_goal_from_the_roadmaps_range():
    # D25: on time on the roadmap's loads: they stay
    assert plan_for(FRESH | {"graduate_by": "2031-spring"})["pace"]["load"] == "roadmap"
    # a 62-unit transfer ends in 2030-spring on the roadmap; by 2029-fall, every term at its heaviest semester (16)
    transfer = FRESH | {"ge_certified": True, "first_time": False, "transfer_units": 62,
                        "completed": [{"code": c, "grade": "B", "transfer": True} for c in ("CSC 101", "MATH 226")]}
    assert plan_for(transfer)["est_graduation_term"] == "2030-spring"
    got = plan_for(transfer | {"graduate_by": "2029-fall"})
    assert got["check"]["valid"] and got["est_graduation_term"] == "2029-fall" and got["pace"]["on_time"]
    assert got["pace"]["load"] == "graduate_by" and {s["max_units"] for s in got["semesters"]} == {16}
    assert got["pace"]["fit"]["note"].endswith("the roadmap's heaviest semester (16)")
    # a freshman a term early needs more than the roadmap ever prints: an overload, so an advisor
    early = plan_for(FRESH | {"graduate_by": "2030-fall"})
    assert early["est_graduation_term"] == "2030-fall" and early["pace"]["fit"]["units_per_term"] == 18
    assert "an overload above 15" in early["pace"]["fit"]["note"] and any(a["role"] == "major_advisor" for a in early["see_advisor"])
    # the student's own cap isn't fitted
    assert plan_for(transfer | {"graduate_by": "2029-fall", "max_units_per_term": 15})["pace"]["load"] == "max_units_per_term"


def test_check_plan_takes_each_terms_cap_and_the_roadmap_load():
    heavy = ["CSC 415", "MATH 227", "PHYS 220", "PHYS 222", "ENG 114", "COMM 150"]  # 3+4+3+1+3+3 = 17
    term = lambda **kw: check_plan(FRESHMAN | {"transfer_units": 60}, {"semesters": [
        {"term": "2027-spring", "courses": heavy} | kw]}, PROGRAM, UNIVERSITY, CATALOG, PREREQS)
    assert errors(term(), "over_cap")  # no cap given: the normal 15
    # QR 3/4's 17-unit semester (p.1910): a plan built at that load passes as built, with a note and no advisor
    as_road = term(max_units=17, roadmap={"units": 17, "source": "p.1910"})
    assert errors(as_road, "over_cap") == [] and "2027-spring: 17 units, above the normal 15, as on the Bulletin roadmap (p.1910)" \
        in as_road["warnings"]
    assert not any("17 units" in w for a in as_road["see_advisor"] for w in a["why"])
    # above the roadmap's load it's an overload again
    above = term(max_units=17, roadmap={"units": 16, "source": "p.1908"})
    assert any("17 units is above the normal load of 15" in w for a in above["see_advisor"] for w in a["why"])
    # the student's cap wins over a term's
    assert errors(check_plan(FRESHMAN | {"transfer_units": 60, "max_units_per_term": 16}, {"semesters": [
        {"term": "2027-spring", "courses": heavy, "max_units": 17}]}, PROGRAM, UNIVERSITY, CATALOG, PREREQS), "over_cap")


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


def f1_senior(**extra):
    """Desktop trial 5: 27 units left (CSC 413, 415, 648, one upper-division GE, 15 senior-elective units) at 12 per term."""
    p02 = yaml.safe_load((ROOT / "evals/profiles/p02-complete-roadmap.yaml").read_text())["profile"]
    left = {"CSC 413", "CSC 415", "CSC 648", "CSC 600", "CSC 652", "CSC 653", "CSC 665", "CSC 675", "PLSI 355"}
    return p02 | {"completed": [r for r in p02["completed"] if r["code"] not in left], "start_term": "2027-spring",
                  "max_units_per_term": 12, **extra}


def test_f1_students_get_full_spring_and_fall_terms():
    # p.2393: "For international students in F1 visa status, immigration regulations require a minimum academic load of
    # 12 units for undergraduates ... for spring and fall semesters"
    # A senior elective goes in as soon as one is ready (CSC 656 in spring 2027), so the plain plan is full too
    assert [s["units"] for s in plan_for(f1_senior())["semesters"]] == [12, 12, 3]
    got = plan_for(f1_senior(f1=True))
    assert [s["units"] for s in got["semesters"]] == [12, 12, 3] and got["check"]["valid"]
    assert any(w.startswith("2028-spring: 3 units; F-1 visa students must carry at least 12") and "Completion of Study"
               in w and "international.sfsu.edu/rcl" in w for w in got["warnings"])  # final-semester RCL
    assert any(w.startswith("F-1: a fully online class counts for only 3 units") for w in got["warnings"])
    assert any(a["role"] == "international" and a["link"].startswith("https://international.sfsu.edu")
               for a in got["see_advisor"])


def test_f1_light_or_skipped_term_is_an_error():
    p = f1_senior(f1=True)
    light = check(p, ("2027-spring", ["CSC 413", "CSC 415"]), ("2027-fall", ["CSC 648"] + 3 * [{"slot": "senior_electives", "units": 3}]))
    assert [e["error"] for e in errors(light)] == ["below_f1_minimum"] and errors(light)[0]["term"] == "2027-spring"
    gap = check(p, ("2027-spring", ["CSC 413", "CSC 415"] + 2 * [{"slot": "senior_electives", "units": 3}]),
                ("2028-spring", ["CSC 648"] + 3 * [{"slot": "senior_electives", "units": 3}]))
    assert [e["error"] for e in errors(gap)] == ["f1_gap"] and "2027-fall" in errors(gap)[0]["message"]  # p.2390
    assert errors(check(f1_senior(), ("2027-spring", ["CSC 413", "CSC 415"]), ("2027-fall", ["CSC 648"]))) == []


def test_f1_term_that_leans_on_online_only_courses_gets_a_warning():
    # international.sfsu.edu/rcl: "only one course (or 3 units) will count toward the enrollment requirement"
    both = {"fall": [4, 4], "spring": [4, 4], "summer": [0, 4], "since": "2023-spring", "until": "2026-fall",
            "last": "2026-fall", "online_only": ["spring"]}
    online = lambda *codes: {c: CATALOG[c] | {"offered": both} for c in codes}
    terms = [("2027-spring", ["CSC 413", "CSC 415"] + 2 * [{"slot": "senior_electives", "units": 3}]),
             ("2027-fall", ["CSC 648"] + 3 * [{"slot": "senior_electives", "units": 3}])]
    plan = {"semesters": [{"term": t, "courses": c} for t, c in terms]}
    run = lambda p, cat: check_plan(p, plan, PROGRAM, UNIVERSITY, CATALOG | cat, PREREQS)
    got = run(f1_senior(f1=True), online("CSC 413", "CSC 415"))
    # a warning, not an error: past sections don't promise future ones
    assert any(w.startswith("2027-spring: CSC 413, CSC 415 ran only fully online") and "counts as 9 of the 12" in w
               for w in got["warnings"])
    for quiet in (run(f1_senior(f1=True), online("CSC 413")), run(f1_senior(), online("CSC 413", "CSC 415"))):
        assert not any("ran only fully online" in w for w in quiet["warnings"])  # 3 online units count; not F-1


def test_in_progress_courses_hold_the_next_spring_or_fall_even_with_summers():
    # Trial 6: last completed 2026-spring, courses in progress (fall 2026): the plan starts 2027-spring, not on top of them
    from gatorpath.engine.planner import first_term
    p = {"completed": [{"code": "CSC 101", "grade": "A", "term": "2026-spring"}], "in_progress": ["CSC 215"]}
    assert first_term(p) == first_term(p | {"include_summer": True}) == "2027-spring"
    assert first_term(p | {"in_progress": [], "include_summer": True}) == "2026-summer"


def test_advisor_handoff_falls_back_to_the_uac_without_program_contacts():
    # ARCHITECTURE D15: a new major needs no advisor names; the UAC routes students to their department
    from gatorpath.engine.planner import see_advisor
    [e] = see_advisor([("substitutions", "CSC 699 for a senior elective")],
                      {k: v for k, v in PROGRAM.items() if k != "advising"}, UNIVERSITY)
    assert e["role"] == "general_advising" and e["why"] == ["CSC 699 for a senior elective"]


def test_a_fall_only_course_waits_for_fall():
    # Phase 5 done-when: never a fall-only course in spring without a warning (Class Search history, ingest.offerings)
    fall_only = {"fall": [4, 4], "spring": [0, 4], "summer": [0, 4], "since": "2023-spring", "until": "2026-fall",
                 "last": "2026-fall"}
    cat = CATALOG | {"CSC 220": CATALOG["CSC 220"] | {"offered": fall_only}}
    plan = {"semesters": [{"term": "2027-spring", "courses": ["CSC 215", "CSC 220"]}]}
    got = check_plan(FRESHMAN, plan, PROGRAM, UNIVERSITY, cat, PREREQS)
    assert any(w.startswith("CSC 220 in 2027-spring: not offered in any of the last 4 spring terms (ran fall 4 of 4")
               for w in got["warnings"])
    from gatorpath.engine.planner import build_plan
    built = build_plan(FRESHMAN | {"start_term": "2027-spring"}, PROGRAM, UNIVERSITY, ROADMAP, cat, PREREQS)
    where = {c: s["term"] for s in built["semesters"] for c in s["courses"] if isinstance(c, str)}
    assert where["CSC 215"] == "2027-spring" and where["CSC 220"].endswith("fall") and built["check"]["valid"]


def test_rare_and_summer_only_courses_are_flagged_not_blocked():
    from gatorpath.engine.planner import season_ok
    span = {"since": "2023-spring", "until": "2026-fall"}
    summer_only = {"CSC 653": {"offered": {"fall": [0, 4], "spring": [0, 4], "summer": [2, 4], "last": "2024-summer"} | span}}
    assert season_ok("CSC 653", "2027-fall", summer_only)[0] is False                          # summers exist: wait
    ok, why = season_ok("CSC 653", "2027-fall", summer_only, ("spring", "fall"))                # a plan without summers
    assert ok and why.startswith("CSC 653: last offered 2024-summer")
    never = {"CSC 668": {"offered": {"fall": [0, 4], "spring": [0, 4], "summer": [0, 4], "last": None} | span}}
    assert season_ok("CSC 668", "2027-fall", never) == (True, "CSC 668: not offered in any term checked (Class Search "
                                                             "2023-spring to 2026-fall); ask the department when it runs")



def test_a_published_terms_schedule_is_exact():
    # Spring 2027's schedule (2026-10-26): a term Class Search was scraped for says which courses run, not history
    from gatorpath.engine.planner import season_ok
    every_spring = {"fall": [4, 4], "spring": [4, 5], "summer": [0, 4], "since": "2023-spring", "until": "2027-spring",
                    "last": "2026-fall", "schedule": {"2026-spring": True, "2027-spring": False}}
    ok, why = season_ok("PSY 441", "2027-spring", {"PSY 441": {"offered": every_spring}})
    assert not ok and why == "PSY 441 in 2027-spring: not on the 2027-spring Class Search schedule; check Class Search"
    fall_only = {"fall": [4, 4], "spring": [1, 5], "summer": [0, 4], "since": "2023-spring", "until": "2027-spring",
                 "last": "2027-spring", "schedule": {"2027-spring": True}}
    assert season_ok("PSY 441", "2027-spring", {"PSY 441": {"offered": fall_only}}) == (True, None)
    assert season_ok("PSY 441", "2028-spring", {"PSY 441": {"offered": every_spring}})[0]  # not scraped: history
    from gatorpath.engine.planner import eligible_options
    off = {"fall": [4, 4], "spring": [4, 5], "summer": [0, 4], "since": "2023-spring", "until": "2027-spring",
           "last": "2026-fall", "schedule": {"2027-spring": False}}
    first = lambda cat: eligible_options(FRESHMAN, "ge_1a", PROGRAM, UNIVERSITY, cat, PREREQS, by_term="2027-spring")["options"]
    top = first(CATALOG)[0]["code"]
    got = first(CATALOG | {top: CATALOG[top] | {"offered": off}})
    assert got[0]["code"] != top and next(o for o in got if o["code"] == top)["not_offered"].startswith(
        f"{top} in 2027-spring: not on the 2027-spring Class Search schedule")  # offered options first

def test_finished_math_adds_no_pathway_courses():
    # Trial 7: MATH 226 met by transfer, QR 3/4: the plan added MATH 197 and 198 from the chain below MATH 226
    p = {"catalog_year": "2026-27", "program": "bs-cs", "qr_pathway": "3/4", "start_term": "2027-spring",
         "completed": [{"code": "CSC 101", "grade": "A", "term": "2026-fall"}, {"code": "MATH 226", "grade": "B", "transfer": True}]}
    planned = {c for s in plan_for(p)["semesters"] for c in s["courses"] if isinstance(c, str)}
    assert "MATH 227" in planned and not planned & {"MATH 197", "MATH 198"}


def test_ge_the_major_meets_plans_no_ge_course():
    # BS Civil Engineering p.1939: GE 1B and 5UD are met by major courses; the plan added a course for each and ran a
    # term past the printed roadmap (9 terms, not 8)
    from gatorpath.engine.planner import NO, OK, evaluate
    name = "bs-civil-engineering"
    got = plan_for({"catalog_year": "2026-27", "program": name, "qr_pathway": "1/2", "start_term": "2027-fall", "completed": []})
    slots = {c["slot"] for s in got["semesters"] for c in s["courses"] if isinstance(c, dict)}
    assert got["check"]["valid"] and len(got["semesters"]) == 8 and not slots & {"ge_1b", "ge_ud_sci"}
    assert "ge_3ud" in slots  # upper-division GE needs 1B first (p.2319): the major's 1B counts
    from gatorpath.engine.planner import cover_combinations
    program, university = load_rules("2026-27", name)
    new = {"catalog_year": "2026-27", "program": name, "qr_pathway": "1/2", "completed": []}
    shown = cover_combinations(new, program, university, CATALOG, PREREQS, by_term="2027-fall")["open"]
    assert "GE 1A English Composition" in shown and not [x for x in shown if x.startswith(("GE 1B", "GE 5UD"))]
    ctx = {"done": {"ENGR 282"}, "ge_done": set(), "catalog": CATALOG, "program": program, "profile": {}}
    assert evaluate({"ge_area": "1B"}, ctx)[0] == NO
    assert evaluate({"ge_area": "1B"}, ctx | {"done": {"ENGR 282", "ENGR 201"}})[0] == OK


def test_upper_division_and_graduate_isnt_graduate_only():
    # MUS 434: "Restricted to upper-division and graduate Broadcast & Electronic Communication Arts and Music majors"
    from gatorpath.engine.planner import NO, OK, evaluate
    ctx = {"program": {"title": "Bachelor of Music in Music"}, "units": 60, "class_level": UNIVERSITY["class_level"]}
    text = "upper-division and graduate Broadcast & Electronic Communication Arts and Music majors"
    assert evaluate({"restricted_to": text}, ctx)[0] == OK
    assert evaluate({"restricted_to": text}, ctx | {"units": 30})[0] == NO  # not upper-division yet
    assert evaluate({"restricted_to": "graduate students"}, ctx)[0] == NO
    # KIN 750: open to the integrated teacher education program's undergraduates too
    assert evaluate({"restricted_to": "graduate standing or KIN ITEP credential students"}, ctx)[0] != NO


def test_not_open_after_a_course_is_an_exclusion():
    # ERTH 110: "Not open to students who have completed ERTH 112."
    from gatorpath.engine.planner import NO, OK, evaluate
    assert evaluate({"not_after": "ERTH 112"}, {"done": set()})[0] == OK
    state, why = evaluate({"not_after": "ERTH 112"}, {"done": {"ERTH 112"}})
    assert state == NO and why == ["no ERTH 112 before this term (not open to students who have completed it)"]


def test_a_dpr_substitution_is_unverified_for_prereqs_not_blocked():
    # Trial 7: MATH 325 met MATH 225 on the DPR; electives needing MATH 225 showed as blocked
    from gatorpath.engine.planner import UNVERIFIED, evaluate
    ctx = {"done": set(), "grades": {}, "same_term": set(), "profile": {"dpr_met": ["MATH 225"]}}
    state, why = evaluate({"course": "MATH 225", "min_grade": "C"}, ctx)
    assert state == UNVERIFIED and why[0].startswith("MATH 225, which your DPR shows met by a substitution")


def test_ge_combinations_list_every_minimal_way():
    # One course for 4UD + ESCA + GP, or two that split them, or one each (ENVS 401's Bulletin tags; the rest are real rows)
    from gatorpath.engine.planner import cover_combinations
    cat = CATALOG | {"ENVS 401": CATALOG["PLSI 355"] | {"title": "International Development and Resource Justice",
                                                        "ge_areas": ["4UD", "ESCA", "GP"]}}
    p = {"catalog_year": "2026-27", "program": "bs-cs", "transfer_units": 60,
         "ge_done": ["1A", "1B", "1C", "2", "3A", "3B", "4", "5A", "5B", "5C", "6", "3UD", "5UD", "USH", "USG", "CSLG", "AERM", "SJ"]}
    got = cover_combinations(p, PROGRAM, UNIVERSITY, cat, PREREQS, by_term="2027-spring")
    assert [t.split(":")[-1].strip()[:6] for t in got["open"]] == ["GE 4UD", "Enviro", "Global"]  # not GWAR: CSC 300GW
    first = got["ways"][0]
    assert first["courses"] == 1 and "ENVS 401" in [e["code"] for e in first["parts"][0]["examples"]]
    two = [w for w in got["ways"] if w["courses"] == 2]
    assert any(len(part["covers"]) == 2 and part["examples"] for w in two for part in w["parts"])  # one course for two of them
    for w in got["ways"]:  # every way covers all three, and every part is needed
        assert set().union(*(set(part["covers"]) for part in w["parts"])) == set(got["open"])


def test_us_history_options_follow_the_first_time_rule():
    # Test user 1 (2026-10-20): ge_combinations offered AFRS 375 (USH, upper division) for US History to a first-time
    # student, then check_plan rejected it. p.2313: first-time students meet it with a lower-division Area 4 USH course
    from gatorpath.engine.planner import eligible_options
    opts = lambda p, gid: {o["code"]: o for o in eligible_options(p, gid, PROGRAM, UNIVERSITY, CATALOG, PREREQS,
                                                                  by_term="2027-spring", limit=99)["options"]}
    transfer = FRESHMAN | {"transfer_units": 30}
    assert "AA S 210" in opts(FRESHMAN, "ai_ush") and "HIST 470" not in opts(FRESHMAN, "ai_ush")
    assert "HIST 470" in opts(transfer, "ai_ush")
    assert "ai_ush" not in opts(FRESHMAN, "ai_usg")["HIST 470"]["also_covers"]
    assert "ai_ush" in opts(transfer, "ai_usg")["HIST 470"]["also_covers"]


def test_a_retake_in_progress_replaces_the_old_grade():
    # 2026-10-20: a course being retaken kept its old failing grade, so the courses after it showed blocked
    from gatorpath.engine.planner import build_plan, eligible_options
    p = FRESHMAN | {"completed": FRESHMAN["completed"] + [{"code": "CSC 215", "grade": "F", "term": "2026-fall"}],
                    "in_progress": ["CSC 215"]}
    assert errors(check(p, ("2027-spring", ["CSC 220"]))) == []
    assert not any("have F" in w for w in build_plan(p, PROGRAM, UNIVERSITY, ROADMAP, CATALOG, PREREQS)["warnings"])
    opts = eligible_options(p, "senior_electives", PROGRAM, UNIVERSITY, CATALOG, PREREQS, by_term="2027-spring", limit=999)
    assert not any("have F" in r for o in opts["options"] for r in o.get("blocked_by", []))


def test_the_current_term_is_taken_by_in_progress_courses():
    # Eval plan-p01 (codex): start_term 2026-fall, the term CSC 101 is in progress, and CSC 215 was planned beside it
    from gatorpath.engine.planner import first_term
    now = {"current_term": "2026-fall", "in_progress": ["CSC 101", "MATH 226"]}
    assert first_term(now) == "2027-spring"  # nothing completed yet: the term after this one, not needs_input
    assert first_term(now | {"start_term": "2026-fall"}) == "2027-spring"
    assert first_term(now | {"start_term": "2027-fall"}) == "2027-fall"
    from gatorpath.engine.planner import build_plan
    moved = build_plan(FRESHMAN | now | {"completed": [], "start_term": "2026-fall"}, PROGRAM, UNIVERSITY, ROADMAP, CATALOG, PREREQS)
    assert moved["semesters"][0]["term"] == "2027-spring"
    assert any(w.startswith("start_term 2026-fall isn't after the current term (2026-fall)") for w in moved["warnings"])
    p = FRESHMAN | now | {"completed": []}
    same = check(p, ("2026-fall", ["CSC 215"]))
    assert [e["error"] for e in errors(same)][:1] == ["term_in_progress"]
    past = check(FRESHMAN | {"current_term": "2026-fall", "completed": []}, ("2026-spring", ["CSC 101"]))
    assert "term_in_past" in [e["error"] for e in errors(past)]
    assert not any(e["error"].startswith("term_in") for e in errors(check(p, ("2027-spring", ["CSC 215"]))))


def test_a_roadmap_without_qr_pathways_fits_every_first_time_student():
    # 2024-25 BS CS has one First-Time Student Roadmap (p.1947), not one per QR pathway
    from gatorpath.engine.planner import pick_variant
    one = {"variants": {"first-time": {"title": "First-Time Student Roadmap"}, "adt": {"title": "ADT"}}}
    assert pick_variant({}, one) == "first-time" and pick_variant({"adt": True}, one) == "adt"
    assert pick_variant({}, ROADMAP) is None and pick_variant({"qr_pathway": "3/4"}, ROADMAP) == "qr-3-4"


def test_winter_session_sits_between_fall_and_spring():
    # "Scheduled during the intersession between the Fall and Spring term"; "The maximum number of units a student may
    # earn in Winter Session is 4 units" (2026-27 p.1716). 2027-winter is January 2027 (DPRs print "Winter 2027").
    from gatorpath.engine.planner import next_term, term_key
    assert term_key("2026-fall") < term_key("2027-winter") < term_key("2027-spring")
    assert next_term("2026-fall", False, winter=True) == "2027-winter" and next_term("2027-winter", False) == "2027-spring"
    assert next_term("2026-fall", False) == "2027-spring" and next_term("2027-spring", True, winter=True) == "2027-summer"
    p = FRESHMAN | {"f1": True}
    one = check(p, ("2027-winter", ["PSY 200"]), ("2027-spring", ["CSC 215", "MATH 227", "PHYS 220", "PHYS 222", "ENG 114"]))
    assert errors(one) == [] and not any(w.startswith("2027-winter: 3 units is below") for w in one["warnings"])
    over = check(FRESHMAN, ("2027-winter", ["CSC 215", "PSY 200"]))
    [e] = errors(over, "over_max_units")
    assert "4-unit Winter Session maximum" in e["message"] and "p.1716" in e["message"]


def test_build_plan_uses_winter_terms_only_when_asked_and_only_for_ge_and_electives():
    from gatorpath.engine.planner import build_plan
    plain = build_plan(FRESHMAN, PROGRAM, UNIVERSITY, ROADMAP, CATALOG, PREREQS)
    assert not any(s["term"].endswith("winter") for s in plain["semesters"])
    got = build_plan(FRESHMAN | {"include_winter": True}, PROGRAM, UNIVERSITY, ROADMAP, CATALOG, PREREQS)
    winters = [s for s in got["semesters"] if s["term"].endswith("winter")]
    assert winters and got["check"]["valid"]
    # Test user 1 asked about Winter 2027 while in Fall 2026: winter is the first term after the one underway
    from gatorpath.engine.planner import first_term
    now = {"completed": [], "current_term": "2026-fall", "in_progress": ["CSC 101"], "include_winter": True}
    assert first_term(FRESHMAN | now) == "2027-winter" and first_term(FRESHMAN | now | {"include_winter": False}) == "2027-spring"
    for s in winters:  # Class Search has no Winter Session history: no required major course is put there
        assert s["units"] <= 4 and all(isinstance(c, dict) for c in s["courses"])


def test_a_plan_with_an_unparsed_group_is_checked_except_for_it():
    from gatorpath.engine.planner import build_plan
    profile = eval_profile(ROOT / "evals/profiles/p11-applied-math-sophomore.yaml")
    program, university, roadmap = rules_for(profile)
    odd = {"id": "cr_nc_limit", "unparsed": True, "source": "p.437",
           "quote": "No more than 9 units can be taken with CR/NC grading."}
    got = build_plan(profile, program | {"groups": program["groups"] + [odd]}, university, roadmap, CATALOG, PREREQS)
    assert got["check"]["valid"], got["check"]["errors"]
    assert any(w.startswith("cr_nc_limit: not checked") for w in got["warnings"])


def test_a_select_one_plans_an_option_whose_prereqs_can_be_met():
    # Applied Math "Select One: MATH 209, CSC 101 & CSC 215, or CSC 309" (p.2129) plans MATH 209, the fewest units, first
    # printed. Here MATH 209 is given a prereq no undergraduate meets, the way CHEM 180 once read for QR 3/4 placement.
    from gatorpath.engine.planner import build_plan
    program, university, roadmap = rules_for({"program": "bs-applied-math"})
    fresh = {"program": "bs-applied-math", "catalog_year": "2026-27", "start_term": "2027-fall", "qr_pathway": "1/2",
             "completed": []}
    planned = lambda p: {c for s in p["semesters"] for c in s["courses"] if isinstance(c, str)}
    assert "MATH 209" in planned(build_plan(fresh, program, university, roadmap, CATALOG, PREREQS))
    blocked = PREREQS | {"MATH 209": {"raw_text": "Graduate standing.", **parse_prereq("Graduate standing.")}}
    got = build_plan(fresh, program, university, roadmap, CATALOG, blocked)
    assert got["check"]["valid"], got["check"]["errors"]
    # CSC 309 is ready too, but MATH 400 (required) needs CSC 215 or MATH 209, so the plan takes CSC 101 & CSC 215
    assert {"CSC 101", "CSC 215"} <= planned(got) and not planned(got) & {"MATH 209", "CSC 309"}
    assert any("planned CSC 101, CSC 215, not MATH 209, which leaves a prereq in this plan unmet" in w for w in got["warnings"])


def test_a_roadmap_major_slot_naming_a_select_one_places_its_course():
    # drafted roadmaps write "Select One (Major Core)" as {slot: major, group: <the one_of group>}. A student past MATH
    # 376 and MATH 400 doesn't need MATH 209 early, so only the roadmap puts it in the first term.
    from gatorpath.engine.planner import build_plan
    program, university, roadmap = rules_for({"program": "bs-applied-math"})
    done = ["MATH 226", "MATH 227", "MATH 228", "MATH 301GW", "MATH 325", "MATH 376", "MATH 400", "MATH 440"]
    profile = {"program": "bs-applied-math", "catalog_year": "2026-27", "start_term": "2027-fall", "qr_pathway": "1/2",
               "completed": [{"code": c, "grade": "A", "term": "2026-spring"} for c in done]}
    v = roadmap["variants"]["qr-1-2"]
    sems = [s | {"items": [i for i in s["items"] if not (isinstance(i, dict) and "MATH 209" in i.get("one_of", []))]}
            for s in v["semesters"]]
    sems[0] = sems[0] | {"items": [{"slot": "major", "group": "programming", "units": 3}] + sems[0]["items"]}
    got = build_plan(profile, program, university, roadmap | {"variants": {"qr-1-2": v | {"semesters": sems}}}, CATALOG, PREREQS)
    assert got["check"]["valid"] and next(s["term"] for s in got["semesters"] if "MATH 209" in s["courses"]) == "2027-fall"


def test_compare_programs_says_what_carries_over_to_a_new_major():
    from gatorpath.engine.planner import compare_programs
    profile = eval_profile(ROOT / "evals/profiles/p03-sophomore-qr34.yaml")  # BS CS, QR 3/4, MATH 226 in progress
    current, target = rules_for(profile), rules_for({"program": "bs-applied-math"})
    got = compare_programs(profile, (current[0], current[2]), (target[0], target[2]), UNIVERSITY, CATALOG, PREREQS)
    # Applied Math (p.2129): CSC 101 & CSC 215 is one "Select One" option, MATH 226 is required; CSC 220 and MATH 225 aren't
    assert got["courses"] == {"count_in_both": ["CSC 101", "CSC 215", "MATH 226"], "only_current": ["CSC 220", "MATH 225"],
                              "only_target": []}
    assert got["target"]["major_units"] == {"done": 7, "in_progress": 4, "needed": 55}
    groups = {g["id"]: g for g in got["target"]["groups"]}
    assert groups["programming"]["status"] == "satisfied" and groups["required"]["in_progress"] == ["MATH 226"]
    assert got["current"]["plan_valid"] and got["target"]["plan_valid"]
    assert got["extra_terms"] == got["target"]["terms"] - got["current"]["terms"]
    assert any(w.startswith("CSC 220, MATH 225 still count toward the 120 units") for w in got["warnings"])
    assert got["see_advisor"][0]["role"] == "substitutions" and any(a["role"] == "major_advisor" for a in got["see_advisor"])
    # a DPR substitution for the current major isn't carried to the new one
    sub = compare_programs(profile | {"dpr_met": ["MATH 324"]}, (current[0], current[2]), (target[0], target[2]),
                           UNIVERSITY, CATALOG, PREREQS)
    assert any(w.startswith("Substitutions on your DPR (MATH 324) are your current major's") for w in sub["warnings"])


@pytest.mark.parametrize("path", sorted((ROOT / "rules/roadmaps").glob("*/*.yaml")), ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_roadmap_files_pass_check_roadmap(path):
    # ARCHITECTURE §6.2 "AI-drafted rules": the hand-written roadmaps are the bar a drafted one is held to
    from gatorpath.engine.planner import check_roadmap
    program, university = load_rules(path.parent.name, path.stem)
    from gatorpath.ingest.programs import LOADABLE
    got = check_roadmap(yaml.safe_load(path.read_text()), program, university, CATALOG)
    if program.get("drafted_by"):  # a loaded draft may name a group still flagged for a person (--load)
        got = [x for x in got if not any(k in x for k in LOADABLE)]
    # the 2025-26 QR 3/4 roadmap never prints PHYS 222, which the major requires (p.1905): the check finds it
    assert got == (["qr-3-4: required but not on this roadmap: PHYS 222"] if f"{path.parent.name}/{path.stem}" == "2025-26/bs-cs" else [])


def test_check_roadmap_reports_what_a_person_must_fix():
    from gatorpath.engine.planner import check_roadmap
    program, university, roadmap = rules_for({"program": "bs-applied-math"})
    v = roadmap["variants"]["qr-1-2"]
    first = v["semesters"][0] | {"items": ["MATH 226", "MATH 999", {"slot": "GE", "area": "9Z", "units": 3},
                                           {"slot": "major", "group": "required", "units": 3}, {"slot": "minor", "units": 3}]}
    bad = roadmap | {"drafted": True, "variants": {
        "qr-1-2": v | {"semesters": [first] + [s for s in v["semesters"][1:] if "MATH 696" not in s["items"]]},
        "transfer": roadmap["variants"]["adt"]}}
    got = check_roadmap(bad, program, university, CATALOG, set(range(2132, 2139)))
    assert got[:6] == ["unknown key 'drafted'", "qr-1-2 semester 1: MATH 999 is not in the 2026-27 catalog",
                       "qr-1-2 semester 1: area '9Z' matches no GE or American Institutions group",
                       "qr-1-2 semester 1: group 'required' isn't a choose or Select One group of bs-applied-math",
                       "qr-1-2 semester 1: unknown slot 'minor' (one of GE, ai, elective, major, senior_elective, "
                       "sfss_or_elective)", "qr-1-2 semester 1: the items add up to 13, units says 16"]
    assert "qr-1-2: the semesters add up to 105, total_units says 120" in got
    assert "qr-1-2: required but not on this roadmap: MATH 696" in got
    assert "transfer: the planner reads only the variants qr-1-2, qr-3-4, first-time, adt" in got
    assert got[-1].startswith("roadmap pages 2134, 2135, 2138 aren't in any variant")
    # a variable-unit course printed at more than its minimum ("AIS 694 Community Service Learning", 1-3, printed 3)
    variable = CATALOG | {"MATH 226": CATALOG["MATH 226"] | {"units_max": 7}}
    fixed = roadmap | {"variants": {"qr-1-2": v | {"semesters": [first | {"items": ["MATH 226"], "units": 7}]}}}
    assert not [x for x in check_roadmap(fixed, program, university, variable) if "semester 1:" in x]
    assert "qr-1-2 semester 1: the items add up to 4 (7 with variable-unit courses at their most), units says 8" in \
        check_roadmap(roadmap | {"variants": {"qr-1-2": v | {"semesters": [first | {"items": ["MATH 226"], "units": 8}]}}},
                      program, university, variable)


def test_check_groups_in_a_plan():
    # §6.2 check groups: grades a plan can't change are a warning (BS CS's "no more than one course below C-" broken by a
    # D already earned), while units a plan chooses are checked like any requirement ("A total of 30 Sociology units must
    # be upper-division", p.851: here 70 upper-division CSC units, more than BS CS has)
    from gatorpath.engine.planner import build_plan
    low = {"id": "low", "title": "Low grades", "across": "major", "max_below": {"grade": "C-", "courses": 0}, "source": "p.2027"}
    ud = {"id": "ud", "title": "Upper-division CSC", "across": "major", "source": "p.851",
          "min_units_from": {"subject": "CSC", "level": "upper", "units": 70}}
    profile = FRESH | {"completed": FRESH["completed"] + [{"code": "CSC 520", "grade": "D", "term": "2026-fall"}]}  # an elective: no C minimum
    got = build_plan(profile, PROGRAM | {"groups": PROGRAM["groups"] + [low]}, UNIVERSITY, ROADMAP, CATALOG, PREREQS)
    assert got["check"]["valid"], got["check"]["errors"]
    assert any(w.startswith("Low grades: not met by the grades so far") for w in got["warnings"])
    got = build_plan(FRESH, PROGRAM | {"groups": PROGRAM["groups"] + [ud]}, UNIVERSITY, ROADMAP, CATALOG, PREREQS)
    assert any("Upper-division CSC: depends on which courses fill the slots" in w for w in got["warnings"])
    filled = check_plan(FRESH, {"semesters": got["semesters"]}, PROGRAM | {"groups": [g for g in PROGRAM["groups"]
                        if g["id"] != "senior_electives"] + [ud]}, UNIVERSITY, CATALOG, PREREQS)
    assert {e.get("group") for e in filled["errors"]} >= {"ud"}  # no slots in its groups: the plan's courses decide
    from gatorpath.engine.planner import eligible_options
    assert eligible_options(FRESH, "ud", PROGRAM | {"groups": PROGRAM["groups"] + [ud]}, UNIVERSITY, CATALOG,
                            PREREQS)["error"] == "not_a_choice"
