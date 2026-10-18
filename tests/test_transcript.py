"""Unofficial transcript text -> course rows, from the synthetic fixture (real layout, fake name/ID)."""

from pathlib import Path

from gatorpath.transcript import parse

FIXTURE = (Path(__file__).parent / "fixtures/transcript_synthetic.txt").read_text()


def test_fixture_rows_terms_and_in_progress():
    got = parse(FIXTURE)
    assert [(r["code"], r["grade"], r["units"], r["term"]) for r in got["completed"]] == [
        ("CSC 101", "B+", 3.0, "2024-fall"), ("MATH 226", "A-", 4.0, "2024-fall"), ("ENG 114", "C", 3.0, "2024-fall"),
        ("CSC 215", "A", 4.0, "2025-spring"), ("MATH 227", "B", 4.0, "2025-spring")]  # SP2025 rows end before a page break
    assert got["in_progress"] == ["CSC 220", "CSC 300GW", "I R 205"]  # blank grade, 0.00 earned; 'I R' has a space
    assert got["transfer_units"] == 12 and "totals only" in got["warnings"][0]


def test_bulletin_grade_symbols_unknown_terms_and_bad_rows_are_flagged_not_guessed():
    # No real sample with these rows yet (TASKS phase 6): the same columns with other grade symbols (p.2403)
    extra = """
                                                                     SU2025
CSC           230          DISCRETE MATH STRUCTURES                                        3.00       3.00     CR               0.00
PHIL          101          INTRODUCTION TO PHILOSOPHY                                      3.00       0.00     W                0.00
MATH          324          PROBABILITY AND STATISTICS                                      3.00       0.00     I                0.00
                                                                     WI2026
COMM          150          FUNDAMENTALS OF ORAL COMM                                       3.00       3.00     A                12.00
BIOL          100          HUMAN BIOLOGY                                                   3.00       3.00
"""
    got = parse(FIXTURE + extra)
    summer = [(r["code"], r["grade"], r.get("term")) for r in got["completed"][5:]]
    assert summer == [("CSC 230", "CR", "2025-summer"), ("PHIL 101", "W", "2025-summer"), ("MATH 324", "I", "2025-summer"),
                      ("COMM 150", "A", None)]
    assert any(w.startswith("Term WI2026: not a fall, spring or summer code") for w in got["warnings"])
    assert any(w == "Term WI2026, course row 2: not in the expected layout, so it was left out; add it by hand"
               for w in got["warnings"])
    assert "HUMAN BIOLOGY" not in str(got)  # a row it can't read is reported by position, never its text


def test_not_a_transcript():
    assert parse("Some other PDF\nwith text")["error"] == "unrecognized_transcript_format"
