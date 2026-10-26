"""Read-only access to data/catalog.db: course rows as the plain dicts `engine/` takes."""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from gatorpath.engine.planner import term_key
from gatorpath.ingest.bulletin import CODE

# ponytail: wording match on the description. Upgrade: parse "for a total of N units" and cap repeats.
REPEATABLE = re.compile(r"may be repeated|may repeat when|repeatable (?:once )?for credit", re.I)


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Read-only; a plain connect would silently create an empty file."""
    if not Path(db_path).exists():
        raise FileNotFoundError(f"{db_path} not built; run: uv run python -m gatorpath.ingest.bulletin data/raw/bulletin-2026-27.pdf")
    return sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)  # as_uri escapes '#', '?', '%'


def sections(db_path: str | Path, term: str, codes: list[str]) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Class Search sections of `codes` in one term, and {subject: scraped_at} for the subjects scraped that term."""
    con = connect(db_path)
    if not con.execute("select 1 from sqlite_master where name = 'offering_scrape'").fetchone():
        con.close()
        return {}, {}
    scraped = dict(con.execute("select subject, scraped_at from offering_scrape where term = ?", (term,)).fetchall())
    con.row_factory = sqlite3.Row
    rows = con.execute(f"select * from offering where term = ? and code in ({', '.join('?' * len(codes))}) "
                       "order by code, section, component", (term, *codes)).fetchall()
    con.close()
    out: dict[str, list[dict]] = {}
    for r in map(dict, rows):
        r |= {k: json.loads(r[k]) for k in ("meetings", "attributes") if r.get(k)}  # JSON lists (ingest.offerings)
        out.setdefault(r["code"], []).append({k: v for k, v in r.items() if k not in ("term", "code") and v is not None})
    return out, scraped


def offered(con: sqlite3.Connection) -> dict[str, dict]:
    """{code: {fall: [ran, checked], spring: …, summer: …, since, until, last, schedule: {term: ran}}} from Class Search
    history (ingest.offerings), for every catalog course whose subject was scraped. Subjects never scraped are left
    out: unknown, not "never"."""
    if not con.execute("select 1 from sqlite_master where name = 'offering_scrape'").fetchone():
        return {}
    checked: dict[str, list[str]] = {}
    for term, subject in con.execute("select term, subject from offering_scrape"):
        checked.setdefault(subject, []).append(term)
    ran: dict[str, set[str]] = {}
    modes: dict[tuple[str, str], set[str]] = {}
    for term, code, mode in con.execute("select term, code, mode from offering"):
        ran.setdefault(code, set()).add(term)
        modes.setdefault((code, term), set()).add(mode or "")
    out = {}
    for (code,) in con.execute("select distinct code from course"):
        terms = checked.get(code.rsplit(" ", 1)[0])
        if terms:
            runs = ran.get(code, set())
            # Seasons whose latest run had only fully online sections ("Online synchronous", …; hybrid isn't): F-1
            # students can count only 3 such units (f1_final_term.online_units_count).
            latest = {s: max((t for t in runs if t.endswith(s)), key=term_key, default=None) for s in ("fall", "spring", "summer")}
            online = [s for s, t in latest.items() if t and all(m.startswith("Online") for m in modes[code, t])]
            out[code] = {s: [sum(t in runs for t in terms if t.endswith(s)), sum(t.endswith(s) for t in terms)]
                         for s in ("fall", "spring", "summer")} | {"since": min(terms, key=term_key),
                                                                    "until": max(terms, key=term_key),
                                                                    "last": max(runs, key=term_key, default=None),
                                                                    "schedule": {t: t in runs for t in sorted(terms, key=term_key)}}
            if online:
                out[code]["online_only"] = online
    return out


def load_catalog(db_path: str | Path, catalog_year: str, codes: set[str] | None = None) -> dict[str, dict]:
    """{code: {title, units_min, units_max, grading, ge_areas, paired, repeatable, source_page, offered?, crosslisted?}}"""
    con = connect(db_path)
    history = offered(con)
    paired = {c for row in con.execute(
        "select code_a, code_b from course_link where catalog_year = ? and kind = 'paired'", (catalog_year,)) for c in row}
    twins: dict[str, list[str]] = {}  # "MUS 130/TH A 131": one course under two codes
    for a, b in con.execute("select code_a, code_b from course_link where catalog_year = ? and kind = 'crosslisted'",
                            (catalog_year,)):
        twins.setdefault(a, []).append(b)
        twins.setdefault(b, []).append(a)
    rows = con.execute("select code, title, units_min, units_max, grading, ge_areas, description, source_page from course "
                       "where catalog_year = ? and (? is null or code in (select value from json_each(?))) order by code",
                       (catalog_year, *[None if codes is None else json.dumps(sorted(codes))] * 2)).fetchall()
    con.close()
    return {
        code: {
            "title": title, "units_min": lo, "units_max": hi, "grading": grading, "ge_areas": json.loads(ge),
            "paired": code in paired,
            "repeatable": bool(REPEATABLE.search(description or "")),
            "source_page": page,
        } | ({"offered": history[code]} if code in history else {}) | (
            {"crosslisted": sorted(twins[code])} if code in twins else {})
        for code, title, lo, hi, grading, ge, description, page in rows
    }


def load_prereqs(db_path: str | Path, catalog_year: str) -> dict[str, dict]:
    """{code: {title, units_min, units_max, source_page, raw_text, expr, status, needs_permission}} for every course."""
    con = connect(db_path)
    rows = con.execute("select c.code, c.title, c.units_min, c.units_max, c.source_page, p.raw_text, p.expr, p.status, "
                       "p.needs_permission from course c join prereq p using (catalog_year, code) where c.catalog_year = ?",
                       (catalog_year,)).fetchall()
    con.close()
    return {code: {"title": title, "units_min": lo, "units_max": hi, "source_page": page, "raw_text": raw,
                   "expr": json.loads(expr) if expr else None, "status": status, "needs_permission": bool(perm)}
            for code, title, lo, hi, page, raw, expr, status, perm in rows}


def get_course(db_path: str | Path, catalog_year: str, code: str) -> dict | None:
    """Full course record (ARCHITECTURE §7.1) or None."""
    con = connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("select * from course where catalog_year = ? and code = ?", (catalog_year, code)).fetchone()
    if row is None:
        con.close()
        return None
    p = con.execute("select raw_text, expr, status, needs_permission from prereq where catalog_year = ? and code = ?",
                    (catalog_year, code)).fetchone()
    links = con.execute("select case when code_a = ? then code_b else code_a end, kind from course_link "
                        "where catalog_year = ? and ? in (code_a, code_b) order by 1", (code, catalog_year, code)).fetchall()
    con.close()
    course = dict(row) | {"ge_areas": json.loads(row["ge_areas"])}
    course["prereq"] = dict(p) | {"expr": json.loads(p["expr"]) if p["expr"] else None,
                                  "needs_permission": bool(p["needs_permission"])}
    course["links"] = [{"code": c, "kind": kind} for c, kind in links]
    course["repeatable"] = bool(REPEATABLE.search(course["description"] or ""))
    return course


def descriptions(db_path: str | Path, catalog_year: str, codes: list[str]) -> dict[str, str]:
    con = connect(db_path)
    rows = con.execute("select code, description from course where catalog_year = ? and code in (select value from json_each(?))",
                       (catalog_year, json.dumps(codes))).fetchall()
    con.close()
    return dict(rows)


def search_courses(db_path: str | Path, catalog_year: str, query: str) -> list[dict]:
    """FTS5 keyword search over code/title/description, best first. Any word may match; title hits rank highest."""
    words = re.findall(r"\w+", query)
    if not words:
        return []
    con = connect(db_path)
    rows = con.execute("select c.code, c.title, c.units_min, c.units_max, c.ge_areas from course_fts f "
                       "join course c on c.catalog_year = f.catalog_year and c.code = f.code "
                       "where course_fts match ? and f.catalog_year = ? order by bm25(course_fts, 0, 10, 5, 1)",
                       (" OR ".join(f'"{w}"*' for w in words), catalog_year)).fetchall()
    con.close()
    return [{"code": code, "title": title, "units": lo if lo == hi else f"{lo:g}-{hi:g}", "ge_areas": json.loads(ge)}
            for code, title, lo, hi, ge in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description="Print the catalog rows for every course code mentioned in the given files (JSON).")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--db", default="data/catalog.db")
    ap.add_argument("--year", default="2026-27")
    args = ap.parse_args()
    codes = {c for f in args.files for c in re.findall(CODE, Path(f).read_text())}
    rows = {c: {k: v for k, v in r.items() if k != "offered"} for c, r in load_catalog(args.db, args.year, codes).items()}
    json.dump(rows, sys.stdout, indent=1, sort_keys=True)  # evals stay independent of each term's scrape
    print()


if __name__ == "__main__":
    main()
