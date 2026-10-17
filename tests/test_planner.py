"""check_plan over the eval catalog snapshot + real Bulletin prereq strings (tests/fixtures/catalog_rows.json)."""

import json
from pathlib import Path

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
    low_gpa = FRESHMAN | {"gpa": 2.5, "transfer_units": 60}
    assert "GPA 3.0" in errors(check(low_gpa, ("2027-spring", ["CSC 415"]), ("2027-fall", ["CSC 653"])), "prereq_not_met")[-1]["message"]
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
    assert errors(ok18) == [] and any("above the normal load of 15 (p.2393)" in w for w in ok18["warnings"])
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
