"""Bulletin PDF -> course rows (ARCHITECTURE §5, §6.1). Offline builder, run once per catalog year."""

import argparse
import json
import re
import sqlite3
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path

from gatorpath.engine.prereq import leaves, parse_prereq

RUNNING_HEAD = "San Francisco State University Bulletin"
CODE = r"[A-Z]{1,5}(?: [A-Z]{1,3})? \d{3}[A-Z]{0,3}"  # 'CSC 300GW', 'I R 205'
STARTS_WITH_CODE = re.compile(rf"{CODE} ")
HEADER = re.compile(rf"({CODE}) (.+?) \(Units?: (\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?\)")
PREREQ_FOR = re.compile(rf"Prerequisites? for ({CODE}):\s*")
PAIRED = re.compile(rf"\(({CODE})/({CODE})(?: \[[^\]]*\])? is a paired course offering")  # "CSC 652 [formerly CSC 650]"
OFFERED_AS = re.compile(r"This course is offered as ([^.]*)\.")
GRADING_NOTE = re.compile(r"\(([^()]*(?:grade|grading|CR/NC)[^()]*)\)")
GE_CODE = re.compile(r"(\d[A-C]?|\dUD): ")  # current scheme; legacy 'UD-C:', 'A3:' etc. are ignored
NAMED_ATTRIBUTES = {
    "Global Perspectives": ["GP"],
    "Social Justice": ["SJ"],
    "Am. Ethnic & Racial Minorities": ["AERM"],
    "Env. Sustain. & Climate Action": ["ESCA"],
    "Graduation Writing Assessment": ["GW"],
    "U.S. History": ["USH"],
    "U.S. Govt CA State Local Govt": ["USG", "CSLG"],
    "Calif State & Local Govt": ["CSLG"],
}


def extract_pages(pdf_path: str | Path) -> list[str]:
    """`pdftotext -raw` keeps the two-column course pages in logical order (default mode interleaves them)."""
    out = subprocess.run(["pdftotext", "-raw", str(pdf_path), "-"], capture_output=True, text=True, check=True)
    return out.stdout.split("\f")


def join(a: str, b: str) -> str:
    return a + b if a.endswith(("-", "/")) else f"{a} {b}"


def joined(lines: list[str]) -> str:
    text = ""
    for line in lines:
        text = join(text, line) if text else line
    return text


def lines_with_pages(pages: list[str]) -> list[tuple[str, int | None]]:
    """Body lines tagged with the printed page number (last line of each page); running heads dropped."""
    out = []
    for page in pages:
        lines = [line.strip() for line in unicodedata.normalize("NFKC", page).split("\n") if line.strip()]  # ligatures: ﬁ -> fi
        printed = int(lines.pop()) if lines and lines[-1].isdigit() else None
        out += [(line, printed) for line in lines if RUNNING_HEAD not in line]
    return out


def header_at(lines: list[tuple[str, int | None]], i: int) -> tuple[re.Match, int] | None:
    """A course header may wrap over up to 3 lines; returns (match, index after header)."""
    if not STARTS_WITH_CODE.match(lines[i][0]):
        return None
    text = lines[i][0]
    for j in range(i, min(i + 3, len(lines))):
        if j > i:
            if STARTS_WITH_CODE.match(lines[j][0]):
                return None
            text = join(text, lines[j][0])
        if m := HEADER.fullmatch(text):
            return m, j + 1
    return None


def grading_kind(text: str) -> str | None:
    for note in GRADING_NOTE.findall(text):
        if "no CR/NC" in note:
            return "letter"
        if "CR/NC" in note and ("letter" in note or "allowed" in note):
            return "letter_or_cr_nc"
        if "CR/NC" in note:
            return "cr_nc"
        if "letter grade" in note or "/NC" in note:
            return "letter"
    return None


def own_prereq(code: str, text: str) -> str:
    """Paired entries print both courses' prereqs ('Prerequisite for CSC 871: …'); keep this course's."""
    parts = PREREQ_FOR.split(text)
    if len(parts) == 1:
        return re.sub(r"^Prerequisites?:\s*", "", text)
    segments = dict(zip(parts[1::2], (s.strip() for s in parts[2::2])))
    return segments.get(code, "")


def parse_body(code: str, body: list[str]) -> dict:
    prereq, k = [], 0
    if body and body[0].startswith("Prerequisite"):
        # ponytail: a prereq with no final period swallows the description up to here; the prereq
        # parser then marks it unparsed. Upgrade: stop at the first sentence-case line if that shows up often.
        while k < len(body) and body[k] != "Course Attributes:":
            prereq.append(body[k])
            k += 1
            if prereq[-1].endswith(".") and not (k < len(body) and body[k].startswith("Prerequisite")):
                break
    attributes, description = [], []
    rest = iter(body[k:])
    for line in rest:
        if line == "Course Attributes:":
            for attr in rest:
                if not attr.startswith("•"):
                    description.append(attr)
                    break
                attributes.append(attr.lstrip("• "))
        else:
            description.append(line)
    ge = []
    for attr in attributes:
        if m := GE_CODE.match(attr):
            ge.append(m.group(1))
        ge += NAMED_ATTRIBUTES.get(attr, [])
    description_text = joined(description)
    paired = [c for m in PAIRED.finditer(description_text) for c in m.groups() if c != code]
    offered = OFFERED_AS.search(description_text)
    listed = re.sub(r"\[[^\]]*\]", "", offered.group(1)) if offered else ""  # drop "[formerly HIST 501]"
    crosslisted = [c for c in re.findall(CODE, listed) if c != code]
    return {
        "prereq_text": own_prereq(code, joined(prereq)) if prereq else "",
        "description": description_text,
        "grading": grading_kind(description_text),
        "ge_areas": ge,
        "paired_with": paired,
        "crosslisted_with": crosslisted,
    }


def parse_courses(pages: list[str]) -> tuple[list[dict], list[str]]:
    """Every course is printed twice (department section, then A–Z catalog): keep the first, warn on mismatch."""
    lines = lines_with_pages(pages)
    entries, i = [], 0
    while i < len(lines):
        if found := header_at(lines, i):
            m, i = found
            entries.append((m, lines[i - 1][1], []))
        else:
            if entries:
                entries[-1][2].append(lines[i][0])
            i += 1
    courses: dict[str, dict] = {}
    warnings = []
    for m, page, body in entries:
        code, title, lo, hi = m.groups()
        course = {
            "code": code,
            "title": title,
            "units_min": float(lo),
            "units_max": float(hi or lo),
            "source_page": page,
            **parse_body(code, body),
        }
        if code not in courses:
            courses[code] = course
            continue
        first = courses[code]
        key = ("title", "units_min", "units_max", "prereq_text")
        if any(first[k] != course[k] for k in key):
            warnings.append(f"{code}: copy on p.{page} differs from p.{first['source_page']}; kept p.{first['source_page']}")
    return list(courses.values()), warnings


SCHEMA = """
create table if not exists course(catalog_year text, code text, title text, units_min real, units_max real,
  description text, grading text, ge_areas text, source_page integer, primary key (catalog_year, code));
create table if not exists prereq(catalog_year text, code text, raw_text text, expr text, status text,
  needs_permission integer, primary key (catalog_year, code));
create table if not exists course_link(catalog_year text, code_a text, code_b text, kind text,
  primary key (catalog_year, code_a, code_b, kind));
"""


def write_catalog(db_path: str | Path, catalog_year: str, courses: list[dict]) -> None:
    """Rebuilds one catalog year in place (ARCHITECTURE §6.1). Raw prereq text is always stored, parsed or not."""
    con = sqlite3.connect(db_path)
    with con:
        con.executescript(SCHEMA)
        for table in ("course", "prereq", "course_link"):
            con.execute(f"delete from {table} where catalog_year = ?", (catalog_year,))
        for c in courses:
            con.execute(
                "insert into course values (?,?,?,?,?,?,?,?,?)",
                (catalog_year, c["code"], c["title"], c["units_min"], c["units_max"], c["description"], c["grading"],
                 json.dumps(c["ge_areas"]), c["source_page"]),
            )
            p = parse_prereq(c["prereq_text"])
            con.execute(
                "insert into prereq values (?,?,?,?,?,?)",
                (catalog_year, c["code"], c["prereq_text"], None if p["expr"] is None else json.dumps(p["expr"]),
                 p["status"], int(p["needs_permission"])),
            )
            for kind, others in (("paired", c["paired_with"]), ("crosslisted", c["crosslisted_with"])):
                for other in others:
                    con.execute("insert or ignore into course_link values (?,?,?,?)",
                                (catalog_year, *sorted((c["code"], other)), kind))
    con.close()


def coverage_report(db_path: str | Path, catalog_year: str, subjects: list[str]) -> str:
    """% ok per subject (over courses that have prereq text), every non-ok string, and codes the catalog lacks."""
    con = sqlite3.connect(db_path)
    rows = con.execute("select code, raw_text, expr, status from prereq where catalog_year = ? order by code",
                       (catalog_year,)).fetchall()
    con.close()
    known = {r[0] for r in rows}
    lines, non_ok, missing = [f"Prereq coverage, {catalog_year} (courses with prereq text)"], [], []
    total_ok = total = 0
    for subject in subjects:
        mine = [r for r in rows if r[0].rsplit(" ", 1)[0] == subject]
        counted = [r for r in mine if r[3] != "none"]
        ok = sum(r[3] == "ok" for r in counted)
        total_ok, total = total_ok + ok, total + len(counted)
        other = Counter(r[3] for r in counted if r[3] != "ok")
        pct = f"{100 * ok / len(counted):.1f}%" if counted else "n/a"
        lines.append(f"{subject:<5} {ok}/{len(counted)} ok ({pct})  " + "  ".join(f"{k} {n}" for k, n in sorted(other.items())))
        non_ok += [f"  {code} [{status}] {raw}" for code, raw, _, status in counted if status != "ok"]
        for code, _, expr, _ in mine:
            refs = dict.fromkeys(leaf["course"] for leaf in leaves(json.loads(expr) if expr else None) if "course" in leaf)
            missing += [f"  {code} -> {ref}" for ref in refs if ref not in known]
    if total:
        lines.append(f"TOTAL {total_ok}/{total} ok ({100 * total_ok / total:.1f}%)")
    lines += ["", f"Not ok ({len(non_ok)}):", *non_ok, "", f"Referenced codes missing from this catalog ({len(missing)}):", *missing]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build data/catalog.db from the Bulletin PDF and print prereq coverage.")
    ap.add_argument("pdf")
    ap.add_argument("--db", default="data/catalog.db")
    ap.add_argument("--year", help="catalog year, e.g. 2026-27 (default: read from the file name)")
    ap.add_argument("--subjects", default="CSC,MATH,PHYS", help="subjects for the coverage report")
    args = ap.parse_args()
    year = args.year or re.search(r"\d{4}-\d{2}", Path(args.pdf).name).group()
    courses, warnings = parse_courses(extract_pages(args.pdf))
    write_catalog(args.db, year, courses)
    print(f"{len(courses)} courses -> {args.db} ({year}); {len(warnings)} dedupe warnings")
    print("\n".join(f"  {w}" for w in warnings))
    print(coverage_report(args.db, year, args.subjects.split(",")))


if __name__ == "__main__":
    main()
