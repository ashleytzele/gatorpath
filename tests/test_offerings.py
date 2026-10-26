"""Class Search parsing and offering history. Rows copy the real searchresultsjson shape (fall: 14 cells, summer: 15
with a date column); names are fake."""

import json
from datetime import date
from pathlib import Path

import pytest

from gatorpath import db
from gatorpath.ingest.bulletin import write_catalog
from gatorpath.ingest.offerings import parse, recent_terms, term_code, write_offerings

ROOT = Path(__file__).parents[1]
ROWS = json.loads((ROOT / "tests/fixtures/catalog_rows.json").read_text())


def row(term: str, course: str, component: str = "LEC", summer: bool = False, mode: str = "In-Person") -> list[str]:
    link = f'<a href="/public/classservices/classsearch/detail/{term_code(term)}/REG/7557" class="underline" >{course}</a>'
    cells = [link, component, "Network Security", "3", "7557", "<span>Upper-Division</span>",
             "<div class='row'><div>We </div><div>7:00 PM - 9:45 PM</div><div>Hensill Hall 543</div></div>",
             f'{mode}<div><span class="description-toggle">(see description)</span></div>',
             "<div> Pat Example</div>", "0", "0", course.split("[")[1].rstrip("]"), "40", ""]
    return cells[:7] + ["Jun 2, 2025 - Aug 8, 2025"] + cells[7:] if summer else cells


def test_term_codes_and_recent_terms():
    assert [term_code(t) for t in ("2025-fall", "2026-summer", "2027-spring")] == ["2257", "2265", "2273"]
    terms = recent_terms(date(2026, 10, 17))
    assert (terms[0], terms[-1], len(terms)) == ("2023-spring", "2026-fall", 12)
    assert recent_terms(date(2026, 10, 26), through="2027-spring")[-2:] == ["2026-fall", "2027-spring"]  # published


def test_parse_reads_both_row_shapes_and_rejects_another_terms_rows():
    got = parse([row("2025-fall", "CSC 653 [01]"), row("2025-fall", "CSC 300GW [02]", "SEM")], "2025-fall")
    assert got[1] == {"term": "2025-fall", "code": "CSC 300GW", "section": "02", "component": "SEM",
                      "mode": "In-Person", "enrolled": 40}
    [summer] = parse([row("2025-summer", "CSC 642 [02]", summer=True)], "2025-summer")
    assert (summer["code"], summer["section"], summer["mode"], summer["enrolled"]) == ("CSC 642", "02", "In-Person", 40)
    with pytest.raises(ValueError, match="isn't from 2025-spring"):
        parse([row("2025-fall", "CSC 653 [01]")], "2025-spring")


def test_offering_history_counts_runs_per_season(tmp_path):
    path = tmp_path / "catalog.db"
    write_catalog(path, "2026-27", ROWS)
    for term in ("2024-fall", "2025-spring", "2025-fall", "2026-spring"):
        write_offerings(path, term, "CSC", parse([row(term, "CSC 101 [01]")] + ([row(term, "CSC 653 [01]")]
                                                  if term.endswith("fall") else []), term))
    cat = db.load_catalog(path, "2026-27")
    assert cat["CSC 653"]["offered"] == {"fall": [2, 2], "spring": [0, 2], "summer": [0, 0],
                                         "since": "2024-fall", "until": "2026-spring", "last": "2025-fall",
                                         "schedule": {"2024-fall": True, "2025-spring": False, "2025-fall": True,
                                                      "2026-spring": False}}
    assert cat["CSC 101"]["offered"]["spring"] == [2, 2]
    assert "offered" not in cat["MATH 226"]  # MATH wasn't scraped: unknown, not "never"


def test_offering_history_marks_seasons_whose_last_run_was_only_online(tmp_path):
    # F-1: "only one course (or 3 units) will count toward the enrollment requirement" (international.sfsu.edu/rcl)
    path = tmp_path / "catalog.db"
    write_catalog(path, "2026-27", ROWS)
    sections = {"2024-fall": [row("2024-fall", "CSC 653 [01]"), row("2024-fall", "CSC 101 [01]", mode="Online synchronous")],
                "2025-spring": [row("2025-spring", "CSC 653 [01]", mode="Hybrid (Online synchronous with occasional in-person)")],
                "2025-fall": [row("2025-fall", "CSC 653 [01]", mode="Online asynchronous"),
                              row("2025-fall", "CSC 101 [01]", mode="Online synchronous"), row("2025-fall", "CSC 101 [02]")]}
    for term, rows in sections.items():
        write_offerings(path, term, "CSC", parse(rows, term))
    cat = db.load_catalog(path, "2026-27")
    assert cat["CSC 653"]["offered"]["online_only"] == ["fall"]  # the latest fall run; hybrid isn't fully online
    assert "online_only" not in cat["CSC 101"]["offered"]  # one in-person section in its last run is enough
