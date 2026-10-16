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
