"""MCP tools over a small catalog.db built from real 2026-27 Bulletin rows (tests/fixtures/catalog_rows.json), so CI
runs without the PDF. The rows are every course in evals/catalog-2026-27.json plus the CSC 653 prereq chain."""

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from gatorpath import server
from gatorpath.engine.rules import audit, load_rules
from gatorpath.ingest.bulletin import write_catalog

ROOT = Path(__file__).parents[1]
ROWS = json.loads((ROOT / "tests/fixtures/catalog_rows.json").read_text())
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
    assert "'*'" in w and "cycle" not in w                   # PHYS 220/222 are corequisites, not a cycle


def test_get_course_record():
    got = server.get_course(" csc 671 ")
    assert (got["code"], got["title"], got["source_page"]) == ("CSC 671", "Deep Learning", 1900)
    assert got["links"] == [{"code": "CSC 871", "kind": "paired"}]
    assert got["prereq"]["status"] == "ok" and got["prereq"]["needs_permission"] is True
    assert got["offered_terms"] == "unknown" and any("phase 5" in w for w in got["warnings"])


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
    assert server.list_programs()["programs"] == [
        {"id": "bs-cs", "title": "Bachelor of Science in Computer Science", "verified": False}]
    req = server.get_program_requirements("bs-cs")
    assert [g["id"] for g in req["program"]["groups"]][:2] == ["math_physics", "core_cs"]
    assert any("not verified" in w for w in req["warnings"])
    assert server.get_program_requirements("../university/2026-27")["error"] == "unknown_program"
    assert set(server.get_roadmap("bs-cs")["variants"]) == {"qr-1-2", "qr-3-4", "adt"}
    rm = server.get_roadmap("bs-cs", "qr-1-2")
    assert rm["semesters"][0]["items"][0] == "CSC 101" and rm["source"] == "p.1908-1909"


@pytest.mark.parametrize("path", sorted((ROOT / "evals/profiles").glob("*.yaml")), ids=lambda p: p.stem)
def test_audit_progress_matches_engine(path):
    profile = yaml.safe_load(path.read_text())["profile"]
    want = audit(profile, *load_rules("2026-27", "bs-cs"), json.loads((ROOT / "evals/catalog-2026-27.json").read_text()))
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


def test_audit_progress_rejects_unknown_program_and_year():
    assert server.audit_progress({"program": "bs-art"})["error"] == "unknown_program"
    assert server.audit_progress({"program": "bs-cs", "catalog_year": "2025-26"})["error"] == "unsupported_catalog_year"


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
