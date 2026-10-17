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


def test_translate_ge_reads_dpr_wording():
    from gatorpath.engine.rules import translate_ge

    got, warnings = translate_ge(["Area D - Social Sciences", "GE D/USH", "UD-D", "A2", "1B", "E", "Area Q"], UNIVERSITY)
    assert got == ["4", "USH", "4UD", "1A", "1B"]
    assert "D → 4" in warnings[0] and "UD-D → 4UD" in warnings[0]
    assert "GE E: no 2026-27 equivalent" in warnings[1]
    assert warnings[2] == "ge_done entries not recognized as GE areas, ignored: Area Q"


BASE = {"catalog_year": "2026-27", "program": "bs-cs"}
groups_of = lambda result: {g["id"]: g for g in result["groups"]}


def test_first_time_students_meet_us_history_only_with_lower_division_area_4():
    # p.2313: "first-time college students will satisfy US History by completing a Lower-Division Area 4 course with USH"
    hist_470 = [{"code": "HIST 470", "grade": "A", "term": "2026-fall"}]  # 3UD, USG, CSLG, USH: not Area 4
    first = audit(BASE | {"completed": hist_470}, PROGRAM, UNIVERSITY, CATALOG)
    assert groups_of(first)["ai_ush"]["status"] == "remaining"
    assert any("HIST 470: carries the area but doesn't meet American Institutions: U.S. History" in w for w in first["warnings"])
    transfer = audit(BASE | {"completed": hist_470, "transfer_units": 30}, PROGRAM, UNIVERSITY, CATALOG)
    assert groups_of(transfer)["ai_ush"]["status"] == "satisfied"
    aa_s_210 = audit(BASE | {"completed": [{"code": "AA S 210", "grade": "B", "term": "2026-fall"}]}, PROGRAM, UNIVERSITY, CATALOG)
    assert groups_of(aa_s_210)["ai_ush"]["status"] == "satisfied"  # Area 4 + USH


def test_cal_getc_certification_meets_lower_division_ge():
    # p.2304: CCCs "can certify up to 34 semester ... units of ... (Cal-GETC) ... to fulfill lower-division general education"
    ld = UNIVERSITY["transfer"]["certified_ld_ge"]
    assert sum(g["choose_units"] for g in UNIVERSITY["groups"] if g["id"] in ld) == 34
    got = groups_of(audit(BASE | {"transfer_units": 60, "ge_certified": True}, PROGRAM, UNIVERSITY, CATALOG))
    assert all(got[i]["status"] == "satisfied" and got[i]["met_by"] == "ge_certification" for i in ld)
    assert got["ge_4_disciplines"]["status"] == "satisfied"
    assert got["ge_3ud"]["status"] == "remaining" and got["ge_4ud"]["status"] == "remaining"  # upper division still due


def test_transfer_unit_caps():
    # p.2304: "no more than a total of 90 semester ... units may be transferred into the university from all sources"
    over = audit(BASE | {"transfer_units": 95}, PROGRAM, UNIVERSITY, CATALOG)
    assert over["totals"]["units"]["value"] == 90 and any("at most 90 can be transferred" in w for w in over["warnings"])
    # p.2313: "Maximum Units for Community College Work: 70 units"
    cc = audit(BASE | {"transfer_units": 75}, PROGRAM, UNIVERSITY, CATALOG)
    assert cc["totals"]["units"]["value"] == 75 and any("no more than 70 from community colleges" in w for w in cc["warnings"])


def test_repeat_policy_comes_from_the_rules():
    # p.2392: "Exceptions to repeat a course for 3 or more times require the consent of the instructor and department chair"
    rows = [{"code": "CSC 220", "grade": g, "term": t} for g, t in (("F", "2025-fall"), ("D", "2026-spring"), ("C", "2026-fall"))]
    got = audit(BASE | {"completed": rows}, PROGRAM, UNIVERSITY, CATALOG)
    assert any("attempt 3" in w and "instructor and department chair" in w for w in got["warnings"])
    # "cannot repeat any courses once they have repeated 28 units of SF State units"
    many = [{"code": c, "grade": g, "term": t} for c in ("CSC 220", "CSC 230", "CSC 256", "CSC 340", "CSC 413", "CSC 415",
                                                         "CSC 510", "CSC 317", "CSC 648", "CSC 300GW")
            for g, t in (("F", "2025-fall"), ("B", "2026-spring"))]
    assert any("30 SF State units of repeats" in w for w in audit(BASE | {"completed": many}, PROGRAM, UNIVERSITY, CATALOG)["warnings"])


def test_senior_electives_under_3_units_are_flagged():
    # p.1905: "five 3-unit senior electives", but the list names CSC 685 (1 unit)
    case = yaml.safe_load((ROOT / "evals/profiles/p06-elective-rules.yaml").read_text())
    got = audit(case["profile"], PROGRAM, UNIVERSITY, CATALOG)
    assert any(w.startswith("CSC 685: 1 units counted toward Electives (15 units), which asks for 3-unit courses")
               for w in got["warnings"])


def test_projects_in_teaching_685_cap():
    # p.2313: at most 4 units of courses "Numbered '685' and Titled 'Projects in Teaching ...'" apply to the degree
    cat = CATALOG | {"C J 685": {"title": "Projects In Teaching Criminal Justice", "units_min": 1.0, "units_max": 4.0,
                                 "grading": None, "ge_areas": [], "paired": False, "repeatable": True, "source_page": 0}}
    rows = [{"code": "C J 685", "grade": "A", "units": 3, "term": t} for t in ("2025-fall", "2026-spring")]
    got = audit(BASE | {"completed": rows}, PROGRAM, UNIVERSITY, cat)
    assert got["totals"]["units"]["value"] == 4 and any("only 4 units of" in w for w in got["warnings"])


def test_engine_grade_points_match_the_bulletin():
    from gatorpath.engine.rules import GRADE_POINTS
    assert GRADE_POINTS == UNIVERSITY["grading"]["points"]  # p.2405
    assert rank("CR") == GRADE_POINTS[UNIVERSITY["grading"]["cr_counts_as"]]  # p.2403


def test_prior_bachelors_degree_waives_university_requirements():
    # p.2313: "will not have to complete any GE or additional graduation requirements"
    got = audit(BASE | {"prior_bachelors": True}, PROGRAM, UNIVERSITY, CATALOG)
    g = groups_of(got)
    assert all(g[x["id"]]["status"] == "waived" for x in UNIVERSITY["groups"])
    assert g["core_cs"]["status"] == "remaining" and any("Prior bachelor's degree" in w for w in got["warnings"])


def test_forgiveness_only_for_repeats_from_fall_2017():
    # p.2406: forgiveness "went into effect at the end of fall 2017 and does not apply retroactively"
    from gatorpath.engine.rules import forgiven
    old = [{"code": "CSC 220", "grade": "F", "term": "2015-fall"}, {"code": "CSC 220", "grade": "A", "term": "2016-spring"}]
    new = [{"code": "CSC 220", "grade": "F", "term": "2018-fall"}, {"code": "CSC 220", "grade": "A", "term": "2019-spring"}]
    assert forgiven(old, UNIVERSITY["repeats"], CATALOG) == set()
    assert forgiven(new, UNIVERSITY["repeats"], CATALOG) == {id(new[0])}


def test_nine_residence_units_in_upper_division_ge():
    # p.2391: "Nine of these residence units must be earned in the Upper Division portion of the General Education program"
    sfsu = audit(BASE | {"completed": [{"code": "HIST 470", "grade": "A", "term": "2026-fall"}]}, PROGRAM, UNIVERSITY, CATALOG)
    assert sfsu["totals"]["residence_upper_division_ge_units"] == {"value": 3.0, "needed": 9, "ok": False}
    transfer = audit(BASE | {"transfer_units": 60, "ge_done": ["3UD", "4UD", "5UD"]}, PROGRAM, UNIVERSITY, CATALOG)
    assert transfer["totals"]["residence_upper_division_ge_units"]["value"] == 0  # transfer UD GE isn't residence


def test_temporary_grades_must_be_replaced_before_graduation():
    # p.2405: "All temporary grades, including those of I ..., RD ..., and RP ... must all be changed to appropriate final grades"
    got = audit(BASE | {"completed": [{"code": "CSC 220", "grade": "I", "term": "2026-fall"}]}, PROGRAM, UNIVERSITY, CATALOG)
    assert any(w.startswith("CSC 220: temporary grade") for w in got["warnings"])


def test_exam_and_extension_credit_carry_no_residence():
    # p.2391: "Units earned for courses awarding extension credit or credit by examination or evaluation do not carry
    # residence credit"
    rows = [{"code": "CSC 220", "grade": "A", "term": "2026-fall"}, {"code": "CSC 230", "grade": "CR", "credit": "exam"}]
    t = audit(BASE | {"completed": rows}, PROGRAM, UNIVERSITY, CATALOG)["totals"]
    assert t["units"]["value"] == 6 and t["residence_units"]["value"] == 3


def test_ge_filter_level_and_waiver_text():
    from gatorpath.engine.rules import matches
    area4_ush = {"ge_area_all": ["4", "USH"], "level": "lower"}
    assert matches(area4_ush, "AA S 210", CATALOG["AA S 210"])
    fake_ud = CATALOG["AA S 210"] | {"ge_areas": ["4", "USH"]}
    assert not matches(area4_ush, "AA S 410", fake_ud)  # same tags, but numbered 410: not lower division
    adt = groups_of(audit(BASE | {"adt": True, "transfer_units": 60}, PROGRAM, UNIVERSITY, CATALOG))
    assert adt["sfss_sj"]["status"] == "waived" and "similar approved major" in adt["sfss_sj"]["waived_by"]
