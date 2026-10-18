"""DPR print -> requirements and profile fields, from the synthetic fixture (real layout, fake name/ID, invented courses)."""

from pathlib import Path

from gatorpath.dpr import parse, to_profile

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
