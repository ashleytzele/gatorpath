"""Anonymous usage totals and feedback for the website (D37). A day's count per event, a one-way hash that says "this
visitor came today" and is deleted the next day, and the messages students choose to send. Nothing here identifies a
student: no profile, grades, plan, email or name. Imported only by api.py: server.py and engine/ never see it."""

import argparse
import hashlib
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

EVENTS = frozenset({"visit", "visitor", "dpr_import", "plan_built", "ai_question", "feedback"})
MAX_MESSAGE = 2000
MAX_STORED = 5000  # messages kept; past this a flood can't fill the disk
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # everything unprintable but tab and newline
REF = re.compile(r"[a-z0-9_-]{1,20}")
_salt: tuple[date, str] = (date.min, "")  # ponytail: in memory, so a restart counts a returning visitor once more that day


def db_path() -> Path:
    return Path(os.environ.get("GATORPATH_STATS_DB") or Path(__file__).parents[2] / "data/stats.db")


def _open() -> sqlite3.Connection:
    db = sqlite3.connect(db_path())
    db.executescript("""
        create table if not exists counts (day text, event text, program text, ref text, n integer,
                                           primary key (day, event, program, ref));
        create table if not exists seen (day text, h text, primary key (day, h));
        create table if not exists feedback (day text, message text);
    """)
    return db


def _bump(db: sqlite3.Connection, event: str, program: str = "", ref: str = "") -> None:
    db.execute("insert into counts values (?, ?, ?, ?, 1) on conflict (day, event, program, ref) do update set n = n + 1",
               (date.today().isoformat(), event, program, ref))


def count(event: str, program: str = "", ref: str = "") -> None:
    """Adds 1 to today's total. A failure to write is dropped: a count must never break what a student is doing."""
    if event not in EVENTS:
        raise ValueError(f"unknown event {event!r}")
    ref = ref.lower()
    try:
        with closing(_open()) as db, db:
            _bump(db, event, program, ref if REF.fullmatch(ref) else "")
    except (sqlite3.Error, OSError):
        pass


def seen(who: str, agent: str) -> None:
    """Counts a visitor once a day per network address and browser (campus students share addresses, and one person
    has several devices: this is visitors, not people)."""
    global _salt
    today = date.today()
    if _salt[0] != today:
        _salt = (today, secrets.token_hex(16))
    digest = hashlib.sha256(f"{_salt[1]}{who}|{agent}".encode()).hexdigest()
    try:
        with closing(_open()) as db, db:
            db.execute("delete from seen where day < ?", (today.isoformat(),))
            if db.execute("insert or ignore into seen values (?, ?)", (today.isoformat(), digest)).rowcount:
                _bump(db, "visitor")
    except (sqlite3.Error, OSError):
        pass


def add_feedback(message: str) -> bool:
    """Keeps the first 2000 characters. False when there is nothing to keep, the store is full, or it can't be written."""
    message = CONTROL.sub("", message).strip()[:MAX_MESSAGE]  # a message is read in the owner's terminal: no escape codes
    if not message:
        return False
    try:
        with closing(_open()) as db, db:
            if db.execute("select count(*) from feedback").fetchone()[0] >= MAX_STORED:
                return False
            db.execute("insert into feedback values (?, ?)", (date.today().isoformat(), message))
            _bump(db, "feedback")
        return True
    except (sqlite3.Error, OSError):
        return False


def report(days: int = 30, feedback: bool = False) -> dict:
    """The last `days` days, newest first, plus totals, the top majors, where visits came from and (only when asked)
    the feedback text."""
    days = max(1, min(days, 366))
    with closing(_open()) as db:
        rows = db.execute("select day, event, program, ref, n from counts order by day desc").fetchall()
        keep = sorted({r[0] for r in rows}, reverse=True)[:days]
        rows = [r for r in rows if r[0] in keep]
        per_day = {d: dict.fromkeys(sorted(EVENTS), 0) for d in keep}
        majors: dict[str, int] = {}
        refs: dict[str, int] = {}
        for day, event, program, ref, n in rows:
            per_day[day][event] += n
            if event == "plan_built" and program:
                majors[program] = majors.get(program, 0) + n
            if event == "visit" and ref:
                refs[ref] = refs.get(ref, 0) + n
        out = {
            "days": [{"day": d, **per_day[d]} for d in keep],
            "totals": {e: sum(per_day[d][e] for d in keep) for e in sorted(EVENTS)},
            "majors": dict(sorted(majors.items(), key=lambda kv: -kv[1])[:20]),
            "refs": dict(sorted(refs.items(), key=lambda kv: -kv[1])),
        }
        if feedback:
            out["feedback"] = [{"day": d, "message": m} for d, m in
                               db.execute("select day, message from feedback order by rowid desc limit 200")]
    return out


def main() -> None:
    """`uv run python -m gatorpath.stats [--days N] [--feedback]`: the numbers, as lines."""
    ap = argparse.ArgumentParser(description="GatorPath's anonymous usage totals")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--feedback", action="store_true", help="also print the feedback messages")
    args = ap.parse_args()
    got = report(args.days, args.feedback)
    print("totals:", ", ".join(f"{e} {n}" for e, n in got["totals"].items()))
    for row in got["days"]:
        print(row["day"], " ".join(f"{e}={row[e]}" for e in sorted(EVENTS)))
    for title in ("majors", "refs"):
        if got[title]:
            print(f"{title}:", ", ".join(f"{k} {v}" for k, v in got[title].items()))
    for m in got.get("feedback", []):
        print(f"feedback {m['day']}: {m['message']}")


if __name__ == "__main__":
    main()
