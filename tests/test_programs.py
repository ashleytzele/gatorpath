"""Bulletin program pages -> source text -> drafted rules (gatorpath.ingest.programs). Pages are built from the 2026-27
Bulletin's own running heads and listing lines (pdftotext -raw), so no PDF is needed."""

import sys

import pytest
import yaml

from gatorpath.ingest import programs as P

NAME = "San Francisco State University Bulletin 2026-2027"
APPLIED = "Bachelor of Science in Applied Mathematics"
LIBERAL = "Bachelor of Arts in Mathematics: Concentration in Mathematics for Liberal Arts"


def right(head: list[str], body: str, n: int) -> str:
    """An odd (right-hand) page: the head, wrapped or not, then the Bulletin's name."""
    lines = [f"{head[0]} {NAME}"] if len(head) == 1 else head + [NAME]
    return "\n".join(lines + [body, str(n)])


def left(head: list[str], body: str, n: int) -> str:
    """An even (left-hand) page: the Bulletin's name, then the head; a wrapped head's second line follows."""
    return "\n".join([f"{NAME} {head[0]}"] + head[1:] + [body, str(n)])


CUT = "Bachelor of Arts in Mathematics: Concentration in Mathematics for Liberal"  # where a wrapped head breaks
PAGES = [
    "\n".join(["Majors", f"• {APPLIED} (p. 2129)", "• Bachelor of Arts in Mathematics: Concentration in Liberal",
               "Arts (p. 2111)", "• Bachelor of Science in Statistics (p. 2141)", "2089"]),
    right([CUT, "Arts"], "Mathematics (B.A.): Concentration in Mathematics for Liberal Arts — 43 units", 2111),
    left([CUT, "Arts"], "Required Courses", 2112),
    right([CUT, "Arts"], "Electives", 2113),
    left([CUT, "Arts Roadmap – Quantitative Reasoning"], "First Semester", 2114),
    right([APPLIED], "Applied Mathematics (B.S.) — 55 units minimum", 2129),
    left([APPLIED], "Electives (15 units)", 2130),
    right([APPLIED], "Remedial courses are not transferable", 2131),
    left([f"{APPLIED} Roadmap – Quantitative", "Reasoning Category 1/2"], "First Semester", 2132),
    right([f"{APPLIED} – MATH Associate Degree for", "Transfer (ADT) Roadmap"], "First Semester", 2133),
    left(["Applied Mathematics BS + Mathematics MA SF State Scholars Roadmap"], "Third Year", 2134),
    right(["Bachelor of Science in Statistics"], "Statistics (B.S.) — 55 units minimum", 2141),
]


def test_running_heads_on_both_sides_and_wrapped():
    assert P.head(PAGES[5]) == P.head(PAGES[6]) == APPLIED
    assert P.head(PAGES[9]) == f"{APPLIED} – MATH Associate Degree for Transfer (ADT) Roadmap"  # right page: whole head
    assert P.head(PAGES[1]) == LIBERAL and P.head(PAGES[2]) == CUT  # a left page: only a wrapped head's first line
    assert P.printed(PAGES[5]) == 2129 and P.head(PAGES[0]) == ""


def test_index_finds_requirement_and_roadmap_pages():
    got = {p["title"]: p for p in P.index(PAGES)}
    assert got[APPLIED]["pages"] == [2129, 2130, 2131] and got[APPLIED]["roadmap_pages"] == [2132, 2133]  # Scholars: own head
    # the department list shortens it to "Liberal Arts": the listed page's own heading is the title; its left-hand
    # roadmap page is told apart by the head's second line
    assert got[LIBERAL]["pages"] == [2111, 2112, 2113] and got[LIBERAL]["roadmap_pages"] == [2114]
    assert got["Bachelor of Science in Statistics"]["pages"] == [2141]


def test_program_ids():
    have = {"Bachelor of Science in Applied Mathematics": "bs-applied-math"}
    assert P.program_id(APPLIED, have) == "bs-applied-math"
    assert P.program_id("Bachelor of Arts in English: Concentration in Literature", have) == "ba-english-literature"
    assert P.program_id("Bachelor of Music: Concentration in Jazz/Ethnomusicology", have) == "bm-jazz-ethnomusicology"
    assert P.program_id("Bachelor of Arts in Chinese: Concentration in Chinese Literature & Linguistics", have) == \
        "ba-chinese-chinese-literature-and-linguistics"


def test_source_text_marks_each_page():
    text = P.source_text(PAGES, [2129, 2130])
    assert text.startswith("=== p.2129 ===\nApplied Mathematics (B.S.) — 55 units minimum\n=== p.2130 ===")
    assert NAME not in text and P.source_pages(text) == {2129, 2130}


def test_prompt_holds_the_rules_vocabulary_examples_and_text():
    text = P.prompt(APPLIED, "bs-applied-math", "2026-27", "=== p.2129 ===\nMATH 226 Calculus I 4\n", ["program: bs-cs\n"])
    assert "### 6.2 Hand-written rules" in text and "```yaml\nprogram: bs-cs\n```" in text
    assert text.endswith("=== p.2129 ===\nMATH 226 Calculus I 4\n") and "unparsed: true" in text


def test_a_draft_is_parsed_checked_and_never_verified(tmp_path):
    answer = tmp_path / "answer.txt"
    answer.write_text("Here it is:\n```yaml\nprogram: anything\ntitle: x\nverified: true\ntotal_units: 4\ngroups:\n"
                      "  - {id: calc, all_of: [MATH 226], source: \"p.2129\", quote: \"MATH 226 Calculus I\"}\n```\n")
    client = f"{sys.executable} -c \"import sys; sys.stdin.read(); print(open(sys.argv[1]).read())\" {answer}"
    got = P.draft(APPLIED, "bs-applied-math", "2026-27", "=== p.2129 ===\nMATH 226 Calculus I 4\n", client)
    assert got["program"] == "bs-applied-math" and got["title"] == APPLIED and got["catalog_year"] == "2026-27"
    assert got["verified"] is False and got["verified_by"] is None and got["drafted_by"].endswith(str(P.date.today()))
    assert got["groups"][0]["all_of"] == ["MATH 226"]
    with pytest.raises(ValueError):
        P.parse_draft("I can't do that.")
    # a title's unquoted colon doesn't lose the draft, at any depth
    assert P.parse_draft("```yaml\ntitle: Bachelor of Music: Composition\nvariants:\n  first-time:\n    title: B.M.: "
                         "Composition Roadmap\n```", "variants") == {
        "title": "Bachelor of Music: Composition", "variants": {"first-time": {"title": "B.M.: Composition Roadmap"}}}
    assert yaml.safe_load(yaml.safe_dump(got)) == got


def test_a_roadmap_draft_is_written_against_the_rules_and_never_verified(tmp_path):
    answer = tmp_path / "answer.txt"
    answer.write_text("```yaml\nprogram: x\nverified: true\nvariants:\n  first-time:\n    semesters: []\n```\n")
    client = f"{sys.executable} -c \"import sys; sys.stdin.read(); print(open(sys.argv[1]).read())\" {answer}"
    university = {"groups": [{"id": "ge_1a", "from": {"ge_area": "1A"}}, {"id": "ush", "from": {"ge_area": "USH"}}]}
    text = P.roadmap_prompt(APPLIED, "bs-applied-math", "2026-27", "=== p.2132 ===\nFirst Semester\n", "program: bs-x\n",
                            ["1A", "USH"], [])
    assert "one of 1A, USH" in text and "```yaml\nprogram: bs-x\n```" in text and "qr-1-2, qr-3-4, first-time, adt" in text
    got = P.draft_roadmap(APPLIED, "bs-applied-math", "2026-27", "=== p.2132 ===\n", "program: bs-x\n", university, client)
    assert got["program"] == "bs-applied-math" and got["catalog_year"] == "2026-27" and got["verified"] is False
    assert list(got)[:2] == ["program", "catalog_year"] and got["variants"] == {"first-time": {"semesters": []}}
    with pytest.raises(ValueError):
        P.parse_draft("```yaml\ngroups: []\n```", "variants")
    answer.write_text("```yaml\nvariants:\n  adt: {title: Bachelor of Music: Composition}\n```")  # unquoted ": "
    keep = tmp_path / "kept.yaml"
    with pytest.raises(yaml.YAMLError):
        P.draft_roadmap(APPLIED, "bs-applied-math", "2026-27", "", "", university, client, keep)
    assert "Bachelor of Music: Composition" in keep.read_text()  # kept for a person, not lost
