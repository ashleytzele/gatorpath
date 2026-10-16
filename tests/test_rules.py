import json
import re
from pathlib import Path

import pytest
import yaml

from gatorpath.engine.rules import RULES_DIR, audit, load_rules, matches, rank

ROOT = Path(__file__).parents[1]
CATALOG = json.loads((ROOT / "evals/catalog-2026-27.json").read_text())
PROGRAM, UNIVERSITY = load_rules("2026-27", "bs-cs")
PROFILES = sorted((ROOT / "evals/profiles").glob("*.yaml"))


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.stem)
def test_eval_profile_matches_hand_computed_audit(path):
    case = yaml.safe_load(path.read_text())
    want = case["expected"]
    got = audit(case["profile"], PROGRAM, UNIVERSITY, CATALOG)
    groups = {g["id"]: g for g in got["groups"]}
    assert {i: g["status"] for i, g in groups.items()} == {i: want["groups"].get(i, want["groups"]["*"]) for i in groups}
    assert got["complete"] == want["complete"]
    for gid, codes in want.get("counted", {}).items():
        assert sorted(groups[gid]["counted"]) == sorted(codes), gid
    for gid, codes in want.get("in_progress", {}).items():
        assert sorted(groups[gid]["in_progress"]) == sorted(codes), gid
    for key, value in want.get("totals", {}).items():
        t = got["totals"][key]
        assert (t["value"] if isinstance(t, dict) else t) == value, key
    for key, ok in want.get("totals_ok", {}).items():
        assert got["totals"][key]["ok"] is ok, key
    for text in want.get("warnings_include", []):
        assert any(text in w for w in got["warnings"]), text
    if "warnings_exactly" in want:
        assert len(got["warnings"]) == want["warnings_exactly"], got["warnings"]
    assert got["catalog_year"] == "2026-27"


def test_every_profile_code_is_a_real_course():
    for path in PROFILES:
        p = yaml.safe_load(path.read_text())["profile"]
        for code in [r["code"] for r in p["completed"]] + p.get("in_progress", []):
            assert code in CATALOG, f"{path.name}: {code}"


def test_cr_meets_c_minus_but_not_c():
    assert rank("CR") >= rank("C-") and rank("CR") < rank("C")
    assert rank("F") is None and rank("W") is None and rank("D-") > 0


def test_level_and_paired_filters():
    grad = {"subject": "CSC", "level": "700+", "paired": False, "except": ["CSC 899"]}
    assert matches(grad, "CSC 869", CATALOG["CSC 869"])
    assert not matches(grad, "CSC 852", CATALOG["CSC 852"])  # paired with CSC 652
    six = {"subject": "CSC", "level": 600, "except": ["CSC 601"]}
    assert matches(six, "CSC 665", CATALOG["CSC 665"]) and not matches(six, "CSC 601", CATALOG["CSC 601"])
    assert not matches(six, "CSC 510", CATALOG["CSC 510"])


def test_every_rule_group_cites_a_page():
    for g in PROGRAM["groups"] + UNIVERSITY["groups"]:
        assert re.fullmatch(r"p\.\d{4}.*", g["source"]), g["id"]


def test_major_units_add_up_to_74():
    required = sum(CATALOG[c]["units_min"] for g in PROGRAM["groups"] for c in g.get("all_of", []))
    electives = next(g for g in PROGRAM["groups"] if g["id"] == "senior_electives")["choose_units"]
    assert required + electives == PROGRAM["total_units"] == 74


def test_ge_area_minimums_add_up_to_43():
    assert sum(g.get("choose_units", 0) for g in UNIVERSITY["groups"] if g["id"].startswith("ge_")) == 43


ROADMAPS = yaml.safe_load((RULES_DIR / "roadmaps/2026-27/bs-cs.yaml").read_text())


@pytest.mark.parametrize("variant", ROADMAPS["variants"])
def test_roadmap_semesters_add_up_to_printed_units(variant):
    v = ROADMAPS["variants"][variant]
    for i, sem in enumerate(v["semesters"], 1):
        units = sum(CATALOG[x]["units_min"] if isinstance(x, str) else x["units"] for x in sem["items"])
        assert units == sem["units"], f"{variant} semester {i}"
    assert sum(s["units"] for s in v["semesters"]) == v["total_units"]


def run(completed, in_progress=()):
    profile = {"catalog_year": "2026-27", "completed": completed, "in_progress": list(in_progress)}
    return audit(profile, PROGRAM, UNIVERSITY, CATALOG)


def test_retaking_a_passed_course_in_progress_is_flagged():
    got = run([{"code": "CSC 220", "grade": "B", "term": "2026-fall"}], in_progress=["CSC 220"])
    assert any("CSC 220: attempt 2" in w and "may not be repeated" in w for w in got["warnings"])


def test_grades_are_normalized_and_unknown_symbols_flagged():
    got = run([{"code": "CSC 101", "grade": " b", "term": "2026-fall"}, {"code": "CSC 215", "grade": "P", "transfer": True}])
    core = next(g for g in got["groups"] if g["id"] == "core_cs")
    assert core["counted"] == ["CSC 101"]
    assert any("CSC 215: grade 'P'" in w and "enter CR" in w for w in got["warnings"])


def test_major_gpa_keeps_a_failed_attempt_while_it_is_retaken():
    got = run([{"code": "CSC 101", "grade": "A"}, {"code": "CSC 215", "grade": "F"}], in_progress=["CSC 215"])
    assert got["totals"]["gpa_major"]["value"] == got["totals"]["gpa_sf_state"]["value"] == 1.714


def test_forgiveness_is_shared_by_sf_state_and_major_gpa():
    # 18 repeated units > 16: ENG 114, PHIL 110, CSC 101, 220, 230 are forgiven; CSC 256's F stays, in both GPAs.
    codes = ["ENG 114", "PHIL 110", "CSC 101", "CSC 220", "CSC 230", "CSC 256"]
    got = run([{"code": c, "grade": "F"} for c in codes] + [{"code": c, "grade": "A"} for c in codes])
    assert got["totals"]["gpa_sf_state"]["value"] == round(72 / 21, 3)
    assert got["totals"]["gpa_major"]["value"] == round(48 / 15, 3)


def test_area_4_disciplines_looks_past_the_greedy_pick():
    got = run([{"code": c, "grade": "A"} for c in ("HIST 120", "HIST 130", "PSY 200", "HIST 308")])
    assert next(g for g in got["groups"] if g["id"] == "ge_4_disciplines")["status"] == "satisfied"


def test_transfer_then_sf_state_repeat_counts_units_once():
    got = audit({"completed": [{"code": "MATH 226", "grade": "C-", "transfer": True}, {"code": "MATH 226", "grade": "A"}],
                 "transfer_units": 4}, PROGRAM, UNIVERSITY, CATALOG)
    assert got["totals"]["units"]["value"] == 4


def test_numeric_ge_done_and_transfer_upper_division_units():
    got = audit({"ge_done": [2], "transfer_units": 3, "completed": [{"code": "CSC 317", "grade": "B", "transfer": True}]},
                PROGRAM, UNIVERSITY, CATALOG)
    assert next(g for g in got["groups"] if g["id"] == "ge_2")["status"] == "satisfied"
    assert got["totals"]["upper_division_units"]["value"] == 3
    assert got["totals"]["residence_upper_division_units"]["value"] == 0
