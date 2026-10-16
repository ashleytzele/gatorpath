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


def load_catalog(db_path: str | Path, catalog_year: str, codes: set[str] | None = None) -> dict[str, dict]:
    """{code: {title, units_min, units_max, grading, ge_areas, paired, repeatable, source_page}}"""
    con = sqlite3.connect(db_path)
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
