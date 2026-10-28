"""MCP tools over a small catalog.db built from real 2026-27 Bulletin rows (tests/fixtures/catalog_rows.json), so CI
runs without the PDF. The rows are every course in evals/catalog-2026-27.json plus the CSC 653 prereq chain."""

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from gatorpath import server
from gatorpath.engine.planner import term_key
from gatorpath.engine.rules import audit, load_rules
from gatorpath.ingest.bulletin import write_catalog

ROOT = Path(__file__).parents[1]
ROWS = json.loads((ROOT / "tests/fixtures/catalog_rows.json").read_text())
TRANSCRIPT = (ROOT / "tests/fixtures/transcript_synthetic.txt").read_text()
DPR = (ROOT / "tests/fixtures/dpr_synthetic.txt").read_text()
REAL_DB = ROOT / "data/catalog.db"


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "catalog.db"
    write_catalog(db, "2026-27", ROWS)
    return db


@pytest.fixture(autouse=True)
def use_fixture_db(fixture_db, monkeypatch):
    monkeypatch.setattr(server, "DB", fixture_db)


def test_prereq_chain_csc_653():
    got = server.get_prereq_chain("csc653")
    assert got["catalog_year"] == "2026-27"
    # "Upper-division standing; CSC 415* with a grade of C or better; GPA of 3.0 or better; or permission of the instructor."
    assert got["requires"] == {"any": [{"all": [{"standing": "upper"}, {"course": "CSC 415", "min_grade": "C"}, {"gpa": 3.0}]},
                                       {"permission": "instructor"}]}
    order = [e["code"] for e in got["chain"]]
    assert order[-1] == "CSC 653" and len(order) == len(set(order))
    for want in ("CSC 415", "CSC 340", "CSC 256", "MATH 324", "PHYS 230", "CSC 101"):
        assert want in order
    for before, after in [("CSC 415", "CSC 653"), ("CSC 340", "CSC 415"), ("CSC 220", "CSC 340"), ("CSC 101", "CSC 215")]:
        assert order.index(before) < order.index(after)
    assert {"for": "CSC 653", "permission": "instructor", "verifiable": False} in got["conditions"]
    assert {"for": "CSC 653", "gpa": 3.0, "verifiable": True} in got["conditions"]
    w = "\n".join(got["warnings"])
    assert "CSC 210 (needed by" in w and "renumbered" in w   # CSC 220/230 still name the old CSC 210
    assert "'*'" not in w and "cycle" not in w  # '*' = enforced at registration (p.2436); PHYS 220/222 are corequisites


def test_get_course_record():
    got = server.get_course(" csc 671 ")
    assert (got["code"], got["title"], got["source_page"]) == ("CSC 671", "Deep Learning", 1900)
    assert got["links"] == [{"code": "CSC 871", "kind": "paired"}]
    assert got["prereq"]["status"] == "ok" and got["prereq"]["needs_permission"] is True
    assert got["offered_terms"] == "unknown" and any("isn't loaded" in w for w in got["warnings"])


def test_unknown_course_suggests_nearest_numbers():
    got = server.get_course("CSC 210")
    assert got["error"] == "unknown_course"
    assert got["close_matches"][:2] == ["CSC 215", "CSC 220"]
    assert server.get_prereq_chain("CSC 210")["error"] == "unknown_course"


def test_search_courses():
    got = server.search_courses("network security", subject="csc", level="upper")
    assert got["results"][0]["code"] == "CSC 653"
    assert all(300 <= int(r["code"][4:7]) < 700 for r in got["results"])  # graduate CSC 853 filtered out
    assert server.search_courses("csc 300gw")["results"][0]["code"] == "CSC 300GW"
    assert server.search_courses("network security", level="800")["results"][0]["code"] == "CSC 853"
    assert server.search_courses("x", level="senior")["error"] == "bad_level"
    assert server.search_courses("?!")["results"] == []


def test_programs_and_roadmap():
    listed = {p["id"]: p for p in server.list_programs()["programs"]}
    assert listed["bs-cs"] == {"id": "bs-cs", "title": "Bachelor of Science in Computer Science", "verified": False,
                               "drafted": False}
    assert listed["bs-applied-math"]["drafted"] is False and listed["bs-public-health"]["drafted"] is True
    req = server.get_program_requirements("bs-cs")
    assert [g["id"] for g in req["program"]["groups"]][:2] == ["math_physics", "core_cs"]
    assert any("not verified" in w for w in req["warnings"])
    assert server.get_program_requirements("../university/2026-27")["error"] == "unknown_program"
    assert set(server.get_roadmap("bs-cs")["variants"]) == {"qr-1-2", "qr-3-4", "adt"}
    rm = server.get_roadmap("bs-cs", "qr-1-2")
    assert rm["semesters"][0]["items"][0] == "CSC 101" and rm["source"] == "p.1908-1909"
    assert set(server.get_roadmap("bs-applied-math")["variants"]) == {"qr-1-2", "qr-3-4", "adt"}


@pytest.mark.parametrize("path", sorted((ROOT / "evals/profiles").glob("*.yaml")), ids=lambda p: p.stem)
def test_audit_progress_matches_engine(path):
    profile = yaml.safe_load(path.read_text())["profile"]
    want = audit(profile, *load_rules("2026-27", profile["program"]), json.loads((ROOT / "evals/catalog-2026-27.json").read_text()))
    # sloppy client input: lower case, no spaces ('aas210' -> 'AA S 210')
    sloppy = profile | {"completed": [r | {"code": r["code"].lower().replace(" ", "")} for r in profile.get("completed", [])],
                        "in_progress": [c.lower() for c in profile.get("in_progress", [])]}
    got = server.audit_progress(sloppy)
    assert got["groups"] == want["groups"] and got["totals"] == want["totals"]
    assert got["warnings"][:len(want["warnings"])] == want["warnings"]


def test_audit_progress_warns_about_assumed_year_and_uncredited_transfer():
    got = server.audit_progress({"program": "bs-cs", "transfer_units": 46, "completed": [{"code": "CSC 215", "grade": "A"}]})
    assert "catalog_year not given" in got["warnings"][0]
    assert any("46 transfer units count toward the 120 only" in w for w in got["warnings"])
    with_year = server.audit_progress({"program": "bs-cs", "catalog_year": "2026-27", "transfer_units": 46, "ge_done": ["1A"]})
    assert not any("catalog_year not given" in w or "toward the 120 only" in w for w in with_year["warnings"])


def test_audit_progress_unknown_program_and_other_catalog_years():
    assert server.audit_progress({"program": "bs-art"})["error"] == "unknown_program"
    # a Spring 2024 student (no 2023-24 rules) is planned with the newest rules and told so, not turned away
    got = server.audit_progress({"program": "bs-cs", "catalog_year": "Spring 2024"})
    assert "error" not in got and got["warnings"][0].startswith("The student's catalog year is Spring 2024")


def test_a_dpr_shaped_profile():
    # Spring 2025 transfer student, as their DPR reads: old GE codes, transfer rows under requirements, MATH 325
    # listed under the MATH 225 requirement
    dpr = {"program": "bs-cs", "catalog_year": "Spring 2025", "transfer_units": 46, "gpa": 4.0,
           "ge_done": ["A1", "Area A2", "A3", "B1", "B2", "B3", "B4", "C1", "C2", "D", "E", "USH"],
           "dpr_met": ["math 225"],
           "completed": [{"code": "MATH 226", "grade": "C", "transfer": True}, {"code": "MATH 227", "grade": "C", "transfer": True},
                         {"code": "CSC 101", "grade": "C", "transfer": True}, {"code": "CSC 215", "grade": "A", "term": "2025-spring"}]}
    got = server.audit_progress(dpr)
    groups = {g["id"]: g for g in got["groups"]}
    assert groups["math_physics"]["met_per_dpr"] == ["MATH 225"] and "MATH 225" in groups["math_physics"]["counted"]
    # 2024-25 rules (the student's year): old areas, D + USH meets D2, the 3/12/25 memo waives E and the third C course
    assert got["catalog_year"] == "2024-25"
    for gid in ("ge_a1", "ge_a2", "ge_a3", "ge_b1", "ge_b2", "ge_b3", "ge_b4", "ge_c1", "ge_c2", "ge_d", "ge_d2"):
        assert groups[gid]["status"] == "satisfied", gid
    assert groups["ge_e"]["status"] == groups["ge_c"]["status"] == "waived" and "3/12/25" in groups["ge_e"]["waived_by"]
    w = "\n".join(got["warnings"])
    assert "A1 → 1C" in w and "UD" not in w.split("read as this Bulletin's areas")[1].split("(")[0]
    assert "MATH 225: counted for Mathematics and Physics" in w
    plan = server.build_plan(dpr)
    assert "MATH 225" not in {c for s in plan["semesters"] for c in s["courses"] if isinstance(c, str)}


@pytest.mark.skipif(not REAL_DB.exists(), reason="catalog.db not built (git-ignored)")
def test_codes_without_spaces_are_unique(monkeypatch):
    monkeypatch.setattr(server, "DB", REAL_DB)
    assert len(server.by_squashed(REAL_DB, "2026-27")) == len(server.prereqs(REAL_DB, "2026-27"))


@pytest.mark.skipif(not REAL_DB.exists(), reason="catalog.db not built (git-ignored)")
def test_fixture_rows_match_catalog_db():
    con = sqlite3.connect(REAL_DB)
    real = {r[0]: r[1:] for r in con.execute(
        "select c.code, title, description, source_page, raw_text from course c join prereq p using (catalog_year, code) "
        "where c.catalog_year = '2026-27'")}
    con.close()
    assert {r["code"]: (r["title"], r["description"], r["source_page"], r["prereq_text"]) for r in ROWS} == \
           {r["code"]: real[r["code"]] for r in ROWS}


def test_check_plan_tool():
    profile = yaml.safe_load((ROOT / "evals/profiles/p07-adt-transfer.yaml").read_text())["profile"]
    plan = {"semesters": [
        {"term": "2027-fall", "courses": ["csc648", "CSC 653", "CSC 665", {"slot": "ge_ud_sci", "units": 3},
                                          {"slot": "ge_4ud", "units": 3}]},
        {"term": "2028-spring", "courses": ["CSC 671", "CSC 620", {"slot": "senior_electives", "units": 3},
                                            {"slot": "elective", "units": 3}, {"slot": "elective", "units": 3}]},
        {"term": "2028-fall", "courses": [{"slot": "elective", "units": 3}]}]}
    got = server.check_plan(profile, plan)
    assert got["valid"], got["errors"]
    plan["semesters"][0]["courses"][0] = "CSC 999"
    bad = server.check_plan(profile, plan)
    assert not bad["valid"] and {"unknown_course", "requirement_not_covered"} <= {e["error"] for e in bad["errors"]}


def test_build_plan_tool():
    profile = yaml.safe_load((ROOT / "evals/profiles/p03-sophomore-qr34.yaml").read_text())["profile"]
    got = server.build_plan(profile)
    assert got["check"]["valid"], got["check"]["errors"]
    assert got["variant"] == "qr-3-4" and got["est_graduation_term"] == got["semesters"][-1]["term"]
    assert server.check_plan(profile, {"semesters": got["semesters"]})["valid"]
    assert server.build_plan(profile | {"qr_pathway": None})["needs_input"] == "qr_pathway"


TRANSFER_SENIOR = {"catalog_year": "2026-27", "program": "bs-cs", "transfer_units": 70, "gpa": 4.0,
                   "ge_done": ["1A", "1B", "1C", "2", "3A", "3B", "4", "5A", "5B", "5C", "6", "USH", "USG", "CSLG"],
                   "completed": [{"code": "AA S 213", "grade": "A", "term": "2026-fall"}]}



def test_sections_for_a_terms_courses(tmp_path, monkeypatch):
    # After a plan: the first term's sections, from Class Search (names and numbers invented, real cell layout)
    from gatorpath.ingest.offerings import write_offerings
    path = tmp_path / "catalog.db"
    write_catalog(path, "2026-27", ROWS)
    lec = {"term": "2027-spring", "code": "CSC 653", "section": "01", "component": "LEC", "mode": "In-Person",
           "enrolled": 0, "class_nbr": "4321", "meetings": [{"days": "Tu Th", "time": "9:30 AM - 10:45 AM",
                                                              "where": "Thornton Hall 329"}],
           "dates": None, "instructor": "Pat Example", "seats_open": 40, "waitlist_open": 5, "attributes": ["Upper-Division"]}
    tba = lec | {"section": "02", "class_nbr": "4322", "instructor": "To be announced"}
    both = lec | {"section": "03", "class_nbr": "4323", "instructor": "Pat Example, To be announced"}
    write_offerings(path, "2027-spring", "CSC", [lec, tba, both], "2026-10-26T21:00:00+00:00")
    monkeypatch.setattr(server, "DB", path)
    got = server.get_sections("2027-spring", ["csc653", "CSC 648", "MATH 226"])
    shown = lambda s: {k: v for k, v in s.items() if k not in ("term", "code", "dates")}
    # Each named instructor gets a Rate My Professors search link (SF State, school 880); "To be announced" doesn't
    rmp = {"rate_my_professors": {"Pat Example": "https://www.ratemyprofessors.com/search/professors/880?q=Pat%20Example"}}
    assert got["sections"] == {"CSC 653": [shown(lec) | rmp, shown(tba), shown(both) | rmp]}
    assert got["not_offered"] == ["CSC 648"] and got["unknown"] == ["MATH 226"]  # MATH wasn't scraped that term
    assert got["scraped_at"] == "2026-10-26T21:00:00+00:00" and any("Class Search" in w for w in got["warnings"])
    assert server.get_sections("2027-fall", ["CSC 653"])["unknown"] == ["CSC 653"]  # schedule not out
    assert server.get_sections("spring", ["CSC 653"])["error"] == "bad_term"

def test_eligible_electives_rank_triple_duty_courses_first():
    got = server.list_eligible_electives(TRANSFER_SENIOR, "ge_4ud", by_term="2027-spring")
    top = got["options"][:2]
    # ENVS 401 / LS 401: 4UD + Environmental Sustainability + Global Perspectives (SJ is already met by AA S 213)
    assert {o["code"] for o in top} == {"ENVS 401", "LS 401"}
    assert all(o["readiness"] == "ready" and set(o["also_covers"]) == {"sfss_esca", "sfss_gp"} for o in top)
    assert top[0]["description"]
    geog = next(o for o in got["options"] if o["code"] == "GEOG 575")
    assert geog["readiness"] == "check" and any("E" in w for w in geog["cannot_check"])  # "... 2/B4*, and E"
    assert server.list_eligible_electives(TRANSFER_SENIOR, "core_cs")["error"] == "not_a_choice"


def test_cybersecurity_electives_come_after_csc_415():
    profile = yaml.safe_load((ROOT / "evals/profiles/p03-sophomore-qr34.yaml").read_text())["profile"]
    plan = {"semesters": server.build_plan(profile)["semesters"]}
    t415 = next(s["term"] for s in plan["semesters"] if "CSC 415" in s["courses"])
    got = {o["code"]: o for o in server.list_eligible_electives(profile, "senior_electives", plan, t415, limit=100)["options"]}
    assert got["CSC 656"]["readiness"] == "ready"  # "CSC 415* (may be taken concurrently)"
    for c in ("CSC 652", "CSC 653"):
        assert got[c]["readiness"] == "blocked" and term_key(got[c]["ready_by"]) > term_key(t415)
    # Fill each slot the way the client does: from what list_eligible_electives says is ready in that slot's term,
    # cybersecurity first
    goal = ["CSC 652", "CSC 653", "CSC 656", "CSC 665", "CSC 620"]
    for s in plan["semesters"]:
        for i, c in enumerate(s["courses"]):
            if isinstance(c, dict) and c["slot"] == "senior_electives":
                ready = [o["code"] for o in server.list_eligible_electives(profile, "senior_electives", plan, s["term"],
                                                                           limit=200)["options"] if o["readiness"] == "ready"]
                s["courses"][i] = next((g for g in goal if g in ready), ready[0])
    checked = server.check_plan(profile, plan)
    assert checked["valid"], checked["errors"]
    term_of = {c: s["term"] for s in plan["semesters"] for c in s["courses"] if isinstance(c, str)}
    assert term_key(term_of["CSC 415"]) < min(term_key(term_of["CSC 652"]), term_key(term_of["CSC 653"]))


def test_get_course_unlocks():
    got = server.get_course("CSC 413")["unlocks"]
    assert {"CSC 620", "CSC 642", "CSC 648", "CSC 665", "CSC 675"} <= set(got)  # all "CSC 413* with a grade of C"
    assert server.get_course("CSC 653")["unlocks"] == []


def test_audit_progress_points_to_the_dpr_and_an_advisor():
    got = server.audit_progress({"program": "bs-cs", "catalog_year": "2026-27"})
    assert [a["role"] for a in got["see_advisor"]] == ["major_advisor", "dpr"]


def test_plan_my_degree_prompt_names_only_real_tools():
    import asyncio
    import re as regex

    text = server.plan_my_degree(goal="AI / machine learning", graduate_by="2029-spring")
    assert "The student's goal: AI / machine learning." in text and "graduate by 2029-spring" in text
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    fields = {"transfer", "ge_done", "transfer_units", "adt", "elective", "why", "see_advisor", "dpr_met", "offered", "last", "profile",
              "approval", "options"}  # data
    named = set(regex.findall(r"`([a-z_]+)`", text)) - fields
    assert named <= tools, named - tools
    assert {"audit_progress", "build_plan", "list_eligible_electives", "check_plan"} <= named
    prompts = asyncio.run(server.mcp.list_prompts())
    assert [p.name for p in prompts] == ["plan_my_degree"]


def test_not_on_dpr_leaves_a_requirement_out_and_sends_to_an_advisor():
    # An older transfer GE pattern on the newest rules (Spring 2024: no 2023-24 rules): the DPR has no Ethnic Studies
    profile = TRANSFER_SENIOR | {"catalog_year": "Spring 2024", "qr_pathway": "1/2",
                                 "ge_done": [a for a in TRANSFER_SENIOR["ge_done"] if a != "6"]}
    plan_with = server.build_plan(profile | {"start_term": "2027-spring"})
    slots = lambda p: {c["slot"] for s in p["semesters"] for c in s["courses"] if isinstance(c, dict)}
    assert "ge_6" in slots(plan_with)
    without = profile | {"start_term": "2027-spring", "not_on_dpr": ["Area 6"]}
    audit = {g["id"]: g for g in server.audit_progress(without)["groups"]}
    assert audit["ge_6"]["status"] == "waived" and audit["ge_6"]["waived_by"] == "not on the student's DPR"
    plan_without = server.build_plan(without)
    assert "ge_6" not in slots(plan_without) and plan_without["check"]["valid"]
    assert any(w.startswith("GE 6 Ethnic Studies: left out because the student's DPR doesn't list it")
               for w in plan_without["warnings"])
    uac = next(a for a in plan_without["see_advisor"] if a["role"] == "general_advising")
    assert "GE 6 Ethnic Studies isn't required for your catalog year" in uac["why"][0]


def test_program_requirements_include_transfer_notes():
    notes = server.get_program_requirements("bs-cs")["program"]["transfer_notes"]
    assert len(notes) >= 8 and all(n["source"].startswith("p.190") for n in notes)
    assert any("ASSIST" in n["text"] for n in notes)
    adt = server.get_roadmap("bs-cs", "adt")["notes"]
    assert any("cannot be guaranteed" in n for n in adt) and any("Upon verification" in n for n in adt)


def test_only_save_profile_writes_a_file(tmp_path, tmp_path_factory, monkeypatch):
    # Golden rule 5: no student data at rest except the one file save_profile writes when the student asks
    import asyncio

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    profile = {"program": "bs-cs", "catalog_year": "2026-27", "qr_pathway": "1/2", "start_term": "2027-spring",
               "completed": [{"code": "CSC 101", "grade": "A", "term": "2026-fall"}]}
    plan = server.build_plan(profile)
    pdf = tmp_path_factory.mktemp("downloads") / "SSR_TSRPT.pdf"  # *.pdf is git-ignored: stub the PDF text
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(server.transcript, "read_pdf", lambda path: TRANSCRIPT)
    monkeypatch.setattr(server.dpr, "read_pdf", lambda path: DPR)
    calls = {
        "search_courses": lambda: server.search_courses("data"), "get_course": lambda: server.get_course("CSC 653"),
        "get_prereq_chain": lambda: server.get_prereq_chain("CSC 653"), "list_programs": server.list_programs,
        "get_program_requirements": lambda: server.get_program_requirements("bs-cs"),
        "get_roadmap": lambda: server.get_roadmap("bs-cs"), "audit_progress": lambda: server.audit_progress(profile),
        "build_plan": lambda: plan, "check_plan": lambda: server.check_plan(profile, plan),
        "list_eligible_electives": lambda: server.list_eligible_electives(profile, "senior_electives", plan),
        "load_profile": server.load_profile, "import_transcript": lambda: server.import_transcript(str(pdf)),
        "import_dpr": lambda: server.import_dpr(str(pdf)),
        "ge_combinations": lambda: server.ge_combinations(profile, plan),
        "compare_programs": lambda: server.compare_programs(profile, "bs-applied-math"),
        "get_sections": lambda: server.get_sections("2027-spring", ["CSC 653"]),
    }
    assert set(calls) == {t.name for t in asyncio.run(server.mcp.list_tools())} - {"save_profile"}
    for call in calls.values():
        call()
    server.plan_my_degree()
    assert list(tmp_path.rglob("*")) == []
    got = server.save_profile(profile | {"goal": "security", "chosen_electives": ["CSC 652"]})
    file = tmp_path / ".gatorpath/profile.yaml"
    assert got["saved"] == str(file.resolve()) and sorted(tmp_path.rglob("*")) == [file.parent, file]
    assert file.stat().st_mode & 0o777 == 0o600
    assert server.load_profile()["profile"] == profile | {"goal": "security", "chosen_electives": ["CSC 652"]}


def test_profile_paths_are_the_students_and_never_the_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = {"program": "bs-cs"}
    assert server.save_profile(p, str(ROOT / "evals/me.yaml"))["error"] == "bad_path"
    assert server.save_profile(p, "profile.yaml")["error"] == "bad_path"  # relative: the server's folder
    assert server.save_profile(p, "~/notes.txt")["error"] == "bad_path"
    other = tmp_path / "config.yaml"
    other.write_text("theme: dark\n")
    assert server.save_profile(p, str(other))["error"] == "not_a_profile" and other.read_text() == "theme: dark\n"
    assert server.load_profile(str(other))["error"] == "not_a_profile"  # never echoes another file
    assert server.load_profile("~/missing.yaml")["error"] == "not_found"
    (tmp_path / "link.yaml").symlink_to(other)  # a .yaml name pointing at another file is still refused
    assert server.save_profile(p, "~/link.yaml")["error"] == "not_a_profile" and other.read_text() == "theme: dark\n"


def test_load_profile_warns_when_the_dpr_is_from_an_earlier_term(tmp_path):
    from datetime import date

    file = tmp_path / "p.yaml"
    file.write_text("program: bs-cs\ndpr_imported: 2020-01-15\n")  # unquoted: YAML reads a date
    got = server.load_profile(str(file))
    assert got["profile"]["dpr_imported"] == "2020-01-15" and "ask for a fresh DPR" in got["warnings"][0]
    file.write_text(f"program: bs-cs\ndpr_imported: '{date.today()}'\n")
    assert server.load_profile(str(file))["warnings"] == []
    file.write_text("program: bs-cs\ndpr_imported: 2026\n")
    assert "isn't a date" in server.load_profile(str(file))["warnings"][0]


def test_import_transcript_gives_the_same_audit_as_typing_and_drops_pii(tmp_path, monkeypatch):
    # Phase 6 done-when (transcript half); golden rule 5: no name, ID or birthdate in the output
    pdf = tmp_path / "SSR_TSRPT.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(server.transcript, "read_pdf", lambda path: TRANSCRIPT)
    got = server.import_transcript(str(pdf))
    for pii in ("Zzfake", "Testperson", "900000001", "01/01/XXXX", "Example Community College"):
        assert pii not in json.dumps(got)
    typed = {"completed": [{"code": "CSC 101", "grade": "B+", "term": "2024-fall"}, {"code": "MATH 226", "grade": "A-", "term": "2024-fall"},
                           {"code": "ENG 114", "grade": "C", "term": "2024-fall"}, {"code": "CSC 215", "grade": "A", "term": "2025-spring"},
                           {"code": "MATH 227", "grade": "B", "term": "2025-spring"}],
             "in_progress": ["CSC 220", "CSC 300GW", "I R 205"], "transfer_units": 12}
    base = {"program": "bs-cs", "catalog_year": "2026-27"}
    imported = {k: got[k] for k in ("completed", "in_progress", "transfer_units")}
    assert server.audit_progress(base | imported) == server.audit_progress(base | typed)
    assert server.import_transcript("SSR_TSRPT.pdf")["error"] == "bad_path"  # relative: the server's folder


def test_import_dpr_builds_a_profile_and_drops_pii(tmp_path, monkeypatch):
    pdf = tmp_path / "Degree Progress Report.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(server.dpr, "read_pdf", lambda path: DPR)
    got = server.import_dpr(str(pdf))
    for pii in ("Zzfake", "Testperson", "900000001"):
        assert pii not in json.dumps(got)
    p = got["profile"]
    assert (p["program"], p["catalog_year"], p["gpa"]) == ("bs-cs", "Fall 2024", 3.215)
    # MATH 100TR under "MATH 226", recorded at the requirement's minimum: C- in 2024-25 (C only for CSC 510, CSC 648)
    assert {"code": "MATH 226", "grade": "C-", "transfer": True} in p["completed"]
    assert p["dpr_met"] == ["MATH 225"] and p["in_progress"] == ["CSC 300GW", "CSC 220"]
    assert got["catalog_year"] == "2024-25" and any("Requirements are the 2024-25 Bulletin's" in w for w in got["warnings"])
    audit = {g["id"]: g for g in server.audit_progress(p)["groups"]}
    assert audit["ge_a1"]["status"] == "satisfied"  # "Area A1 - Oral Communication" done on the DPR
    assert [w.split(":")[0] for w in got["cross_check"]] == ["Units toward the 120", "Not found on this DPR"]
    assert [a["role"] for a in got["see_advisor"]] == ["dpr"]


FRESH = {"program": "bs-cs", "catalog_year": "2026-27", "start_term": "2027-fall"}
MATH_FRESH = FRESH | {"program": "bs-applied-math"}
SCENARIOS = {
    "new freshman, QR 1/2": FRESH | {"qr_pathway": "1/2"},
    "new freshman, QR 3/4, F-1": FRESH | {"qr_pathway": "3/4", "f1": True},
    "Fall 2025 catalog, QR 3/4": FRESH | {"qr_pathway": "3/4", "catalog_year": "Fall 2025"},  # roadmap without PHYS 222
    "Fall 2024 catalog (old GE)": FRESH | {"catalog_year": "Fall 2024"},  # one roadmap, no QR pathway; Area E waived
    # Mid-degree students on the older catalogs (they began then), for the evals: courses as their roadmaps lay them out
    "Fall 2025 sophomore": {"program": "bs-cs", "catalog_year": "Fall 2025", "qr_pathway": "1/2", "completed": [
        {"code": c, "grade": "B", "term": t} for t, cs in {
            "2025-fall": ["CSC 101", "MATH 226", "ENG 114", "COMM 150", "AA S 210"],
            "2026-spring": ["CSC 215", "MATH 227", "PHYS 220", "PHYS 222", "PHIL 110"]}.items() for c in cs],
        "in_progress": ["CSC 220", "CSC 230", "PHYS 230", "PHYS 232", "ARTH 201"]},
    "Fall 2024 junior (old GE)": {"program": "bs-cs", "catalog_year": "Fall 2024", "completed": [
        {"code": c, "grade": "B", "term": t} for t, cs in {
            "2024-fall": ["CSC 101", "MATH 226", "ENG 114", "COMM 150", "PHIL 110"],
            "2025-spring": ["CSC 215", "MATH 227", "PHYS 220", "PHYS 222", "AA S 210"],
            "2025-fall": ["CSC 220", "CSC 230", "MATH 225", "PHYS 230", "PHYS 232", "ARTH 201"],
            "2026-spring": ["CSC 256", "CSC 340", "MATH 324", "BIOL 100", "ECON 101"]}.items() for c in cs],
        "in_progress": ["CSC 300GW", "CSC 317", "CSC 510"]},
    "freshman with AP credit": FRESH | {"qr_pathway": "1/2", "first_time": True, "transfer_units": 8, "ge_done": ["USH", "2"]},
    "sophomore": yaml.safe_load((ROOT / "evals/profiles/p03-sophomore-qr34.yaml").read_text())["profile"],
    "ADT transfer": FRESH | {"adt": True, "ge_certified": True, "first_time": False, "transfer_units": 60,
                             "completed": [{"code": c, "grade": "B", "transfer": True} for c in ("CSC 101", "CSC 215", "MATH 226")]},
    "Cal-GETC transfer, no ADT": FRESH | {"qr_pathway": "1/2", "ge_certified": True, "first_time": False, "transfer_units": 60},
    "prior bachelor's": FRESH | {"qr_pathway": "1/2", "prior_bachelors": True, "transfer_units": 90},
    "fast, with summers": FRESH | {"qr_pathway": "1/2", "include_summer": True, "max_units_per_term": 18},
    "part-time with a deadline": FRESH | {"qr_pathway": "1/2", "max_units_per_term": 12, "graduate_by": "2031-spring"},
    "retaking a D": {"program": "bs-cs", "catalog_year": "2026-27", "qr_pathway": "1/2",
                     "completed": [{"code": "CSC 101", "grade": "A", "term": "2026-fall"},
                                   {"code": "MATH 226", "grade": "B", "term": "2026-fall"},
                                   {"code": "CSC 215", "grade": "D", "term": "2027-spring"}]},
    "older-catalog DPR": FRESH | {"catalog_year": "Spring 2025", "first_time": False, "transfer_units": 45,
                                  "ge_done": ["Area A1 - Oral Communication", "A2", "A3", "B4", "GE D/USH"],
                                  "not_on_dpr": ["6"], "dpr_met": ["MATH 225"], "qr_pathway": "1/2"},
    "CCC transfer from another major": FRESH | {"qr_pathway": "1/2", "ge_certified": True, "first_time": False,
        "transfer_units": 62, "completed": [{"code": c, "grade": "B", "transfer": True}
                                            for c in ("CSC 101", "CSC 215", "MATH 226", "MATH 227", "PHYS 220", "PHYS 222")]},
    "junior, on track": {"program": "bs-cs", "catalog_year": "2026-27", "qr_pathway": "1/2", "completed": [
        {"code": c, "grade": "B", "term": t} for t, cs in {
            "2025-fall": ["CSC 101", "MATH 226", "ENG 114", "COMM 150", "AA S 210"],
            "2026-spring": ["CSC 215", "MATH 227", "PHYS 220", "PHYS 222", "PHIL 110"],
            "2026-fall": ["CSC 220", "CSC 230", "PHYS 230", "PHYS 232", "ARTH 201", "ECON 101"],
            "2027-spring": ["CSC 256", "CSC 340", "MATH 225", "MATH 324", "BIOL 100"]}.items() for c in cs]},
    "failed MATH 226": {"program": "bs-cs", "catalog_year": "2026-27", "qr_pathway": "1/2",
                        "completed": [{"code": "CSC 101", "grade": "A", "term": "2026-fall"},
                                      {"code": "MATH 226", "grade": "F", "term": "2026-fall"}]},
    "freshman at 18 units": FRESH | {"qr_pathway": "1/2", "max_units_per_term": 18},
    # BS Applied Mathematics (pp.2129-2137)
    "Applied Math freshman, QR 1/2": MATH_FRESH | {"qr_pathway": "1/2"},
    "Applied Math freshman, QR 3/4": MATH_FRESH | {"qr_pathway": "3/4"},
    "Applied Math ADT transfer": MATH_FRESH | {"adt": True, "ge_certified": True, "first_time": False, "transfer_units": 60,
                                               "completed": [{"code": c, "grade": "B", "transfer": True}
                                                             for c in ("MATH 226", "MATH 227", "MATH 228")]},
    "Applied Math, CSC 101 done": MATH_FRESH | {"qr_pathway": "1/2", "completed": [
        {"code": "CSC 101", "grade": "A", "term": "2027-spring"}, {"code": "MATH 226", "grade": "B", "term": "2027-spring"}]},
}


def test_an_applied_math_plan_follows_its_roadmap_and_select_ones():
    # QR 1/2 at 15 units: every course in its roadmap semester (p.2132-2133); the "Select One" is MATH 209
    sems = yaml.safe_load((ROOT / "rules/roadmaps/2026-27/bs-applied-math.yaml").read_text())["variants"]["qr-1-2"]["semesters"]
    road = {c: n for n, sem in enumerate(sems) for c in sem["items"] if isinstance(c, str)}
    plan = server.build_plan(SCENARIOS["Applied Math freshman, QR 1/2"])
    at = {c: n for n, s in enumerate(plan["semesters"]) for c in s["courses"] if isinstance(c, str)}
    assert plan["check"]["valid"] and len(plan["semesters"]) == 8
    assert {c: at[c] for c in road} == road and at["MATH 209"] == 1
    slots = {c["slot"] for s in plan["semesters"] for c in s["courses"] if isinstance(c, dict)}
    assert {"theory", "major_electives", "application_electives"} <= slots
    assert plan["see_advisor"][0]["role"] == "substitutions" and "consent of the applied mathematics advisor" in plan["see_advisor"][0]["why"][0]
    # CSC 101 already done: the CSC 101 & CSC 215 option, and the roadmap's "CSC 215 (if CSC 101 taken)"
    switch = server.build_plan(SCENARIOS["Applied Math, CSC 101 done"])
    codes = {c for s in switch["semesters"] for c in s["courses"] if isinstance(c, str)}
    assert switch["check"]["valid"] and "CSC 215" in codes and not codes & {"MATH 209", "CSC 309"}


def test_a_freshman_plan_is_the_roadmap_adjusted():
    # 15 units: the roadmap's own semesters, a term later at most (its 16-unit terms); 18 units: earlier, never later
    road = {c: n for n, sem in enumerate(yaml.safe_load((ROOT / "rules/roadmaps/2026-27/bs-cs.yaml").read_text())
                                         ["variants"]["qr-1-2"]["semesters"]) for c in sem["items"] if isinstance(c, str)}
    for cap, terms in ((15, 8), (18, 7)):
        plan = server.build_plan(FRESH | {"qr_pathway": "1/2", "max_units_per_term": cap})
        at = {c: n for n, s in enumerate(plan["semesters"]) for c in s["courses"] if isinstance(c, str)}
        shift = [at[c] - road[c] for c in road]
        assert len(plan["semesters"]) == terms and plan["check"]["valid"]
        assert any(w.startswith("Laid out on the Bulletin's First-Time Student Roadmap") for w in plan["warnings"])
        if cap == 15:
            assert shift.count(0) >= 0.85 * len(shift) and max(shift) <= 1 and min(shift) >= 0
        else:
            assert max(shift) <= 0 and min(shift) < 0  # the extra units pull courses forward


@pytest.mark.parametrize("name", SCENARIOS)
def test_every_kind_of_student_gets_a_checked_plan_and_ge_ways(name):
    import time

    p = SCENARIOS[name]
    assert "error" not in server.audit_progress(p)
    plan = server.build_plan(p)
    assert plan.get("semesters") and plan["check"]["valid"], (plan.get("needs_input"), plan.get("check"))
    assert server.check_plan(p, {"semesters": plan["semesters"]})["valid"]  # golden rule 6, as the client re-checks it
    start = time.time()
    ways = server.ge_combinations(p, {"semesters": plan["semesters"]})
    assert time.time() - start < 5 and "error" not in ways
    assert ways["ways"] or not ways["open"] or any("No eligible course" in w for w in ways["warnings"])
    for s in plan["semesters"]:
        for slot in {c["slot"] for c in s["courses"] if isinstance(c, dict) and c["slot"] != "elective"}:
            got = server.list_eligible_electives(p, slot, {"semesters": plan["semesters"]}, by_term=s["term"])
            assert "error" not in got, (slot, got.get("error"))


def test_the_students_catalog_year_picks_the_rules():
    # Catalog rights (p.2390): audited against the student's own year. Test user 1's DPR: Fall 2025 -> 2025-26 rules
    year = lambda given: server.rules_year({"program": "bs-cs", "catalog_year": given})
    assert year("Fall 2025") == year("Spring 2026") == year("2025-fall") == year("2025-26") == "2025-26"
    assert year("Fall 2026") == "2026-27" and year("Spring 2025") == year("Fall 2024") == "2024-25"
    assert year("Spring 2024") == year(None) == server.YEAR  # no 2023-24 rules
    assert year("2025-2026") == "2025-26" and year("2025-30") == server.YEAR
    assert server.YEAR == server.YEARS[-1]
    # Commit review: "Fall 2026" is the newest year itself, not an unsupported one
    warn = lambda given: server.year_warning({"program": "bs-cs", "catalog_year": given}, year(given))
    assert warn("Fall 2026") == warn("2026-27") == []
    assert warn("Spring 2024")[0].startswith("The student's catalog year is Spring 2024, but GatorPath has bs-cs rules "
                                             "only for 2024-25, 2025-26, 2026-27")
    # a program with fewer years names its own: BA Economics has only 2026-27 rules
    econ = {"program": "ba-economics", "catalog_year": "Fall 2025"}
    assert server.rules_year(econ) == "2026-27"
    assert "has ba-economics rules only for 2026-27, so this uses 2026-27" in server.year_warning(econ, "2026-27")[0]
    # BS Applied Mathematics 2025-26 is a rule diff of 2026-27 (no "Grades of C or better" list yet)
    assert server.rules_year({"program": "bs-applied-math", "catalog_year": "Fall 2025"}) == "2025-26"


def test_a_2025_26_student_needs_c_only_in_csc_510_and_648():
    # 2025-26 p.1905: "Grades of C or better are required for CSC 510 and CSC 648"; 2026-27 asks C in all Math/Physics
    rows = [{"code": "PHYS 220", "grade": "C", "term": "2025-fall"}, {"code": "PHYS 222", "grade": "D", "term": "2025-fall"}]
    audit = lambda year: server.audit_progress({"program": "bs-cs", "catalog_year": year, "completed": rows})
    groups = lambda out: {g["id"]: g for g in out["groups"]}
    old, new = audit("Fall 2025"), audit("2026-27")
    assert "PHYS 222" in groups(old)["math_physics"]["counted"] and "PHYS 222" in groups(new)["math_physics"]["remaining"]
    assert old["catalog_year"] == "2025-26" and any(w.startswith("Requirements are the 2025-26 Bulletin's") for w in old["warnings"])


def test_a_completed_course_dropped_since_keeps_its_older_row(tmp_path, monkeypatch):
    # D23: course facts are the newest Bulletin's, but a course taken before it was dropped still counts
    db = tmp_path / "catalog.db"
    write_catalog(db, "2026-27", ROWS)
    gone = next(r for r in ROWS if r["code"] == "ECON 101") | {"code": "ETHS 100", "title": "Introduction to Ethnic Studies"}
    write_catalog(db, "2025-26", [gone])
    monkeypatch.setattr(server, "DB", db)
    assert server.catalog_for({"completed": [{"code": "ETHS 100", "grade": "A"}]})["ETHS 100"]["title"] == gone["title"]
    assert "ETHS 100" not in server.catalog_for({"completed": []})


def test_qr_pathway_is_read_however_the_student_writes_it():
    # Eval run 2026-10-18: a client passed "QR 3/4" and build_plan asked for qr_pathway again
    university = server.load_rules("2026-27", "bs-cs")[1]
    read = lambda qr: server.prepare({"program": "bs-cs", "qr_pathway": qr}, university)[0]["qr_pathway"]
    assert [read(q) for q in ("QR 3/4", "Category 1/2", "3-4", "1/2")] == ["3/4", "1/2", "3/4", "1/2"]
    assert read("not sure") == "not sure"  # left as given: build_plan then asks for it


def test_the_server_never_plans_on_top_of_the_current_term():
    # Eval plan-p01 (codex): start_term 2026-fall while CSC 101 was in progress in it; today is pinned to 2026-10-18
    p = {"catalog_year": "2026-27", "program": "bs-cs", "in_progress": ["CSC 101"], "start_term": "2026-fall"}
    errs = [e["error"] for e in server.check_plan(p, {"semesters": [{"term": "2026-fall", "courses": ["CSC 215"]}]})["errors"]]
    assert "term_in_progress" in errs


def test_compare_programs_quotes_the_change_of_major_rule():
    p = SCENARIOS["Fall 2025 sophomore"]  # BS CS on the 2025-26 Bulletin
    got = server.compare_programs(p, "bs-applied-math")
    assert got["catalog_year"] == got["target"]["catalog_year"] == "2026-27" and got["current"]["catalog_year"] == "2025-26"
    rule = next(w for w in got["warnings"] if w.startswith("Changing major:"))
    assert "must fulfill the major requirements in effect at the time they declare or change their major" in rule
    assert "(p.2352, p.2390)" in rule and "stay your catalog year's (2025-26)" in rule
    assert "MATH 226" in got["courses"]["count_in_both"] and "PHYS 220" in got["courses"]["only_current"]
    assert server.compare_programs(p, "bs-cs")["error"] == "same_program"
    assert server.compare_programs(p, "ba-math")["error"] == "unknown_program"
    freshman = server.compare_programs(SCENARIOS["new freshman, QR 1/2"], "bs-applied-math")
    assert freshman["courses"] == {"count_in_both": [], "only_current": [], "only_target": []}
    assert freshman["extra_terms"] == freshman["target"]["terms"] - freshman["current"]["terms"]
