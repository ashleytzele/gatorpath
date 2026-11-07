"""Local DPR PDF (Student Center → Degree Progress Report, printed to PDF) -> requirements and a profile
(ARCHITECTURE §7.3, D14). Names, IDs and the raw text never leave this module (golden rule 5).

Each requirement's status is the DPR's own: its icon (Complete, Currently in Progress, Not Complete, Exception), which the
print keeps as an image in a column at the right and the legend names (icon_statuses). That holds for a section printed
collapsed too. Without the icons (pdftocairo missing) the rows decide: a grade (or T, transfer) means used, a term with
no grade means in progress, "Fall, Spring" in the When column means a course that may be used but wasn't taken,
"Units/Courses: … needed" lines mean the requirement isn't met, and a collapsed section is complete.
"""

import html
import re
import subprocess
from collections import Counter, defaultdict, deque
from pathlib import Path

from gatorpath.engine.rules import GRADE_SYMBOLS, area_groups, translate_ge

CODE = r"[A-Z]{1,5}(?: [A-Z]{1,3})? \d{2,3}[A-Z]{0,4}"  # 'MATH 226', 'CSC 300GW', 'COMM 100TR', 'TRFX 50NTR'
COURSE_TITLE = re.compile(rf"[A-Z]{{1,5}}(?: [A-Z]{{1,3}})? \d{{3}}[A-Z]{{0,3}}(?: (?:and|or|,) [A-Z]{{1,5}}(?: [A-Z]{{1,3}})? \d{{3}}[A-Z]{{0,3}})*")
TAG = re.compile(r"\s*\[([RG]\d+)(?: / (L\d+))?\]\s*")
ROW = re.compile(rf"\s*(?P<code>{CODE})\s+(?P<desc>.*?)\s*(?P<units>\d+\.\d\d)"
                 r"(?:\s+(?P<when>(?:Fall|Spring|Summer|Winter) \d{4}))?(?:\s+(?P<grade>[A-Z][A-Z+-]{0,2}))?"
                 r"(?:\s+(?P<notes>\d\d))?(?:\s+(?P<desig>GE \S.*?))?\s*")
NEEDED = re.compile(r"(Units|Courses): (\d+(?:\.\d+)?) required, (\d+(?:\.\d+)?) taken, (\d+(?:\.\d+)?) needed")
PAGES = re.compile(r"First\s+(\d+)-(\d+) of (\d+)\s+Last")
NOT_TITLE = ("Units Required", "Total Units Required", "Courses Required", "(", "Complete ", "One course",
             "The following", "Course ", "View All", "Note:")
PRINT_CHROME = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2} [AP]M\s.*|https?://\S+.*")  # browser header/footer
TRANSFER = re.compile(r"\d+N?TR$")
AREA_TITLE = re.compile(r"(?:Area \w+|UD-\w)(?::| -) [^.]+")  # 'Area 1A: English Composition', 'UD-B: Physical/Life Science'


def term_of(when: str) -> str:
    season, year = when.split()
    return f"{year}-{season.lower()}"


def parse(text: str, statuses: list[tuple[str, str]] | None = None) -> dict:
    """{plan, catalog_term, gpa, sf_state_gpa, requirements: [{id, title, kind, status, rows, needed, waived}], warnings}.
    `statuses`: the DPR's own icons (icon_statuses), matched to requirements by title in print order"""
    out = {"plan": None, "catalog_term": None, "gpa": None, "sf_state_gpa": None, "requirements": [], "warnings": []}
    icons: dict[str, deque] = defaultdict(deque)
    for title, status in statuses or []:
        icons[title].append(status)
    recent: list[str] = []
    block: dict | None = None
    in_ge = True  # "Area …" titles are GE areas only in the General Education section, not a major's "Area 1: …"
    title_only = None  # a requirement's title, until the next line shows whether the print collapsed it
    cut = []  # lists printed without View All
    foreign: Counter = Counter()  # rows with a grade SF State doesn't give
    for line in text.splitlines():
        s = line.strip()
        if PRINT_CHROME.fullmatch(s):  # a page break can fall between a requirement's title and its tag
            continue
        if s and title_only:  # collapsed (met, printed without Expand All): the next title follows, no tag or rows
            if not s.startswith(NOT_TITLE) and not TAG.fullmatch(line):
                out["requirements"].append({"id": "collapsed", "title": title_only, "rows": [], "needed": None,
                                            "waived": None, "kind": "course" if COURSE_TITLE.fullmatch(title_only) else "ge",
                                            "icon": icons[title_only].popleft() if icons[title_only] else None})
            title_only = None
        if COURSE_TITLE.fullmatch(s) or in_ge and AREA_TITLE.fullmatch(s):
            title_only = s
        m = re.search(r"Plan:\s+(.+?)\s{2,}((?:Fall|Spring|Summer|Winter) \d{4})", line)
        if m and out["plan"] is None and not m[1].endswith("-MN"):  # the major's; a minor's Plan line has its own term
            out["plan"], out["catalog_term"] = m[1], m[2]
        for key, label in (("gpa", "Overall GPA:"), ("sf_state_gpa", "SF State GPA:")):
            if m := re.search(rf"{label}\s+(\d\.\d+)", line):
                out[key] = float(m[1])
        if m := TAG.fullmatch(line):
            # an area or course title wins; else the last line that isn't an instruction or a sentence (a note's end)
            title = next((r for r in reversed(recent) if COURSE_TITLE.fullmatch(r) or AREA_TITLE.fullmatch(r)), None) or next(
                (r for r in reversed(recent) if not r.startswith(NOT_TITLE) and not r.endswith(".")), "")
            if m[1].startswith("G"):  # a section: GE, University Requirements, the major
                in_ge = "General Education" in title
            block = {"id": m[1] + (f"/{m[2]}" if m[2] else ""), "title": title, "kind": "group" if not m[2] else
                     "course" if COURSE_TITLE.fullmatch(title) else "ge" if in_ge and title.startswith(("Area ", "UD-")) else "other",
                     "rows": [], "needed": None, "waived": None,
                     "icon": icons[title].popleft() if icons[title] else None}
            out["requirements"].append(block)
            recent = []
            continue
        if s == "Courses Not Used":
            block = {"id": "not_used", "title": s, "kind": "not_used", "rows": [], "needed": None, "waived": None, "icon": None}
            out["requirements"].append(block)
            continue
        if s:
            recent.append(s)
        if block is None:
            continue
        if m := NEEDED.search(line):
            block["needed"] = {"what": m[1].lower(), "required": float(m[2]), "taken": float(m[3]), "needed": float(m[4])}
        elif "waived" in s.lower() and block["waived"] is None:
            block["waived"] = s
        elif (m := PAGES.search(line)) and int(m[2]) < int(m[3]):
            cut.append(f"{block['title']} ({m[2]} of {m[3]} courses)")
        elif m := ROW.fullmatch(line):
            elsewhere = bool(m["grade"]) and m["grade"] not in GRADE_SYMBOLS | {"T"}  # another school's grade: A+
            if elsewhere:
                foreign[m["grade"]] += 1
            block["rows"].append({
                "code": m["code"], "units": float(m["units"]), "term": term_of(m["when"]) if m["when"] else None,
                "grade": m["grade"], "notes": m["notes"], "designation": m["desig"],
                "transfer": bool(TRANSFER.search(m["code"])) or elsewhere, "option": m["when"] is None})
    for b in out["requirements"]:
        used = [r for r in b["rows"] if r["grade"]]
        going = [r for r in b["rows"] if r["term"] and not r["grade"]]
        # A "needed" line wins over waiver wording: "Area E and/or Area C waived … Min Units Changed from 48 to 42"
        # changes a minimum that can still be short.
        # The DPR's own icon when the print has it; else the rows say (a collapsed section prints once it's complete)
        b["status"] = b.get("icon") or (
            "collapsed" if b["id"] == "collapsed" else "needed" if b["needed"] and b["needed"]["needed"] > 0
            else "waived" if b["waived"] else "in_progress" if going else "done" if used
            else "needed" if b["kind"] == "course" else "info")
    if foreign:
        out["warnings"].append(f"{sum(foreign.values())} course row(s) have a grade SF State doesn't give "
                               f"({', '.join(sorted(foreign))}; p.2403), so they're read as credit from another school, "
                               "not SF State work; check them on your DPR")
    if cut:
        out["warnings"].append(f"These lists print only their first rows: {'; '.join(cut)}. Each list's counter in the PDF "
                               "reads \"1-10 of …\" when View All wasn't on; click View All on each (after Expand All), "
                               "check that the counters show every course, and print again. Until then a course that is only "
                               "on those lists is missing")
    if folded := [b for b in out["requirements"] if b["id"] == "collapsed"]:
        out["warnings"].append(f"Collapsed in this print: {', '.join(b['title'] for b in folded)}. " + (
            "Their status is the DPR's own (its icons)" if all(b.get("icon") for b in folded) else
            "A requirement prints collapsed once it's complete, so these count as done")
            + "; Expand All before printing shows their courses and grades")
    return out


def to_profile(dpr: dict, min_grade: dict[str, str], units: dict[str, float]) -> dict:
    """Profile fields from a parsed DPR. Transfer rows under a course requirement meet that course (the DPR prints
    only T, so they get the requirement's minimum grade from `min_grade`, said in a warning; with two open courses,
    `units` picks the one whose units match); a GE area the DPR shows
    done goes in ge_done by its DPR title (translated by the tools); an SF State course used for another course's
    requirement is a substitution (dpr_met)."""
    completed: dict[tuple, dict] = {}
    in_progress: list[str] = []
    ge_done, dpr_met, warnings = [], [], []
    assumed, notes = [], set()
    for b in dpr["requirements"]:
        for r in b["rows"]:
            if r["notes"]:
                notes.add(r["notes"])
            if r["transfer"]:
                continue
            if r["grade"]:
                completed.setdefault((r["code"], r["term"]), {"code": r["code"], "grade": r["grade"]}
                                     | ({"term": r["term"]} if r["term"] else {}))
            elif r["term"] and r["code"] not in in_progress:
                in_progress.append(r["code"])
        if b["kind"] == "ge" and b["status"] in ("done", "collapsed", "waived"):  # waived: met by an exception
            ge_done.append(b["title"])
        for r in b["rows"]:
            for part in (r["designation"] or "").removeprefix("GE ").split("/"):
                if part.strip() in ("USH", "USG", "CSLG") and r["grade"] and part.strip() not in ge_done:
                    ge_done.append(part.strip())
        if b["kind"] != "course" or b["status"] not in ("done", "in_progress"):
            continue
        wanted = re.findall(r"[A-Z]{1,5}(?: [A-Z]{1,3})? \d{3}[A-Z]{0,3}", b["title"])
        open_codes = [c for c in wanted if not any(r["code"] == c for r in b["rows"] if r["grade"] or r["term"])]
        for r in [r for r in b["rows"] if r["transfer"] and r["grade"]]:
            if not open_codes:
                break
            code = next((c for c in open_codes if r["units"] == units.get(c)), open_codes[0])
            open_codes.remove(code)
            grade = min_grade.get(code, "CR")
            completed[(code, None)] = {"code": code, "grade": grade, "transfer": True}
            assumed.append(f"{code} (via {r['code']}, recorded as {grade})")
        subs = [r for r in b["rows"] if r["grade"] and not r["transfer"] and r["code"] not in wanted]
        if subs and open_codes:
            dpr_met += [c for c in open_codes if c not in dpr_met]
    # A course requirement the DPR shows complete without its row (collapsed, or met another way): unless the course
    # shows in another list, it counts as met the way a substitution does. ponytail: "X or Y" can't say which, so not yet
    have = {code for code, _ in completed} | set(in_progress)
    for b in dpr["requirements"]:
        if b["kind"] == "course" and b["status"] in ("done", "collapsed", "waived") and " or " not in b["title"]:
            dpr_met += [c for c in re.findall(r"[A-Z]{1,5}(?: [A-Z]{1,3})? \d{3}[A-Z]{0,3}", b["title"])
                        if c not in have and c not in dpr_met]
    if assumed:
        warnings.append("Met by transfer credit on the DPR (it prints only T, not the other school's grade), recorded at "
                        f"each requirement's minimum: {', '.join(assumed)}. Give the real grades if you know them")
    if notes:
        warnings.append(f"DPR Notes codes {', '.join(sorted(notes))} have no legend in the print; ask the Registrar or "
                        "an advisor what they mean")
    transfer_units = count_transfer_units(dpr["requirements"])
    if transfer_units:
        warnings.append(f"{transfer_units:g} transfer units counted from the transfer rows this DPR lists under requirements; if "
                        "you have more (your transcript's Transfer Totals), use that total for transfer_units")
    remaining = [{"requirement": b["title"], **({k: b["needed"][k] for k in ("what", "needed")} if b["needed"] else {})}
                 for b in dpr["requirements"] if b["status"] == "needed" and b["kind"] != "group"]
    return {"catalog_year": dpr["catalog_term"], "completed": list(completed.values()), "in_progress": in_progress,
            "ge_done": ge_done, "dpr_met": dpr_met, "transfer_units": transfer_units,
            **({"gpa": dpr["gpa"]} if dpr["gpa"] is not None else {}), "remaining": remaining, "warnings": warnings}


# The DPR's own unit lines, by audit totals key: "Units: 120.00 required, 112.00 taken, 8.00 needed" (taken counts
# courses in progress). Titles as the 2024-25 and 2025-26 prints have them
UNIT_TOTALS = {"120 Minimum Units": "units", "Upper-Division Units": "upper_division_units",
               "Residence Units - Upper Division": "residence_upper_division_units", "Residence Units =": "residence_units"}


def unit_totals(dpr: dict) -> dict[str, float]:
    """What the DPR counts toward each unit total, in-progress courses included."""
    return {key: b["needed"]["taken"] for b in dpr["requirements"] if b["needed"] and b["needed"]["what"] == "units"
            for prefix, key in UNIT_TOTALS.items() if b["title"].startswith(prefix)}


def count_transfer_units(requirements: list[dict]) -> float:
    """Each transfer course once. A row repeats across lists, but codes are generic (MATH 100TR), so two rows in one
    list, or under two course requirements, are two courses. ponytail: a truncated list can still hide one."""
    rows = lambda b: Counter((r["code"], r["term"], r["units"]) for r in b["rows"] if r["transfer"])
    lists = [rows(b) for b in requirements]
    under_courses = sum((rows(b) for b in requirements if b["kind"] == "course"), Counter())
    return sum(key[2] * max(under_courses[key], *(c[key] for c in lists)) for key in set().union(*lists))


def not_listed(dpr: dict, university: dict, program: dict | None = None) -> list[dict]:
    """Groups the rules have and this DPR doesn't list: the DPR decides what applies to its student (D33). GE areas
    by their "Area …" titles (SF State Studies and American Institutions aren't titled that way), and a major's
    required-courses group none of whose courses the print names anywhere, in a title or a row (rules from another
    catalog year than the student's). No GE on the print, nothing to go by."""
    areas = [b["title"] for b in dpr["requirements"] if b["kind"] == "ge"]
    if not areas:
        return []
    by_area = area_groups(university)
    seen = {by_area[a] for title in areas for a in translate_ge([title], university)[0] if a in by_area}
    named = {c for b in dpr["requirements"] for c in re.findall(CODE, b["title"])} | {
        r["code"] for b in dpr["requirements"] for r in b["rows"]}
    return [g for g in university["groups"] if g["id"].startswith("ge_") and g["id"] in by_area.values() and g["id"] not in seen
            ] + [g for g in (program or {}).get("groups", []) if g.get("all_of") and not set(g["all_of"]) & named]


def cross_check(dpr: dict, audit: dict, university: dict, program: dict | None = None) -> list[str]:
    """The DPR's status vs GatorPath's audit for every DPR requirement GatorPath also tracks: course requirements by
    code, GE areas through translate_ge, GWAR, and units toward the 120. One warning per disagreement, saying the DPR
    wins (catches rule bugs while the rules are verified: false); plus GE areas GatorPath has that the DPR doesn't list."""
    word = {"satisfied": "done", "remaining": "needed"}
    groups = {g["id"]: g for g in audit["groups"]}
    code_status: dict[str, str] = {}
    for g in audit["groups"]:
        code_status |= {c: "in_progress" for c in g.get("in_progress", []) if c not in code_status}
        code_status |= {c: "done" for c in g.get("counted", [])}
    by_area = area_groups(university)
    out = []
    for b in dpr["requirements"]:
        if b["status"] in ("info", "waived", "collapsed"):
            continue
        if b["kind"] == "course":
            codes = re.findall(r"[A-Z]{1,5}(?: [A-Z]{1,3})? \d{3}[A-Z]{0,3}", b["title"])
            states = [code_status.get(c, "needed") for c in codes]
            pick = any if " or " in b["title"] else all  # "CSC 101 or CSC 215" takes one
            ours = ("done" if pick(x == "done" for x in states) else
                    "in_progress" if pick(x != "needed" for x in states) else "needed")
        elif b["kind"] == "ge" or "GWAR" in b["title"]:
            ids = ["gwar"] if "GWAR" in b["title"] else [by_area[a] for a in translate_ge([b["title"]], university)[0]
                                                           if a in by_area]
            if not ids or any(i not in groups for i in ids):
                continue
            states = [word.get(groups[i]["status"], groups[i]["status"]) for i in ids]
            ours = "done" if all(x == "done" for x in states) else "needed" if "needed" in states else "in_progress"
        elif b["title"].startswith("120 Minimum Units") and b["needed"]:
            t = audit["totals"]
            ours_units = t["units"]["value"] + t.get("units_in_progress", 0)
            if abs(ours_units - b["needed"]["taken"]) > 0.5:
                out.append(f"Units toward the 120: the DPR counts {b['needed']['taken']:g} taken, GatorPath "
                           f"{ours_units:g} (with in-progress). Transfer units the DPR doesn't list under a requirement "
                           "are the usual reason: set transfer_units from your transcript's Transfer Totals")
            continue
        else:
            continue
        if ours != b["status"]:
            out.append(f"{b['title']}: the DPR says {b['status'].replace('_', ' ')}, GatorPath says "
                       f"{ours.replace('_', ' ')}. The DPR wins; ask an advisor if it looks wrong, and tell GatorPath "
                       "if its rule is the one that's off")
    if missing := not_listed(dpr, university, program):
        out.append(f"Not found on this DPR: {', '.join(g['title'] for g in missing)}. Left out of the plan, because the DPR "
                   "decides what's required: confirm with an advisor. If the print was cut, print it again with View All")
    return out


# The status icons: the print keeps each requirement's (Complete, Currently in Progress, Not Complete, ...) as an image in
# a column at the right, and the legend at the top says which image is which
LEGEND = {"Complete": "done", "Currently in Progress": "in_progress", "Planned for Future": "needed",
          "Not Complete": "needed", "Exception or Override": "waived"}
IMAGE = re.compile(r'<image id="([\w-]+)"[^>]*?height="([\d.]+)"[^>]*?xlink:href="([^"]+)"')
USE = re.compile(r'<use xlink:href="#([\w-]+)"(?![^>]*filter=)[^>]*?transform="matrix\(([^)]*)\)"')
LINE = re.compile(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', re.S)
STATUS_COLUMN = 450  # points from the left: requirement icons sit at ~499-516, course rows' at ~373 (ponytail: a print
#                      at another page width moves them; read the column from the legend's page if one does)


def icon_statuses(svg: str, boxes: str) -> list[tuple[str, str]]:
    """[(requirement title, status)] in print order, from the icons (pdftocairo -svg) and the lines beside them
    (pdftotext -bbox-layout). [] when the legend isn't found, so the rows decide as before."""
    images = {m[1]: (m[3], float(m[2])) for m in IMAGE.finditer(svg)}
    pages = []
    for picture, text in zip(svg.split("<page>")[1:], boxes.split("<page ")[1:]):
        icons = []
        for m in USE.finditer(picture):
            if m[1] in images:
                a, b, c, d, x, y = map(float, m[2].split(","))
                data, height = images[m[1]]
                icons.append((data, x, y + d * height / 2))
        lines = [(float(x0), float(y0), float(x1), float(y1), html.unescape(" ".join(re.findall(r">([^<]*)</word>", w))))
                 for x0, y0, x1, y1, w in LINE.findall(text)]
        pages.append((icons, lines))
    key = {}
    for icons, lines in pages:
        for data, x, mid in icons:
            right = [l[4] for l in lines if l[1] - 5 <= mid <= l[3] + 5 and 0 < l[0] - x < 40]
            if right and right[0] in LEGEND and data not in key:
                key[data] = LEGEND[right[0]]
    out = []
    for icons, lines in pages:
        for data, x, mid in icons:
            left = [(x - l[2], l[4]) for l in lines if l[1] - 5 <= mid <= l[3] + 5 and l[2] < x]
            if data in key and x > STATUS_COLUMN and left:
                out.append((" ".join(min(left)[1].split()), key[data]))
    return out


def read_statuses(path: Path) -> list[tuple[str, str]]:
    run = lambda tool: subprocess.run([*tool, str(path), "-"], capture_output=True, text=True, check=True).stdout
    return icon_statuses(run(["pdftocairo", "-svg"]), run(["pdftotext", "-bbox-layout"]))


def read_statuses_bytes(data: bytes) -> list[tuple[str, str]]:
    run = lambda tool: subprocess.run([*tool, "-", "-"], input=data, capture_output=True, check=True,
                                      timeout=60).stdout.decode("utf-8", "replace")
    return icon_statuses(run(["pdftocairo", "-svg"]), run(["pdftotext", "-bbox-layout"]))


def read_pdf(path: Path) -> str:
    """pdftotext -layout to memory; nothing written to disk."""
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout


def read_pdf_bytes(data: bytes) -> str:
    """The same from bytes, over stdin: a web upload never touches the disk."""
    done = subprocess.run(["pdftotext", "-layout", "-", "-"], input=data, capture_output=True, check=True, timeout=60)
    return done.stdout.decode("utf-8", "replace")
