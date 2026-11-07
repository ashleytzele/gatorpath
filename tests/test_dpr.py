"""DPR print -> requirements and profile fields, from the synthetic fixture (real layout, fake name/ID, invented courses)."""

import shutil
from pathlib import Path

import pytest

from gatorpath import dpr
from gatorpath.dpr import cross_check, parse, to_profile
from gatorpath.engine.rules import load_rules

DPR = parse((Path(__file__).parent / "fixtures/dpr_synthetic.txt").read_text())
by_title = {r["title"]: r for r in DPR["requirements"] if r["kind"] != "group"}


def test_header_and_statuses_come_from_the_rows():
    assert (DPR["plan"], DPR["catalog_term"], DPR["gpa"], DPR["sf_state_gpa"]) == ("Computer Science-BS", "Fall 2024", 3.215, 3.15)
    status = {t: r["status"] for t, r in by_title.items()}
    assert status["Area A1 - Oral Communication"] == "done"            # COMM 100TR, grade T
    assert status["Area D - Social Sciences"] == "needed"              # "Units: 9.00 required, 6.00 taken, 3.00 needed"
    assert status["Area E - Lifelong Learning and Self-Development"] == "waived"   # Dean's memo 3/12/25
    assert status["Minimum Units of General Education Coursework"] == "needed"     # 48 -> 42 still 11 short
    assert status["CSC 220"] == "in_progress" and status["CSC 413"] == "needed"    # "Fall, Spring, Summer" = not taken
    assert [r["code"] for r in by_title["Courses Not Used"]["rows"]] == ["TRFX 50NTR"]  # not CSC 413's
    assert any("10 of 12 courses" in w for w in DPR["warnings"])


def test_transfer_rows_meet_the_course_they_sit_under_and_substitutions_become_dpr_met():
    got = to_profile(DPR, {"CSC 101": "C", "MATH 226": "C"}, {"CSC 101": 3.0, "CSC 215": 4.0})
    assert {"code": "CSC 101", "grade": "C", "transfer": True} in got["completed"]  # CSC 100TR under "CSC 101 and CSC 215"
    assert {"code": "CSC 215", "grade": "B", "term": "2025-fall"} in got["completed"]
    assert got["dpr_met"] == ["MATH 225"]                                             # MATH 325 under "MATH 225"
    assert got["ge_done"] == ["Area A1 - Oral Communication", "Area A2 - Written Communication I",
                              "Area A3 - Critical Thinking", "USH"]                   # Area D isn't done; USH from GE D/USH
    assert got["transfer_units"] == 19 and any("no legend" in w for w in got["warnings"])
    assert [r["requirement"] for r in got["remaining"]] == ["Area D - Social Sciences", "Minimum Units of General Education Coursework",
                                                           "120 Minimum Units Required for Degree", "CSC 413"]


def test_print_headers_and_instruction_lines_are_not_titles():
    # Test user 1 (2026-10-20; layout copied, rows invented): a page break between a title and its tag made the
    # browser's print header the title; "One course is required." stood in for "U.S. History"
    text = """
         Area 5B: Biological Science

https://cmsweb.sfsu.edu/psp/CSFPRDS/EMPLOYEE/SA/c/SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL?gsmobile=0                   3/16

01/20/27, 10:05 AM                                                                     My Academic Requirements

          Units Required = 3 Units (2.68 Converted Quarter Units)

          [R12829 / L0040]

         Course            Description                               Units      When                Grade Status
         BIOL 100          HUMAN BIOLOGY                      3.00              Fall 2025           B

         U.S. History

          One course is required.

          [R10003 / L0010]

                       Courses: 1 required, 0 taken, 1 needed
"""
    assert [r["title"] for r in parse(text)["requirements"]] == ["Area 5B: Biological Science", "U.S. History"]


def test_cross_check_flags_only_real_disagreements():
    # Phase 6 done-when: the synthetic DPR's courses and GE areas agree with an audit of what it lists; what's left
    # is explained (unlisted transfer units; GE areas this partial DPR doesn't show)
    from gatorpath.engine.rules import load_rules
    _, university = load_rules("2026-27", "bs-cs")
    group = lambda i, status, counted=(), going=(): {"id": i, "status": status, "counted": list(counted), "in_progress": list(going)}
    audit = {"groups": [group("ge_1c", "satisfied"), group("ge_1a", "satisfied"), group("ge_1b", "satisfied"),
                        group("ge_4", "remaining"), group("gwar", "in_progress"),
                        group("math_physics", "remaining", ["MATH 225", "MATH 226", "MATH 227"]),
                        group("core_cs", "remaining", ["CSC 101", "CSC 215"], ["CSC 220", "CSC 300GW"])],
             "totals": {"units": {"value": 46.0}, "units_in_progress": 6.0}}
    got = cross_check(DPR, audit, university)
    assert got[0].startswith("Units toward the 120: the DPR counts 74 taken, GatorPath 52")
    assert got[1].startswith("Not found on this DPR: GE 2 Mathematical") and "SF State Studies" not in got[1]
    assert len(got) == 2
    audit["groups"][0]["status"] = "remaining"
    assert cross_check(DPR, audit, university)[0].startswith(
        "Area A1 - Oral Communication: the DPR says done, GatorPath says needed. The DPR wins")


def test_a_minor_and_a_majors_own_areas_dont_pass_for_the_major_and_ge():
    # A Fall 2025 DPR (2026-10-26; layout copied, plans and rows invented): the minor's Plan line came second and
    # replaced the major's, and the major's "Area 1: Basic Psychological Processes" was read as GE Area 1
    text = """
   Plan:         Psychology-BA                      Fall 2025
   Plan:         Spanish-MN                         Spring 2027                       Overall GPA:            3.100
      General Education Requirements
   The University requires students to complete 43 units of General Education requirements.
   [G11368]
          Area 1A: English Composition
           Units Required = 3 Units
           [R12828 / L0010]
         Course             Description                               Units        When                    Grade Status
         ENG 114            WRITING FIRST YEAR                3.00                Fall 2025               B
      University Requirements
   University Requirements
   [G10000]
      B.A. in Psychology
   Total Units Required = 40.68 - 41 Units
   [G10005]
          Area 1: Basic Psychological Processes
           Units Required = 6 Units
           [R10084 / L0010]
         Course             Description                               Units        When                    Grade Status
         PSY 492            PERCEPTION                        3.00                Fall 2025               A-
         PSY 493            MOTIVATION                        3.00                Fall 2025               B+
"""
    got = parse(text)
    assert (got["plan"], got["catalog_term"]) == ("Psychology-BA", "Fall 2025")
    kinds = {r["title"]: r["kind"] for r in got["requirements"] if r["kind"] != "group"}
    assert kinds == {"Area 1A: English Composition": "ge", "Area 1: Basic Psychological Processes": "other"}
    assert to_profile(got, {}, {})["ge_done"] == ["Area 1A: English Composition"]


def test_collapsed_requirements_are_flagged_not_missing():
    # The same DPR printed without Expand All: a met requirement shows only its title, no tag or rows
    text = """
      General Education Requirements
   The University requires students to complete 43 units of General Education requirements.
   [G11368]
       Area 1: English Communication
        Complete one course in each area.
        [R12828]
          Area 1A: English Composition
          Area 1B: Critical Thinking
       Upper Division General Education
        Complete one course in the three areas (2UD/5UD, 3UD, and 4UD) for a minimum of 9
        [R12831]
          Area 3UD: Arts or Humanities
           Units Required = 3 Units
           [R12831 / L0060]
         Course             Description                               Units        When                    Grade Status
         HUM 325            ART AND IDEAS                     3.00                Spring 2027
      B.A. in Psychology
   Total Units Required = 40.68 - 41 Units
   [G10005]
       Core Curriculum
        Units Required = 13.68 to 14 Units
        [R10080]
          PSY 200
          PSY 400
           Units Required = 3 Units
           [R10080 / L0040]
"""
    got = parse(text)
    collapsed = [r["title"] for r in got["requirements"] if r["status"] == "collapsed"]
    assert collapsed == ["Area 1A: English Composition", "Area 1B: Critical Thinking", "PSY 200"]
    assert any("Expand All" in w and "Area 1A" in w for w in got["warnings"])
    from gatorpath.engine.rules import load_rules
    _, university = load_rules("2026-27", "bs-cs")
    audit = {"groups": [{"id": "ge_3ud", "status": "in_progress"}], "totals": {"units": {"value": 0.0}}}
    assert not any("GE 1A" in w for w in cross_check(got, audit, university))  # on the DPR, just collapsed


def pdf_of(text: str) -> bytes:
    """A one-line PDF, offsets and all, so the real pdftotext has something to read."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>",
               b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    table = len(out)
    out += b"xref\n0 5\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % table


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="poppler not installed")
def test_read_pdf_bytes_reads_over_stdin():
    assert "Degree Progress Report" in dpr.read_pdf_bytes(pdf_of("Degree Progress Report"))


def block(title, kind, status="done", rows=()):
    return {"id": title, "title": title, "kind": kind, "status": status, "rows": list(rows), "needed": None, "waived": None}


def transfer_row(code, units, term=None):
    return {"code": code, "units": units, "term": term, "grade": "T", "notes": None, "designation": None,
            "transfer": True, "option": term is None}


def test_a_dpr_area_is_compared_with_its_own_requirement_not_the_combined_one():
    """Area C has C1, C2 and a 9-unit group over both: a done C1 is measured against C1, or it can never match."""
    _, university = load_rules("2024-25", "bs-cs")
    print_ = {"requirements": [block("Area C1 - Arts", "ge"), block("Area C2 - Humanities", "ge")]}
    audit = {"groups": [{"id": "ge_c1", "status": "satisfied"}, {"id": "ge_c2", "status": "satisfied"},
                        {"id": "ge_c", "status": "in_progress"}], "totals": {}}
    assert not any("Area C" in w for w in cross_check(print_, audit, university))
    audit["groups"][0]["status"] = "remaining"  # a real disagreement still shows
    assert any(w.startswith("Area C1") for w in cross_check(print_, audit, university))


def test_transfer_units_count_each_course_once_but_never_merge_two_courses():
    """Every transfer course has a generic code, so MATH 100TR can be two courses, and one row repeats across lists."""
    calc1, calc2, cs = [block(t, "course", rows=[transfer_row(c, u)])
                        for t, c, u in (("MATH 226", "MATH 100TR", 4.0), ("MATH 227", "MATH 100TR", 4.0), ("CSC 101", "CSC 100TR", 3.0))]
    wanted = {"MATH 226": "C-", "MATH 227": "C-", "CSC 101": "C-"}
    units = {"MATH 226": 4.0, "MATH 227": 4.0, "CSC 101": 3.0}
    profile = lambda *blocks: to_profile({"requirements": list(blocks), "catalog_term": "Spring 2025", "gpa": None}, wanted, units)
    assert profile(calc1, calc2, cs)["transfer_units"] == 11
    summary = block("Courses Completed / In-Progress", "other", "info", [transfer_row("MATH 100TR", 4.0), transfer_row("CSC 100TR", 3.0)])
    assert profile(calc1, cs, summary)["transfer_units"] == 7  # the same rows again, in a summary list
    both = block("Courses Completed / In-Progress", "other", "info", [transfer_row("ENG 100TR", 3.0), transfer_row("ENG 100TR", 3.0)])
    assert profile(both)["transfer_units"] == 6  # two rows in one list are two courses
