"""Class Search -> offering rows (ARCHITECTURE §5, §6.1). Offline, once per term, cached, polite (AGENTS.md etiquette).

The public search keeps the query in the session: GET .../classsearch/results?term=2257&classCategory=REG&subject=CSC,
then GET .../searchresultsjson returns that search's sections as DataTables JSON ("aaData" rows of HTML cells).
"""

import argparse
import json
import re
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from gatorpath.engine.planner import next_term, term_key
from gatorpath.ingest.bulletin import CODE

BASE = "https://webapps.sfsu.edu/public/classservices"
USER_AGENT = "GatorPath/0.1 (SF State degree-planning tool; +https://github.com/ashleytzele/gatorpath)"
DELAY = 2.0  # seconds between requests (AGENTS.md: at least 2)
TERM_DIGIT = {"spring": 3, "summer": 5, "fall": 7}  # PeopleSoft term code: 2 + YY + digit, e.g. 2257 = fall 2025
SECTION = re.compile(rf"({CODE}) \[(\w+)[^\]]*\]")  # Spring 2027 prints one "ERTH 870 [01`]"

DETAILS = {"class_nbr": "text", "meetings": "text", "dates": "text", "instructor": "text", "seats_open": "integer",
           "waitlist_open": "integer", "attributes": "text"}  # 2026-10-26 (get_sections); meetings, attributes: JSON
SCHEMA = """
create table if not exists offering(term text, code text, section text, component text, mode text, enrolled integer,
  primary key (term, code, section, component));
create table if not exists offering_scrape(term text, subject text, sections integer, scraped_at text,
  primary key (term, subject));
"""


def term_code(term: str) -> str:
    year, season = term_key(term)[0], term[5:]
    return f"2{year % 100:02d}{TERM_DIGIT[season]}"


def recent_terms(today: date, years: int = 4, through: str | None = None) -> list[str]:
    """Spring/summer/fall terms of the last `years` years, through the current term ('2023-spring' … '2026-fall') or
    `through`, a next term whose schedule is out ('2027-spring')."""
    current = f"{today.year}-{'fall' if today.month >= 8 else 'summer' if today.month >= 6 else 'spring'}"
    term, out = f"{today.year - years}-{current[5:]}", []
    while term_key(term) < term_key(through or current):
        term = next_term(term, True)
        out.append(term)
    return out


def text(cell: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()


def instructors(cell: str) -> str:
    """One <div> per instructor (co-taught, or "Pat Example" and "To be announced"), so the names stay apart."""
    return ", ".join(dict.fromkeys(n for n in map(text, re.findall(r"<div[^>]*>(.*?)</div>", cell)) if n)) or text(cell)


def meetings(cell: str) -> list[dict]:
    """One {days, time, where} per meeting; an online one has no time, and "To be arranged" is all some print."""
    out = []
    for part in cell.split("<hr/>"):
        divs = [text(d) for d in re.findall(r"<div[^>]*>([^<]*)</div>", part)]
        keys = ("days", "time", "where") if len(divs) == 3 else ("days", "where") if len(divs) == 2 else ("time",)
        if m := {k: v for k, v in zip(keys, divs if len(divs) <= 3 else [" ".join(divs)]) if v}:
            out.append(m)
    return out


def parse(rows: list[list[str]], term: str) -> list[dict]:
    """aaData rows -> offering dicts. Summer rows carry an extra date column, so trailing cells are read from the end:
    mode, instructor, then (the page's own comment) remainingSeats, remainingWaitList, classSection, enrollTotal. There
    is no capacity column."""
    out = []
    for r in rows:
        if f"/detail/{term_code(term)}/" not in r[0]:
            raise ValueError(f"row {text(r[0])!r} isn't from {term}; the session served another search")
        m = SECTION.match(text(r[0]))
        if not m:
            raise ValueError(f"unexpected course cell {text(r[0])!r}")
        mode = text(r[-7]).split(" (see description)")[0]
        out.append({"term": term, "code": m[1], "section": m[2], "component": text(r[1]), "mode": mode,
                    "enrolled": int(text(r[-2]) or 0), "class_nbr": text(r[4]), "meetings": meetings(r[6]),
                    "dates": text(r[7]) if len(r) == 15 else None, "instructor": instructors(r[-6]),
                    "seats_open": int(text(r[-5]) or 0), "waitlist_open": int(text(r[-4]) or 0),
                    "attributes": [n for n in map(text, r[5].split("<hr/>")) if n]})
    return out


def fetch(client: httpx.Client, term: str, subject: str, cache: Path) -> tuple[list[list[str]], str]:
    """One search, from the cache when it's there (AGENTS.md: cache everything), and when it was fetched."""
    path = cache / f"{term}-{subject}.json"
    if not path.exists():
        params = {"term": term_code(term), "classCategory": "REG", "subject": subject}
        client.get(f"{BASE}/classsearch/results", params=params).raise_for_status()
        time.sleep(DELAY)
        resp = client.get(f"{BASE}/searchresultsjson")
        resp.raise_for_status()
        time.sleep(DELAY)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(resp.text)
    fetched = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    return json.loads(path.read_text())["aaData"], fetched


def write_offerings(db_path: str | Path, term: str, subject: str, rows: list[dict], scraped_at: str | None = None) -> None:
    """Replaces one (term, subject) in place, and records that it was checked (even with no sections) and when."""
    con = sqlite3.connect(db_path)
    with con:
        con.executescript(SCHEMA)
        have = {r[1] for r in con.execute("pragma table_info(offering)")}
        for col, kind in DETAILS.items():  # a catalog.db from before the section details
            if col not in have:
                con.execute(f"alter table offering add column {col} {kind}")
        cols = ["term", "code", "section", "component", "mode", "enrolled", *DETAILS]
        con.execute("delete from offering where term = ? and code like ?", (term, f"{subject} %"))
        con.executemany(f"insert or replace into offering ({', '.join(cols)}) values ({', '.join(':' + c for c in cols)})",
                        [r | {k: json.dumps(r[k]) for k in ("meetings", "attributes")} for r in rows])
        con.execute("insert or replace into offering_scrape values (?, ?, ?, ?)",
                    (term, subject, len(rows), scraped_at or datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape Class Search offering history into data/catalog.db.")
    ap.add_argument("--subjects", default="CSC,MATH,PHYS")
    ap.add_argument("--years", type=int, default=4, help="how many years back, through the current term")
    ap.add_argument("--through", help="last term, when the next term's schedule is out (e.g. 2027-spring)")
    ap.add_argument("--db", default="data/catalog.db")
    ap.add_argument("--cache", default="data/cache/offerings")
    args = ap.parse_args()
    terms = recent_terms(date.today(), args.years, args.through)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
        for subject in args.subjects.upper().split(","):
            for term in terms:
                cells, fetched = fetch(client, term, subject, Path(args.cache))
                rows = parse(cells, term)
                write_offerings(args.db, term, subject, rows, fetched)
                print(f"{term} {subject}: {len(rows)} sections, {len({r['code'] for r in rows})} courses")


if __name__ == "__main__":
    main()
