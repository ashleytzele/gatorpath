"""The anonymous counters (stats.py): daily totals, a one-day visitor hash, feedback. Always on a temporary file."""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from gatorpath import stats

SRC = Path(__file__).parents[1] / "src/gatorpath"


@pytest.fixture
def stats_file(tmp_path):  # the same file conftest.py points every test at
    return tmp_path / "stats.db"


def test_counts_add_up_per_day_event_and_program():
    for _ in range(3):
        stats.count("plan_built", "cs-bs")
    stats.count("plan_built", "bio-bs")
    got = stats.report()
    assert got["totals"]["plan_built"] == 4
    assert got["majors"] == {"cs-bs": 3, "bio-bs": 1}


def test_unknown_event_is_refused():
    with pytest.raises(ValueError):
        stats.count("login")


def test_ref_is_cleaned():
    stats.count("visit", ref="Flyer")
    assert stats.report()["refs"] == {"flyer": 1}
    stats.count("visit", ref="<script>x")
    stats.count("visit", ref="a" * 21)
    assert stats.report()["refs"] == {"flyer": 1}  # the other two land under "", which the report leaves out
    assert stats.report()["totals"]["visit"] == 3


def test_a_visitor_counts_once_a_day():
    stats.seen("1.2.3.4", "Safari")
    stats.seen("1.2.3.4", "Safari")
    assert stats.report()["totals"]["visitor"] == 1
    stats.seen("1.2.3.4", "Chrome")
    assert stats.report()["totals"]["visitor"] == 2
    stats.seen("5.6.7.8", "Safari")
    assert stats.report()["totals"]["visitor"] == 3


def test_yesterdays_hashes_are_deleted(stats_file):
    stats.seen("1.2.3.4", "Safari")
    with sqlite3.connect(stats_file) as db:
        db.execute("update seen set day = ?", ((date.today() - timedelta(days=1)).isoformat(),))
    stats.seen("9.9.9.9", "x")
    with sqlite3.connect(stats_file) as db:
        assert db.execute("select count(*) from seen").fetchone()[0] == 1


def test_feedback_is_cut_refused_empty_and_capped(stats_file):
    assert stats.add_feedback("x" * 2500) is True
    assert len(stats.report(feedback=True)["feedback"][0]["message"]) == 2000
    assert stats.add_feedback("  ") is False
    with sqlite3.connect(stats_file) as db:
        db.executemany("insert into feedback values (?, ?)", [("2026-01-01", "m")] * 5000)
    assert stats.add_feedback("hi") is False


def test_report_hides_feedback_text_unless_asked():
    stats.add_feedback("hello")
    assert "feedback" not in stats.report()  # the per-day feedback count lives under days and totals
    assert stats.report()["totals"]["feedback"] == 1
    assert stats.report(feedback=True)["feedback"][0]["message"] == "hello"


def test_a_broken_stats_file_never_raises(monkeypatch):
    monkeypatch.setenv("GATORPATH_STATS_DB", "/nonexistent-dir/x.db")
    stats.count("visit")
    stats.seen("a", "b")
    assert stats.add_feedback("x") is False


def test_the_tables_hold_no_student_data(stats_file):
    stats.count("visit")
    stats.seen("a", "b")
    stats.add_feedback("x")
    with sqlite3.connect(stats_file) as db:
        columns = {t: {r[1] for r in db.execute(f"pragma table_info({t})")}
                   for (t,) in db.execute("select name from sqlite_master where type = 'table'")}
    assert columns == {"counts": {"day", "event", "program", "ref", "n"}, "seen": {"day", "h"},
                       "feedback": {"day", "message"}}


def test_server_and_engine_never_import_stats():
    files = [SRC / "server.py", *(SRC / "engine").glob("*.py")]
    assert files and not [f.name for f in files if "stats" in f.read_text()]
