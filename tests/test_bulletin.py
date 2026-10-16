import json
import sqlite3
from pathlib import Path

import pytest

from gatorpath.ingest.bulletin import coverage_report, extract_pages, parse_courses, write_catalog

HEAD = "San Francisco State University Bulletin 2026-2027 Computer Science"


def page(body: str, printed: int) -> str:
    """A page as `pdftotext -raw` prints it: running head, body, printed page number."""
    return f"{HEAD}\n{body.strip()}\n{printed}\n"


# Real text, Bulletin 2026-27 PDF p.1897 (printed 1896).
P1896 = page("""
CSC 256 Machine Structures (Units: 3)
Prerequisite: CSC 230 with a grade of C or better.
Digital logic circuits, data representation, assembly language
programming, subroutine linkage, machine language encoding, interrupt
and exception handling, memory system concepts, and CPU organization
and performance.
CSC 300GW Ethics, Communication, and Tools for Software Development
- GWAR (Units: 3)
Prerequisites: Restricted to upper-division Computer Science majors and
minors; GE Area 1A/A2; CSC 210 or CSC 215.
Privacy, security, legal, and ethical issues in Software development.
Study and use of basic tools for SW development and collaboration. (ABC/NC
grading only)
Course Attributes:
• Graduation Writing Assessment
CSC 306 An Interdisciplinary Approach to Computer Programming (Units:
3)
Prerequisites: Restricted to Biology, Chemistry, and Biochemistry majors
and Certiﬁcate in Data Science and Machine Learning for Biotechnology
Professionals students; upper-division standing; or permission of the
instructor.
Basics of programming for interdisciplinary problem-solving, using
Python.
CSC 310 Computer Programming Lab (Unit: 1)
Prerequisite: Concurrent enrollment in CSC 309 is recommended.
Laboratory for CSC 309. (CR/NC
grading only)
""", 1896)


def by_code(pages):
    courses, warnings = parse_courses(pages)
    return {c["code"]: c for c in courses}, warnings


def test_header_title_units_and_printed_page():
    c = by_code([P1896])[0]["CSC 256"]
    assert c["title"] == "Machine Structures"
    assert (c["units_min"], c["units_max"]) == (3, 3)
    assert c["source_page"] == 1896


def test_header_wrapped_title_and_wrapped_units():
    cs = by_code([P1896])[0]
    assert cs["CSC 300GW"]["title"] == "Ethics, Communication, and Tools for Software Development - GWAR"
    assert cs["CSC 306"]["title"] == "An Interdisciplinary Approach to Computer Programming"
    assert cs["CSC 306"]["units_min"] == 3


def test_singular_unit_and_unit_range():
    cs = by_code([P1896, page("CSC 699 Independent Study (Units: 1-3)\nPrerequisite: Permission of the instructor.\nStudy.", 1904)])[0]
    assert cs["CSC 310"]["units_max"] == 1
    assert (cs["CSC 699"]["units_min"], cs["CSC 699"]["units_max"]) == (1, 3)


def test_prereq_text_stops_where_description_starts():
    cs = by_code([P1896])[0]
    assert cs["CSC 256"]["prereq_text"] == "CSC 230 with a grade of C or better."
    assert cs["CSC 306"]["prereq_text"].endswith("or permission of the instructor.")
    assert cs["CSC 306"]["description"].startswith("Basics of programming")


def test_grading_kinds_from_wrapped_notes():
    cs = by_code([P1896])[0]
    assert cs["CSC 300GW"]["grading"] == "letter"
    assert cs["CSC 310"]["grading"] == "cr_nc"
    allowed = page("ENG 114 Writing the First Year (Units: 3)\nPractice. (Plus-\nminus ABC/NC, CR/NC allowed)", 900)
    assert by_code([allowed])[0]["ENG 114"]["grading"] == "letter_or_cr_nc"


def test_course_attributes_map_to_current_ge_codes_only():
    cs = by_code([P1896])[0]
    assert cs["CSC 300GW"]["ge_areas"] == ["GW"]
    bus = page("""
BUS 401 Business in Society (Units: 3)
Prerequisite: Upper-division standing.
Topics. (Plus-minus letter grade only)
Course Attributes:
• UD-C: Arts and/or Humanities
• 3UD: Arts or Humanities
• Global Perspectives
• U.S. Govt CA State Local Govt
""", 120)
    assert by_code([bus])[0]["BUS 401"]["ge_areas"] == ["3UD", "GP", "USG", "CSLG"]


def test_running_head_and_page_number_not_in_text_across_page_break():
    p1 = page("CSC 620 Natural Language Technologies (Units: 3)\nPrerequisite: CSC 413 with a\ngrade of C or better.\nIntroduction to NLP.", 2556)
    p2 = page("Practical experience in NLP. (Plus-minus letter grade only)\nCSC 621 Biomedical Imaging (Units: 3)\nPrerequisite: CSC 510.\nImaging.", 2557)
    c = by_code([p1, p2])[0]["CSC 620"]
    assert c["description"] == "Introduction to NLP. Practical experience in NLP. (Plus-minus letter grade only)"
    assert "2556" not in c["description"] and "Bulletin" not in c["description"]
    assert c["source_page"] == 2556


# Real text, PDF p.1905 (printed 1904).
P871 = page("""
CSC 871 Deep Learning (Units: 3)
Prerequisite for CSC 871: Graduate standing or permission of the
instructor.
Prerequisites for CSC 671: Upper-division standing; CSC 510*; MATH 225
or MATH 325 with a grade of C or better; GPA of 3.0 or higher; or
permission of the instructor.
Exploration of the major technology trends that drive Deep Learning. (Plus-minus letter grade only)
(CSC 871/CSC 671 is a paired course offering. Students who complete
the course at one level may not repeat the course at the other level.)
""", 1904)


def test_paired_entry_keeps_only_own_prereq_segment():
    c = by_code([P871])[0]["CSC 871"]
    assert c["prereq_text"] == "Graduate standing or permission of the instructor."
    assert c["paired_with"] == ["CSC 671"]


def test_paired_entry_does_not_invent_the_other_course():
    cs, _ = by_code([P871])
    assert "CSC 671" not in cs  # no fabricated course rows


def test_dedupe_keeps_first_copy_and_warns_when_texts_differ():
    dept = page("CSC 256 Machine Structures (Units: 3)\nPrerequisite: CSC 230.\nDigital logic.", 1896)
    same = page("CSC 256 Machine Structures (Units: 3)\nPrerequisite: CSC 230.\nDigital logic.", 2555)
    diff = page("CSC 256 Machine Structures (Units: 4)\nPrerequisite: CSC 230.\nDigital logic.", 2555)
    courses, warnings = parse_courses([dept, same])
    assert [c["source_page"] for c in courses] == [1896] and warnings == []
    courses, warnings = parse_courses([dept, diff])
    assert len(courses) == 1 and courses[0]["units_min"] == 3
    assert any("CSC 256" in w for w in warnings)


def test_line_starting_with_course_code_is_not_a_header():
    p = page("CSC 340 Programming Methodology (Units: 3)\nPrerequisites: CSC 220 and\nCSC 230 with grades of C or better.\nDesign.", 1897)
    cs = by_code([p])[0]
    assert list(cs) == ["CSC 340"]
    assert cs["CSC 340"]["prereq_text"] == "CSC 220 and CSC 230 with grades of C or better."


PDF = Path(__file__).parents[1] / "data/raw/bulletin-2026-27.pdf"


@pytest.mark.skipif(not PDF.exists(), reason="Bulletin PDF not present (git-ignored)")
def test_real_bulletin_csc():
    cs, warnings = by_code(extract_pages(PDF))
    assert cs["CSC 653"]["title"] == "Network Security"
    assert cs["CSC 215"]["units_min"] == 4
    assert cs["CSC 871"]["paired_with"] == ["CSC 671"]
    assert cs["CSC 671"]["prereq_text"].startswith("Upper-division standing; CSC 510*")
    assert cs["CSC 300GW"]["ge_areas"] == ["GW"]
    assert 1895 <= cs["CSC 256"]["source_page"] <= 1905  # department-section copy wins


def test_prereq_missing_final_period_stops_at_course_attributes():
    # Real shape of SPED 745 (no period after its prereq)
    p = page("""
SPED 745 Inclusive Service Delivery (Units: 3)
Prerequisite: Graduate-level standing or minor in Special Education
Focus on inclusive and integrated service delivery. (Plus-minus letter grade only)
Course Attributes:
• Teacher Credential Program Crs
""", 2700)
    c = by_code([p])[0]["SPED 745"]
    assert "Course Attributes" not in c["prereq_text"]
    assert c["ge_areas"] == []


def test_ligatures_are_normalized():
    p = page("CSC 511 Data Science Lab (Units: 3)\nPrerequisite: Restricted to Certiﬁcate students.\nScientiﬁc work.", 1898)
    c = by_code([p])[0]["CSC 511"]
    assert c["prereq_text"] == "Restricted to Certificate students."
    assert c["description"] == "Scientific work."


def test_crosslisted_codes_skip_formerly_notes():
    # Real text, LTNS 501 entry
    p = page("""
LTNS 501 Latina/o/x History (Units: 3)
Prerequisite: Upper-division standing.
History. (This course is offered as HIST 358 [Formerly HIST 501], ANTH 501, and LTNS 501. Students may not
repeat the course under an alternate prefix.)
""", 1300)
    c = by_code([p])[0]["LTNS 501"]
    assert c["crosslisted_with"] == ["HIST 358", "ANTH 501"]
    assert by_code([P1896])[0]["CSC 256"]["crosslisted_with"] == []


def test_paired_note_with_formerly():
    # Real text, CSC 852 entry (printed p.1903)
    p = page("""
CSC 852 Introduction to Security and Data Privacy (Units: 3)
Prerequisite for CSC 852: Graduate standing or permission of the instructor.
Data privacy. Extra fee required.
(CSC 852/CSC 652 [formerly CSC 650] is a paired course offering. Students who complete the course at one level may
not repeat the course at the other level.)
""", 1903)
    assert by_code([p])[0]["CSC 852"]["paired_with"] == ["CSC 652"]


def test_write_catalog_rows_and_links(tmp_path):
    db = tmp_path / "catalog.db"
    courses, _ = parse_courses([P1896, P871])
    write_catalog(db, "2026-27", courses)
    write_catalog(db, "2026-27", courses)  # rebuild replaces, never duplicates
    con = sqlite3.connect(db)
    assert con.execute("select count(*) from course").fetchone()[0] == len(courses)
    page_, ge = con.execute("select source_page, ge_areas from course where code='CSC 300GW'").fetchone()
    assert (page_, json.loads(ge)) == (1896, ["GW"])
    raw, expr, status, perm = con.execute("select raw_text, expr, status, needs_permission from prereq where code='CSC 871'").fetchone()
    assert raw == "Graduate standing or permission of the instructor."
    assert status == "ok" and perm == 1
    assert json.loads(expr) == {"any": [{"standing": "graduate"}, {"permission": "instructor"}]}
    assert con.execute("select code_a, code_b, kind from course_link").fetchall() == [("CSC 671", "CSC 871", "paired")]


def test_coverage_report_lists_every_non_ok_string(tmp_path):
    db = tmp_path / "catalog.db"
    odd = page("CSC 699 Independent Study (Units: 1-3)\nPrerequisite: Formal commitment to a thesis.\nStudy.", 1904)
    write_catalog(db, "2026-27", parse_courses([P1896, odd])[0])
    report = coverage_report(db, "2026-27", ["CSC"])
    assert "CSC" in report and "4/5 ok (80.0%)" in report
    assert "CSC 699 [unparsed] Formal commitment to a thesis." in report
    assert "CSC 300GW -> CSC 210" in report  # referenced code missing from this catalog (renumbered)
