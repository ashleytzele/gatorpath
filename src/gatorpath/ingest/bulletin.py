"""Bulletin PDF -> course rows (ARCHITECTURE §5, §6.1). Offline builder, run once per catalog year."""

import argparse
import html
import json
import re
import sqlite3
import statistics
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path

import yaml

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


WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>')


def extract_words(pdf_path: str | Path, page: int) -> list[dict]:
    """One page's words with their boxes (`pdftotext -bbox-layout`; `page` is the 0-based PDF index): {t, x0, y0, x1, y1,
    sup}. A word under 85% of the page's median height is a superscript, a footnote mark ("Biochemistry I Laboratory ¹"),
    which -raw prints as a bare number line just like the units."""
    out = subprocess.run(["pdftotext", "-bbox-layout", "-f", str(page + 1), "-l", str(page + 1), str(pdf_path), "-"],
                         capture_output=True, text=True, check=True).stdout
    words = [{"t": " ".join(unicodedata.normalize("NFKC", html.unescape(t)).split()), "x0": float(a), "y0": float(b),
              "x1": float(c), "y1": float(d)} for a, b, c, d, t in WORD.findall(out)]
    words = [w for w in words if w["t"]]
    body = statistics.median(w["y1"] - w["y0"] for w in words) if words else 0
    return [w | {"sup": w["y1"] - w["y0"] < 0.85 * body} for w in words]


SUBJ, NUMBER = r"[A-Z]{1,5}(?: [A-Z]{1,2})?", r"\d{3}[A-Z]{0,2}"
WHOLE_CODE = re.compile(rf"^&?\s*(?:{SUBJ}(?: {NUMBER})?/ ?)*{SUBJ} {NUMBER}$")  # "PLSI/GER/HIST/I R/JS 514", "& BIOL 351"
CODE_PIECE = re.compile(rf"^&?\s*(?:{SUBJ}(?: {NUMBER})?/ ?)*(?:{SUBJ}(?: {NUMBER})?/?|{NUMBER})$")  # wrapped: "PLSI/GER/HIST/I"
UNITS = re.compile(r"^\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?$")
MARKS = re.compile(r"^\d(?:,\d)*$")
GUTTER, MIDDLE = (302.0, 310.0), 306.0  # between the columns of a 612pt page: left text ends by x≈300.5, right starts at 311.4
TABLE = {"left": (103.0, 297.5), "right": (378.0, 575.5), "wide": (170.0, 575.5)}  # Title column x, Units right edge


def codes_in(code: str) -> list[str]:
    """'PLSI/GER/HIST/I R/JS 514' -> PLSI 514, GER 514, …; 'PLSI 386/CST 300' -> both; 'BIOL 351GW & BIOL 351' -> both."""
    out = []
    for part in re.split(r"\s*&\s*", code):
        subjects = []
        for seg in (s.strip() for s in part.split("/") if s.strip()):
            m = re.fullmatch(rf"({SUBJ})(?: ({NUMBER}))?", seg)
            subjects = subjects + [m.group(1)] if m else []
            if m and m.group(2):
                out += [f"{s} {m.group(2)}" for s in subjects]
                subjects = []
    return out


def course_rows(words: list[dict]) -> list[dict]:
    """A page's course-table rows from its words: [{code, codes, units, marks}]. Each column (or a table that spans the
    page) is read as Code | Title | Units: a code wrapped over lines is joined ("PLSI/GER/HIST/I" + "R/JS 514"), a "&"
    line is a bundle, the units are the number in the narrow Units column, and the marks are the superscripts on the
    course's lines, each on the line its box overlaps most. Column positions come from each "Code Title Units" header."""
    body = sorted((w for w in words if not w["sup"]), key=lambda w: (w["y0"] + w["y1"]) / 2)
    bands = []  # lines across the whole page: a line crossing the gutter is a full-width table's
    for w in body:
        if bands and (w["y0"] + w["y1"]) / 2 - bands[-1]["c"] < 3.6:
            bands[-1]["w"].append(w)
        else:
            bands.append({"c": (w["y0"] + w["y1"]) / 2, "w": [w]})
    wide, wide_y, run = set(), [], []
    # ponytail: a full-width table is the run of lines around one that crosses the gutter, up to a 20pt gap; two-column
    # text right below one without a gap would be read as full width. Upgrade to a gutter test per column block.
    for b in bands + [None]:
        if b is None or run and b["c"] - run[-1]["c"] > 20:
            if any(GUTTER[0] < w["x1"] and w["x0"] < GUTTER[1] for r in run for w in r["w"]):
                wide |= {id(w) for r in run for w in r["w"]}
                wide_y.append((min(w["y0"] for r in run for w in r["w"]) - 3, max(w["y1"] for r in run for w in r["w"]) + 3))
            run = []
        if b is not None:
            run.append(b)

    def side(w: dict) -> str:
        if id(w) in wide or w["sup"] and any(a <= w["y0"] <= b for a, b in wide_y):
            return "wide"
        return "right" if w["x0"] >= MIDDLE else "left"

    rows, geometry = [], dict(TABLE)
    for column in ("left", "right", "wide"):
        lines = []
        for w in (w for w in body if side(w) == column):
            if lines and abs((w["y0"] + w["y1"]) / 2 - lines[-1]["c"]) < 3.6:
                lines[-1]["w"].append(w)
                lines[-1]["y0"], lines[-1]["y1"] = min(lines[-1]["y0"], w["y0"]), max(lines[-1]["y1"], w["y1"])
            else:
                lines.append({"c": (w["y0"] + w["y1"]) / 2, "w": [w], "y0": w["y0"], "y1": w["y1"]})
        for s in (w for w in words if w["sup"] and side(w) == column):
            overlap = lambda line: min(line["y1"], s["y1"]) - max(line["y0"], s["y0"])
            best = max(lines, key=overlap, default=None)
            if best is not None and overlap(best) > 0:
                best["w"].append(s)
        current = None
        for line in lines:
            ws = sorted(line["w"], key=lambda w: w["x0"])
            if ws[0]["t"] == "Code" and any(w["t"] == "Units" for w in ws):
                title = next((w for w in ws if w["t"] == "Title"), None)
                geometry[column] = (title["x0"] if title else geometry[column][0], next(w for w in ws if w["t"] == "Units")["x1"])
                current = None
                continue
            title_x, units_right = geometry[column]
            code = " ".join(w["t"] for w in ws if w["x0"] < title_x - 3 and not w["sup"])
            rest = [w for w in ws if w["x0"] >= title_x - 3]
            if current and not re.search(rf"{NUMBER}$", current["code"]) and code and CODE_PIECE.match(code):
                current["code"] = join(current["code"], code)  # a code wrapped over lines
            elif current and code.startswith("&") and WHOLE_CODE.match(code):
                current["code"] += " " + code
            elif WHOLE_CODE.match(code) or "/" in code and CODE_PIECE.match(code):  # "FIN/ECON/ENVS" (651 below)
                current = {"code": code, "units": None, "marks": []}
                rows.append(current)
            elif code or not rest or re.match(r"(Select|Total)", " ".join(w["t"] for w in rest)):
                current = None
            if current is None:
                continue
            units = [w["t"] for w in rest if not w["sup"] and UNITS.match(w["t"]) and w["x1"] > units_right - 15
                     and w["x0"] >= units_right - 22]  # in the narrow Units column: never a year ending a title
            if units and current["units"] is None:
                current["units"] = units[0]
            current["marks"] += [m for w in rest if w["sup"] and MARKS.match(w["t"]) for m in w["t"].split(",")]
    return [r | {"codes": codes_in(r["code"])} for r in rows]


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
create virtual table if not exists course_fts using fts5(catalog_year unindexed, code, title, description,
  tokenize = 'porter unicode61');
"""


def write_catalog(db_path: str | Path, catalog_year: str, courses: list[dict], legacy: dict | None = None) -> None:
    """Rebuilds one catalog year in place (ARCHITECTURE §6.1). Raw prereq text is always stored, parsed or not; an older
    GE code in it is stored as the area `legacy` (the year's legacy_ge_areas map) gives it."""
    con = sqlite3.connect(db_path)
    with con:
        con.executescript(SCHEMA)
        for table in ("course", "prereq", "course_link", "course_fts"):
            con.execute(f"delete from {table} where catalog_year = ?", (catalog_year,))
        for c in courses:
            con.execute(
                "insert into course values (?,?,?,?,?,?,?,?,?)",
                (catalog_year, c["code"], c["title"], c["units_min"], c["units_max"], c["description"], c["grading"],
                 json.dumps(c["ge_areas"]), c["source_page"]),
            )
            p = parse_prereq(c["prereq_text"], legacy or {})
            con.execute(
                "insert into prereq values (?,?,?,?,?,?)",
                (catalog_year, c["code"], c["prereq_text"], None if p["expr"] is None else json.dumps(p["expr"]),
                 p["status"], int(p["needs_permission"])),
            )
            for kind, others in (("paired", c["paired_with"]), ("crosslisted", c["crosslisted_with"])):
                for other in others:
                    con.execute("insert or ignore into course_link values (?,?,?,?)",
                                (catalog_year, *sorted((c["code"], other)), kind))
        con.execute("insert into course_fts select catalog_year, code, title, description from course where catalog_year = ?",
                    (catalog_year,))
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


LEGACY_GE = re.compile(r"• ((?:GE-)?[A-F][1-5]?(?: or [A-F][1-5])?|UD-[B-D]): ")
CURRENT_GE = re.compile(r"• (\d[A-C]?|\dUD): ")


def legacy_ge_report(pages: list[str]) -> str:
    """For each older GE code in "Course Attributes:" (A2, C1, UD-D, GE-F, ...), which current codes the same courses
    carry and how often. The evidence behind rules/university legacy_ge_areas; rerun it for each new Bulletin."""
    old_new: dict[str, Counter] = {}
    seen: Counter = Counter()
    attrs: list[str] | None = None
    for line in (l.strip() for page in pages for l in page.splitlines()):
        if line == "Course Attributes:":
            attrs = []
        elif attrs is not None and line.startswith("• "):
            attrs.append(line)
        elif attrs is not None:
            olds = {m.group(1) for a in attrs if (m := LEGACY_GE.match(a))}
            news = {m.group(1) for a in attrs if (m := CURRENT_GE.match(a))}
            for o in olds:
                seen[o] += 1
                old_new.setdefault(o, Counter()).update(news)
            attrs = None
    rows = [f"{o:9} on {n:4} course entries; with: "
            + (", ".join(f"{c} {k}" for c, k in old_new[o].most_common(3)) or "no current GE code")
            for o, n in seen.most_common()]
    return "\n".join(["Older GE code -> current codes on the same courses (entries, incl. department + A-Z listings)", *rows])


def main() -> None:
    ap = argparse.ArgumentParser(description="Build data/catalog.db from the Bulletin PDF and print prereq coverage.")
    ap.add_argument("pdf")
    ap.add_argument("--db", default="data/catalog.db")
    ap.add_argument("--year", help="catalog year, e.g. 2026-27 (default: read from the file name)")
    ap.add_argument("--subjects", default="CSC,MATH,PHYS", help="subjects for the coverage report")
    ap.add_argument("--legacy-ge", action="store_true", help="only print the older-GE-code report (writes nothing)")
    args = ap.parse_args()
    year = args.year or re.search(r"\d{4}-\d{2}", Path(args.pdf).name).group()
    pages = extract_pages(args.pdf)
    if args.legacy_ge:
        print(legacy_ge_report(pages))
        return
    courses, warnings = parse_courses(pages)
    rules = Path(__file__).parents[3] / f"rules/university/{year}.yaml"
    legacy = yaml.safe_load(rules.read_text()).get("legacy_ge_areas", {}).get("map", {}) if rules.exists() else {}
    write_catalog(args.db, year, courses, {str(k).upper(): v for k, v in legacy.items()})
    print(f"{len(courses)} courses -> {args.db} ({year}); {len(warnings)} dedupe warnings")
    print("\n".join(f"  {w}" for w in warnings))
    print(coverage_report(args.db, year, args.subjects.split(",")))


if __name__ == "__main__":
    main()
