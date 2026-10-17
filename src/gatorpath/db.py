"""Read-only access to data/catalog.db: course rows as the plain dicts `engine/` takes."""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from gatorpath.ingest.bulletin import CODE

# ponytail: wording match on the description. Upgrade: parse "for a total of N units" and cap repeats.
REPEATABLE = re.compile(r"may be repeated|may repeat when|repeatable (?:once )?for credit", re.I)


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Read-only; a plain connect would silently create an empty file."""
    if not Path(db_path).exists():
        raise FileNotFoundError(f"{db_path} not built; run: uv run python -m gatorpath.ingest.bulletin data/raw/bulletin-2026-27.pdf")
    return sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)


def load_catalog(db_path: str | Path, catalog_year: str, codes: set[str] | None = None) -> dict[str, dict]:
    """{code: {title, units_min, units_max, grading, ge_areas, paired, repeatable, source_page}}"""
    con = connect(db_path)
    paired = {c for row in con.execute(
        "select code_a, code_b from course_link where catalog_year = ? and kind = 'paired'", (catalog_year,)) for c in row}
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
        }
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
    json.dump(load_catalog(args.db, args.year, codes), sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main()
