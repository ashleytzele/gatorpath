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
    got = audit(case["profile"], *load_rules("2026-27", case["profile"]["program"]), CATALOG)
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


YEARS = sorted(p.stem for p in (RULES_DIR / "university").glob("*.yaml"))  # every catalog year with rules
PROGRAMS = [(y, p.stem) for y in YEARS for p in sorted((RULES_DIR / "programs" / y).glob("*.yaml"))]


@pytest.mark.parametrize("year,name", PROGRAMS)
def test_every_rule_group_cites_a_page(year, name):
    program, university = load_rules(year, name)
    assert program["catalog_year"] == university["catalog_year"] == year and program["program"] == name
    for g in program["groups"] + university["groups"]:
        assert re.fullmatch(r"p\.\d{1,4}.*", g["source"]), g["id"]


@pytest.mark.parametrize("year", YEARS)
def test_major_units_add_up_to_74(year):
    program = load_rules(year, "bs-cs")[0]
    required = sum(CATALOG[c]["units_min"] for g in program["groups"] for c in g.get("all_of", []))
    electives = next(g for g in program["groups"] if g["id"] == "senior_electives")["choose_units"]
    assert required + electives == program["total_units"] == 74


# GE minimum per year: 43 (2025-26 on); 48 in 2024-25 (p.2259): A 9 + B 9 + C 9 + D 6 + E 3 + F 3 + UD 9, where ge_c
# holds C1+C2, ge_d holds D2, and the "B3: 0-1 units" lab (p.2260) is on top
GE_MIN = {"2024-25": (48, {"ge_c1", "ge_c2", "ge_d2", "ge_b3"}), "2025-26": (43, set()), "2026-27": (43, set())}


@pytest.mark.parametrize("year", YEARS)
def test_ge_area_minimums_add_up(year):
    university = load_rules(year, "bs-cs")[1]
    want, inside = GE_MIN[year]
    assert sum(g.get("choose_units", 0) for g in university["groups"] if g["id"].startswith("ge_") and g["id"] not in inside) == want


ROADMAPS = {(y, n): yaml.safe_load((RULES_DIR / f"roadmaps/{y}/{n}.yaml").read_text()) for y, n in PROGRAMS}


@pytest.mark.parametrize("key,variant", [(k, v) for k, r in ROADMAPS.items() for v in r["variants"]])
def test_roadmap_semesters_add_up_to_printed_units(key, variant):
    v = ROADMAPS[key]["variants"][variant]
    for i, sem in enumerate(v["semesters"], 1):  # a variable-unit course (AIS 694, 1-3) may be printed above its minimum
        add = lambda end: sum(CATALOG[x].get(end, CATALOG[x]["units_min"]) if isinstance(x, str) else x["units"]
                              for x in sem["items"])
        assert add("units_min") <= sem["units"] <= add("units_max"), f"{variant} semester {i}"
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
    assert any(w.startswith("CSC 317: transfer credit counted as upper division") for w in got["warnings"])  # p.2304


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
    # Test user 1 (2026-10-20): a DPR with Area 4 done and US History needed read as US History met
    area_4 = audit(BASE | {"ge_done": ["4"]}, PROGRAM, UNIVERSITY, CATALOG)
    assert groups_of(area_4)["ai_ush"]["status"] == "remaining"
    exam = audit(BASE | {"ge_done": ["USH"]}, PROGRAM, UNIVERSITY, CATALOG)  # AP U.S. History (p.2350)
    assert groups_of(exam)["ai_ush"]["status"] == "satisfied"


def test_cal_getc_certification_meets_lower_division_ge():
    # p.2304: CCCs "can certify up to 34 semester ... units of ... (Cal-GETC) ... to fulfill lower-division general education"
    ld = UNIVERSITY["transfer"]["certified_ld_ge"]
    assert sum(g["choose_units"] for g in UNIVERSITY["groups"] if g["id"] in ld) == UNIVERSITY["transfer"]["certified_units"] == 34
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


def test_cr_nc_only_major_courses_are_outside_the_cr_cap():
    # p.2313: "Major courses only offered as CR/NC are not included in the 24 unit maximum"
    seminar = PROGRAM | {"global": {}, "groups": [{"id": "seminar", "all_of": ["CSC 601"], "source": "p.0"}]}
    rows = [{"code": "CSC 601", "grade": "CR", "term": "2026-fall"}, {"code": "CSC 602", "grade": "CR", "term": "2026-fall"}]
    got = audit(BASE | {"completed": rows}, seminar, UNIVERSITY, CATALOG)
    assert got["totals"]["cr_units"]["value"] == 2  # CSC 602 (CR/NC-only, not in this major) still counts


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


def test_open_ge_areas_name_the_major_courses_still_ahead_that_carry_them():
    # Trial 9: the model guessed AA S 210 might meet GE 6 and recalled PHYS 220 = 5A from memory. Major courses count for
    # GE too (p.2352), so the audit names them: PHYS 220 (5A), PHYS 222 (5C), CSC 300GW (GWAR); nothing for GE 6
    p03 = yaml.safe_load((ROOT / "evals/profiles/p03-sophomore-qr34.yaml").read_text())["profile"]
    groups = {g["id"]: g for g in audit(p03, PROGRAM, UNIVERSITY, CATALOG)["groups"]}
    assert (groups["ge_5a"]["major_courses"], groups["ge_5c"]["major_courses"]) == (["PHYS 220"], ["PHYS 222"])
    assert groups["gwar"]["major_courses"] == ["CSC 300GW"]
    assert "major_courses" not in groups["ge_6"] and "major_courses" not in groups["ge_1a"]  # none; ge_1a is satisfied


def test_min_grade_can_name_courses():
    # 2025-26 BS CS (p.1905): "Grades of C or better are required for CSC 510 and CSC 648." CSC 415 with a D counts
    program = PROGRAM | {"groups": [g | {"min_grade": {"CSC 510": "C", "CSC 648": "C"}} if g["id"] == "advanced_cs" else g
                                    for g in PROGRAM["groups"]]}
    rows = [{"code": c, "grade": "D", "term": "2026-fall"} for c in ("CSC 415", "CSC 510")] + \
           [{"code": "CSC 648", "grade": "C", "term": "2026-fall"}]
    got = audit(BASE | {"completed": rows}, program, UNIVERSITY, CATALOG)
    adv = groups_of(got)["advanced_cs"]
    assert adv["counted"] == ["CSC 415", "CSC 648"] and adv["remaining"] == ["CSC 510"]
    assert any(w.startswith("CSC 510: grade D doesn't count toward Advanced") and "needs C or better" in w for w in got["warnings"])


def test_amendments_change_a_group_after_publication():
    # §6.2: a change after the Bulletin was published, applied on top of the group and cited in the audit (DPR wording,
    # 2024-25: "Area E: Requirement waived 3/12/25 to align with Fall 2025 CSU GE ... via Dean's Memo")
    memo = "Dean's memo 3/12/25 (quoted on DPRs)"
    university = UNIVERSITY | {"groups": [
        g | {"amendments": [{"effective": "2025-03-12", "change": {"waived": True}, "source": memo}]} if g["id"] == "ge_3a"
        else g | {"amendments": [{"effective": "2025-03-12", "change": {"choose_units": 3}, "source": memo}]} if g["id"] == "ge_4"
        else g for g in UNIVERSITY["groups"]]}
    one = [{"code": "ECON 101", "grade": "B", "term": "2026-fall"}]
    got = groups_of(audit(BASE | {"completed": one}, PROGRAM, university, CATALOG))
    assert (got["ge_3a"]["status"], got["ge_3a"]["waived_by"]) == ("waived", memo)
    assert got["ge_4"]["status"] == "satisfied" and got["ge_4"]["amended_by"] == [memo]  # 3 units now, not 6


def test_a_legacy_ge_code_can_stand_for_two_areas():
    # 2024-25 "D2: Social Sciences: US History" (p.2259) is Area 4 with USH in the newest course tags
    from gatorpath.engine.rules import translate_ge
    university = UNIVERSITY | {"legacy_ge_areas": UNIVERSITY["legacy_ge_areas"] | {"map": {"D2": ["4", "USH"], "A2": "1A"}}}
    assert translate_ge(["Area D2 - Social Sciences: US History", "A2"], university)[0] == ["4", "USH", "1A"]


def test_a_select_one_plans_the_option_still_open():
    # BS Applied Mathematics p.2129: "Select One: MATH 209, CSC 101 & CSC 215, or CSC 309", C or better, no CR/NC
    program, university = load_rules("2026-27", "bs-applied-math")
    group = lambda rows, prog=(): next(g for g in audit({"catalog_year": "2026-27", "completed": rows, "in_progress": list(prog)},
                                                        program, university, CATALOG)["groups"] if g["id"] == "programming")
    assert group([])["remaining"] == ["MATH 209"]  # the fewest units, first printed
    started = group([{"code": "CSC 101", "grade": "A", "term": "2026-fall"}])
    assert started["status"] == "remaining" and started["counted"] == ["CSC 101"] and started["remaining"] == ["CSC 215"]
    assert group([{"code": "CSC 101", "grade": "A", "term": "2026-fall"}], ["CSC 215"])["status"] == "in_progress"
    # MATH 209 with CR doesn't count and can't be retaken (p.2392): plan CSC 309, the other 3-unit option
    cr = group([{"code": "MATH 209", "grade": "CR", "term": "2026-fall"}])
    assert cr["remaining"] == ["CSC 309"] and {"courses": ["MATH 209"], "left": ["MATH 209"]} in cr["options"]
    assert group([{"code": "CSC 309", "grade": "B", "term": "2026-fall"}])["status"] == "satisfied"


def test_an_unparsed_group_is_reported_never_guessed():
    # A drafted rule the vocabulary can't express (BA Asian American Studies p.437): unchecked, quoted, never complete
    program, university = load_rules("2026-27", "bs-applied-math")
    odd = {"id": "cr_nc_limit", "unparsed": True, "source": "p.437",
           "quote": "No more than 9 units can be taken with CR/NC grading."}
    got = audit({"catalog_year": "2026-27", "completed": []}, program | {"groups": program["groups"] + [odd]},
                university, CATALOG)
    group = next(g for g in got["groups"] if g["id"] == "cr_nc_limit")
    assert group["status"] == "unparsed" and group["quote"] == odd["quote"] and not got["complete"]
    assert any("can't check" in w and odd["quote"] in w for w in got["warnings"])


def test_a_select_one_claims_its_course_before_an_elective_list_does():
    # BA Art History (p.911): its ARTH electives list names ART 671, which is also an option of a later Select One; listed
    # first, the electives took it and left the Select One uncovered. Applied Math stands in: MATH 209 in both.
    program, university = load_rules("2026-27", "bs-applied-math")
    extra = {"id": "extra", "choose_units": 3, "from": {"list": ["MATH 209", "MATH 430"]}, "source": "p.2129"}
    got = audit({"catalog_year": "2026-27", "completed": [{"code": "MATH 209", "grade": "A", "term": "2026-fall"}]},
                program | {"groups": [extra] + program["groups"]}, university, CATALOG)
    status = {g["id"]: g for g in got["groups"]}
    assert status["programming"]["status"] == "satisfied" and status["extra"]["counted"] == []
    assert [g["id"] for g in got["groups"]][:2] == ["extra", "required"]  # still in the rules' order



def test_two_select_ones_sharing_a_course_plan_different_options():
    # BS Environmental Science: NRM&C (pp.2065-2066): GEOG 604 is in the Statistics core's Select One and in Tools and
    # Techniques'; both planned it, the plan took it once, and no course counts twice, so Tools was left uncovered.
    # Applied Math stands in: an earlier Select One that also offers MATH 209
    program, university = load_rules("2026-27", "bs-applied-math")
    stats = {"id": "stats", "one_of": [["MATH 209"], ["MATH 430"]], "source": "p.2129"}
    got = {g["id"]: g for g in audit({"catalog_year": "2026-27", "completed": []},
                                     program | {"groups": [stats] + program["groups"]}, university, CATALOG)["groups"]}
    assert got["stats"]["remaining"] == ["MATH 209"] and got["programming"]["remaining"] == ["CSC 309"]

def test_electives_fill_to_the_programs_total():
    # BA General Biology p.1785: "as many units as needed to reach a total of 58 units in the program". Applied Math (55)
    # stands in: its 6 units of major electives as a fill_to_total group with a minimum of 0
    program, university = load_rules("2026-27", "bs-applied-math")
    fill = [g | {"choose_units": 0, "fill_to_total": True} if g["id"] == "major_electives" else g for g in program["groups"]]
    need = lambda rows: next(g for g in audit({"catalog_year": "2026-27", "completed": rows}, program | {"groups": fill},
                                              university, CATALOG)["groups"] if g["id"] == "major_electives")["units_needed"]
    assert need([]) == 6  # MATH 209 (3) for the Select One, as the audit plans it
    bundle = [{"code": c, "grade": "A", "term": "2026-fall"} for c in ("CSC 101", "CSC 215")]
    assert need(bundle) == 6 - 4  # CSC 101 & CSC 215 (7 units) instead: 4 fewer elective units
    low = next(g for g in audit({"catalog_year": "2026-27", "completed": []}, program | {"groups": fill, "total_units": 40},
                                university, CATALOG)["groups"] if g["id"] == "major_electives")
    assert low["units_needed"] == 0 and low["status"] == "satisfied"  # nothing left to fill: met, not an error


def test_program_files_pass_check_program():
    # ARCHITECTURE §6.2 "AI-drafted rules": the hand-written programs are the bar a draft is held to
    from gatorpath.engine.rules import check_program
    from gatorpath.ingest.programs import LOADABLE, source_pages
    for path in sorted((RULES_DIR / "programs/2026-27").glob("*.yaml")):
        source = path.with_suffix(".source.txt").read_text()
        program = yaml.safe_load(path.read_text())
        got = check_program(program, CATALOG, source_pages(source), source, UNIVERSITY)
        if program.get("drafted_by"):  # a loaded draft may still carry requirements flagged for a person (--load)
            got = [x for x in got if not any(k in x for k in LOADABLE)]
        assert got == [], path.name


def test_check_program_reports_what_a_person_must_fix():
    from gatorpath.engine.rules import check_program
    source = (RULES_DIR / "programs/2026-27/bs-applied-math.source.txt").read_text()
    good = yaml.safe_load((RULES_DIR / "programs/2026-27/bs-applied-math.yaml").read_text())
    theory = {"id": "theory", "choose_units": 3, "from": {"list": ["MATH 335", "MATH 370", "MATH 380"]}, "source": "p.2129",
              "quote": "Select One: 3 MATH 335 Modern Algebra"}
    assert check_program(good | {"groups": [g if g["id"] != "theory" else theory for g in good["groups"]]},
                         CATALOG, {2129, 2130, 2131}, source) == []  # the quote survives pdftotext's line breaks
    bad = good | {"groups": [
        {"id": "required", "all_of": ["MATH 226", "MATH 999"], "min_grade": "C+-", "source": "p.2200", "level": 3},
        {"id": "required", "choose_units": 6, "source": "p.2129", "quote": "Select six units of anything"},
        {"id": "odd", "unparsed": True, "source": "p.2130", "quote": "A coherent collection of three courses"},
    ]}
    got = check_program(bad, CATALOG, {2129, 2130, 2131}, source)
    assert got == ["required: unknown key 'level'", "required: MATH 999 is not in the 2026-27 catalog",
                   "required: min_grade 'C+-' isn't a grade",
                   "required: source p.2200 is outside the program's pages (2129-2131)",
                   "required: duplicate id", "required: a choose group needs `from`",
                   "required: quote isn't word for word in the Bulletin text: 'Select six units of anything'",
                   "odd: unparsed, a person writes this requirement from its quote",
                   "units: can't check total_units with choose_n or unparsed groups (the others add up to 10 of 55); "
                   "a person adds them up"]
    # approval text is shown to students as the Bulletin's words too: a paraphrase is flagged
    reworded = good | {"groups": [g | {"approval": "Get your advisor to pick three courses."} if g["id"] == "application_electives"
                                  else g for g in good["groups"]]}
    assert "application_electives: approval isn't word for word in the Bulletin text: 'Get your advisor to pick three " \
           "courses.'" in check_program(reworded, CATALOG, {2129, 2130, 2131}, source)
    short = good | {"total_units": 56}
    assert check_program(short, CATALOG)[-1] == "units: the groups' minimums add up to 55, total_units says 56"
    # a variable-unit course (KIN 699 Independent Study, 1-3 in "Select one: 3", p.710) can reach the printed total
    variable = CATALOG | {"MATH 696": CATALOG["MATH 696"] | {"units_max": CATALOG["MATH 696"]["units_min"] + 1}}
    assert check_program(short, variable) == [] and check_program(good | {"total_units": 57}, variable)[-1] == \
        "units: the groups' minimums add up to 55 (56 with variable-unit courses at their most), total_units says 57"
    # MUS 130/TH A 131 (BM Composition, p.1549) is one course: both codes in an all_of would need it twice
    twins = CATALOG | {"MUS 130": {"units_min": 3, "crosslisted": ["TH A 131"]},
                       "TH A 131": {"units_min": 3, "crosslisted": ["MUS 130"]}}
    theory = {"id": "theory", "all_of": ["MUS 130", "TH A 131"], "source": "p.2129"}
    assert "theory: MUS 130 and TH A 131 are one cross-listed course, so all_of needs it twice; make it its own one_of " \
           "group [[MUS 130], [TH A 131]]" in check_program(good | {"groups": [theory]}, twins)
    # BA Chemistry's major "gwar" (CHEM 390GW) shared the university GWAR's id: the audit reported the university's
    # result for it, so CHEM 390GW at CR, or another GWAR course, looked done (found by ingest.programs --cross)
    clash = good | {"groups": good["groups"] + [{"id": "gwar", "all_of": ["MATH 301GW"], "source": "p.2129"}]}
    assert "gwar: the university rules use this id too (their result would stand for this group); name it for the major, " \
           "e.g. major_gwar" in check_program(clash, CATALOG, university=UNIVERSITY)
    # BA Women and Gender Studies' "elective" (3 upper-division units) shared the planner's free-elective slot name: its
    # slot merged into the free electives and lost its upper-division units, so the plan ended 3 short
    free = good | {"groups": good["groups"] + [{"id": "elective", "choose_units": 3, "from": {"list": ["MATH 430"]},
                                                "source": "p.2129"}]}
    assert "elective: the planner names its free-elective slots this; name it for the major, e.g. major_elective" \
        in check_program(free, CATALOG)
    early = good | {"groups": [g | {"source": "p.152"} for g in good["groups"]]}  # a page under 1000
    assert check_program(early, CATALOG, {152}) == []


def test_check_groups_read_the_courses_other_groups_count():
    # §6.2 check groups, from real Bulletin rules: "Courses fulfilling the ... core requirement may not be taken on a CR/NC
    # basis" (p.1322), "no more than 6 units of the core may be completed on a CR/NC basis" (p.53), "No more than one
    # course counted toward major requirements may be completed with a grade less than a C-" (p.2027), "a minimum grade
    # point average of 2.0 in all Core Requirement Business courses" (p.53), "At least 12 units in biology must be
    # completed at SF State" (p.1784). Applied Math's required courses stand in for the core.
    program, university = load_rules("2026-27", "bs-applied-math")
    checks = [
        {"id": "letters", "across": ["required"], "letter_grade": True, "source": "p.1322"},
        {"id": "cr_cap", "across": ["required"], "max_cr": {"units": 8, "except_exam": True}, "source": "p.53"},
        {"id": "low", "across": "major", "max_below": {"grade": "C-", "courses": 1}, "source": "p.2027"},
        {"id": "gpa", "across": ["required"], "min_gpa": 2.0, "source": "p.53"},
        {"id": "here", "across": "major", "min_units_from": {"subject": "MATH", "level": "upper", "units": 12, "sf_state": True},
         "source": "p.1784"},
        {"id": "cap", "across": "major", "max_units_from": {"list": ["MATH 226", "MATH 227"], "units": 4}, "source": "p.437"},
        {"id": "two", "across": ["required"], "distinct_subjects": 2, "source": "p.1264"},
        {"id": "upper2", "across": ["required"], "min_units_from": {"level": "upper", "courses": 2}, "source": "p.1013"},
        {"id": "lower1", "across": ["required"], "max_units_from": {"level": "lower", "courses": 1}, "source": "p.1278"},
        {"id": "moved", "across": "major", "max_units_from": {"subject": "MATH", "units": 6, "transfer": True}, "source": "p.476"},
        {"id": "fields", "across": ["required"], "min_categories": 3, "source": "p.1640",
         "categories": [["MATH 226", "MATH 227"], ["MATH 227"], ["MATH 440", "MATH 460"]]},  # MATH 227 counts once
        {"id": "area", "across": ["required"], "one_category": True, "source": "p.402",
         "categories": [["MATH 226", "MATH 227", "MATH 325"], ["MATH 440", "MATH 460"]]},
    ]
    only_cr = CATALOG | {"MATH 228": CATALOG["MATH 228"] | {"grading": "cr_nc"}}
    plain = [{k: v for k, v in g.items() if k != "min_grade"} for g in program["groups"]]

    def run(rows, catalog=CATALOG):
        got = audit({"catalog_year": "2026-27", "completed": [{"term": "2026-fall"} | r for r in rows]},
                    program | {"groups": checks + plain, "global": {}}, university, catalog)  # CR may count
        return {g["id"]: g for g in got["groups"]}, got["warnings"]

    status, _ = run([])
    assert [status[i]["status"] for i in ("letters", "cr_cap", "low", "gpa", "here")] == ["in_progress"] * 4 + ["remaining"]
    assert status["low"]["across"] == ["required", "programming", "theory", "major_electives", "application_electives"]
    status, warnings = run([{"code": "MATH 226", "grade": "CR"}, {"code": "MATH 227", "grade": "CR", "credit": "exam"},
                            {"code": "MATH 228", "grade": "CR"}], only_cr)
    assert status["letters"]["status"] == "remaining"  # MATH 228 is CR/NC-only: only MATH 226 and the exam break it
    assert "letters: MATH 226, MATH 227: CR, but these courses must be taken for a letter grade (p.1322)" in warnings
    assert status["cr_cap"]["status"] == "in_progress"  # 12 CR units, but the 4 by exam are outside the cap: 8 <= 8
    status, warnings = run([{"code": c, "grade": "D"} for c in ("MATH 226", "MATH 227")]
                           + [{"code": c, "grade": "A", "transfer": True} for c in ("MATH 325", "MATH 376", "MATH 400")]
                           + [{"code": c, "grade": "B"} for c in ("MATH 440", "MATH 460")])
    assert status["low"]["status"] == status["gpa"]["status"] == "remaining" and status["gpa"]["gpa"] == 1.857  # D, D, B, B (4, 4, 3, 3 units)
    assert "low: MATH 226, MATH 227: below C-, at most 1 course(s) may be (p.2027)" in warnings
    assert status["here"]["min_units_from"]["done"] == 6  # the transfer courses aren't SF State units
    assert status["here"]["status"] == "remaining"
    assert status["cap"]["status"] == "remaining" and "cap: MATH 226, MATH 227: 8 units, at most 4 count (p.437)" in warnings
    assert status["two"]["status"] == "remaining" and status["two"]["subjects"] == ["MATH"]
    assert status["upper2"]["status"] == "satisfied" and status["upper2"]["min_units_from"]["done"] == 5  # courses, not units
    assert status["moved"]["status"] == "remaining"  # 9 transfer units (MATH 325, 376, 400): at most 6
    assert status["fields"]["status"] == "satisfied" and status["fields"]["categories_met"] == 3  # 226, 227, 440
    assert status["area"]["status"] == "remaining" and any(w.startswith("area: MATH 226, MATH 227,") for w in warnings)
    assert status["lower1"]["status"] == "remaining" and "lower1: MATH 226, MATH 227: 2 courses, at most 1 count (p.1278)" in warnings


def test_a_filter_caps_units_and_takes_a_division():
    # BA Sociology p.851: "Upper-division SOC courses ... Up to 9 units of lower-division sociology courses"
    program, university = load_rules("2026-27", "bs-applied-math")
    electives = {"id": "electives", "choose_units": 12, "source": "p.851",
                 "from": [{"subject": "MATH", "level": "upper"}, {"subject": "MATH", "level": "lower", "max_units": 4}]}
    rows = [{"code": c, "grade": "A", "term": "2026-fall"} for c in ("MATH 226", "MATH 227", "MATH 430", "MATH 442")]
    got = audit({"catalog_year": "2026-27", "completed": rows}, program | {"groups": [electives]}, university, CATALOG)
    g = next(g for g in got["groups"] if g["id"] == "electives")
    assert g["counted"] == ["MATH 226", "MATH 430", "MATH 442"] and g["units_done"] == 10  # one 4-unit lower-division
    assert not matches({"level": "upper"}, "MATH 226", CATALOG["MATH 226"]) and matches({"level": "upper"}, "MATH 430", CATALOG["MATH 430"])
    assert matches({"level": [400, 600]}, "MATH 430", CATALOG["MATH 430"]) and not matches({"level": [500, 600]}, "MATH 430", CATALOG["MATH 430"])
    approved = electives | {"from": [{"approved": True, "level": "upper"}, {"approved": True, "level": "lower", "max_units": 4}]}
    got = audit({"catalog_year": "2026-27", "completed": rows, "approved": {"electives": [r["code"] for r in rows]}},
                program | {"groups": [approved]}, university, CATALOG)  # BA American Studies p.1264: a level on approved
    assert next(g for g in got["groups"] if g["id"] == "electives")["counted"] == ["MATH 226", "MATH 430", "MATH 442"]
    mins = program["groups"][:1] + [electives | {"min_units_from": {"level": "upper", "units": 9}}]
    got = audit({"catalog_year": "2026-27", "completed": rows}, program | {"groups": mins}, university, CATALOG)
    assert next(g for g in got["groups"] if g["id"] == "electives")["min_units_from"]["done"] == 6


def test_check_program_reads_check_groups():
    from gatorpath.engine.rules import check_program
    good = yaml.safe_load((RULES_DIR / "programs/2026-27/bs-applied-math.yaml").read_text())
    ok = [{"id": "gpa", "across": ["required", "theory"], "min_gpa": 2.0, "source": "p.2129"},
          {"id": "ud", "across": "major", "min_units_from": {"level": "upper", "units": 30}, "source": "p.2129"}]
    assert check_program(good | {"groups": good["groups"] + ok}, CATALOG) == []
    bad = [{"id": "two", "across": ["required"], "min_gpa": 2.0, "letter_grade": True, "source": "p.2129"},
           {"id": "where", "across": ["nowhere"], "max_cr": {"units": 6, "courses": 1}, "source": "p.2129"},
           {"id": "low", "across": "major", "max_below": {"grade": "Z"}, "except": ["MATH 999"], "source": "p.2129"},
           {"id": "any", "choose_units": 0, "from": {"max_units": 3}, "min_units_from": {"subject": "MATH"}, "source": "p.2129"}]
    assert check_program(good | {"groups": good["groups"] + bad}, CATALOG) == [
        "two: a check group needs exactly one of letter_grade, max_cr, max_below, min_gpa, min_units_from, max_units_from, "
        "distinct_subjects, min_categories, one_category (has letter_grade, min_gpa)",
        "where: across must be `major` or ids of this program's course groups (has ['nowhere'])",
        "where: max_cr needs units or courses",
        "low: max_below needs a grade and courses", "low: MATH 999 is not in the 2026-27 catalog",
        "any: min_units_from needs units",
        "any: a filter needs one of list, subject, level, ge_area, ge_area_all, approved"]
