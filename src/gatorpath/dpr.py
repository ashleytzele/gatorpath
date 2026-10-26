"""Local DPR PDF (Student Center → Degree Progress Report, printed to PDF) -> requirements and a profile
(ARCHITECTURE §7.3, D14). Names, IDs and the raw text never leave this module (golden rule 5).

The print loses the status icons, so status comes from the rows: a grade (or T, transfer) means used, a term with no
grade means in progress, "Fall, Spring" in the When column means a course that may be used but wasn't taken, and
"Units/Courses: … needed" lines mean the requirement isn't met.
"""

import re
import subprocess
from pathlib import Path

from gatorpath.engine.rules import GRADE_SYMBOLS, translate_ge

CODE = r"[A-Z]{1,5}(?: [A-Z]{1,3})? \d{2,3}[A-Z]{0,4}"  # 'MATH 226', 'CSC 300GW', 'COMM 100TR', 'TRFX 50NTR'
COURSE_TITLE = re.compile(rf"[A-Z]{{1,5}}(?: [A-Z]{{1,3}})? \d{{3}}[A-Z]{{0,3}}(?: (?:and|or|,) [A-Z]{{1,5}}(?: [A-Z]{{1,3}})? \d{{3}}[A-Z]{{0,3}})*")
TAG = re.compile(r"\s*\[([RG]\d+)(?: / (L\d+))?\]\s*")
ROW = re.compile(rf"\s*(?P<code>{CODE})\s+(?P<desc>.*?)\s*(?P<units>\d+\.\d\d)"
                 r"(?:\s+(?P<when>(?:Fall|Spring|Summer|Winter) \d{4}))?(?:\s+(?P<grade>[A-Z][A-Z+-]{0,2}))?"
                 r"(?:\s+(?P<notes>\d\d))?(?:\s+(?P<desig>GE \S.*?))?\s*")
NEEDED = re.compile(r"(Units|Courses): (\d+(?:\.\d+)?) required, (\d+(?:\.\d+)?) taken, (\d+(?:\.\d+)?) needed")
PAGES = re.compile(r"First\s+(\d+)-(\d+) of (\d+)\s+Last")
NOT_TITLE = ("Units Required", "Total Units Required", "(", "Complete ", "One course", "The following", "Course ",
             "View All")
PRINT_CHROME = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2} [AP]M\s.*|https?://\S+.*")  # browser header/footer
TRANSFER = re.compile(r"\d+N?TR$")
AREA_TITLE = re.compile(r"Area \w+(?::| -) [^.]+")  # 'Area 1A: English Composition', not a sentence about an area


def term_of(when: str) -> str:
    season, year = when.split()
    return f"{year}-{season.lower()}"


def parse(text: str) -> dict:
    """{plan, catalog_term, gpa, sf_state_gpa, requirements: [{id, title, kind, status, rows, needed, waived}], warnings}"""
    out = {"plan": None, "catalog_term": None, "gpa": None, "sf_state_gpa": None, "requirements": [], "warnings": []}
    recent: list[str] = []
    block: dict | None = None
    in_ge = True  # "Area …" titles are GE areas only in the General Education section, not a major's "Area 1: …"
    title_only = None  # a requirement's title, until the next line shows whether the print collapsed it
    for line in text.splitlines():
        s = line.strip()
        if PRINT_CHROME.fullmatch(s):  # a page break can fall between a requirement's title and its tag
            continue
        if s and title_only:  # collapsed (met, printed without Expand All): the next title follows, no tag or rows
            if not s.startswith(NOT_TITLE) and not TAG.fullmatch(line):
                out["requirements"].append({"id": "collapsed", "title": title_only, "rows": [], "needed": None,
                                            "waived": None, "kind": "course" if COURSE_TITLE.fullmatch(title_only) else "ge"})
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
            title = next((r for r in reversed(recent) if not r.startswith(NOT_TITLE)), "")
            if m[1].startswith("G"):  # a section: GE, University Requirements, the major
                in_ge = "General Education" in title
            block = {"id": m[1] + (f"/{m[2]}" if m[2] else ""), "title": title, "kind": "group" if not m[2] else
                     "course" if COURSE_TITLE.fullmatch(title) else "ge" if in_ge and title.startswith("Area ") else "other",
                     "rows": [], "needed": None, "waived": None}
            out["requirements"].append(block)
            recent = []
            continue
        if s == "Courses Not Used":
            block = {"id": "not_used", "title": s, "kind": "not_used", "rows": [], "needed": None, "waived": None}
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
            out["warnings"].append(f"{block['title']}: the print shows {m[2]} of {m[3]} courses. If a course is missing "
                                   "below, click View All on that list and print the DPR again")
        elif m := ROW.fullmatch(line):
            if m["grade"] and m["grade"] not in GRADE_SYMBOLS | {"T"}:
                out["warnings"].append(f"{block['title']}: a course row has grade {m['grade']!r}, not an SF State grade "
                                       "symbol (p.2403) or T; check that row on your DPR")
            block["rows"].append({
                "code": m["code"], "units": float(m["units"]), "term": term_of(m["when"]) if m["when"] else None,
                "grade": m["grade"], "notes": m["notes"], "designation": m["desig"],
                "transfer": bool(TRANSFER.search(m["code"])), "option": m["when"] is None})
    for b in out["requirements"]:
        used = [r for r in b["rows"] if r["grade"]]
        going = [r for r in b["rows"] if r["term"] and not r["grade"]]
        # A "needed" line wins over waiver wording: "Area E and/or Area C waived … Min Units Changed from 48 to 42"
        # changes a minimum that can still be short.
        b["status"] = ("collapsed" if b["id"] == "collapsed" else
                       "needed" if b["needed"] and b["needed"]["needed"] > 0 else "waived" if b["waived"]
                       else "in_progress" if going else "done" if used else "needed" if b["kind"] == "course" else "info")
    if folded := [b["title"] for b in out["requirements"] if b["status"] == "collapsed"]:
        out["warnings"].append(f"Collapsed in this print, so their courses don't show: {', '.join(folded)}. Click Expand "
                               "All above the Degree Progress Report (and View All on long lists), print to PDF again and "
                               "import that one; until then GatorPath can't count them as met")
    return out


def to_profile(dpr: dict, min_grade: dict[str, str], units: dict[str, float]) -> dict:
    """Profile fields from a parsed DPR. Transfer rows under a course requirement meet that course (the DPR prints
    only T, so they get the requirement's minimum grade from `min_grade`, said in a warning; with two open courses,
    `units` picks the one whose units match); a GE area the DPR shows
    done goes in ge_done by its DPR title (translated by the tools); an SF State course used for another course's
    requirement is a substitution (dpr_met)."""
    completed: dict[tuple, dict] = {}
    in_progress: list[str] = []
    ge_done, dpr_met, warnings, transfer = [], [], [], {}
    assumed, notes = [], set()
    for b in dpr["requirements"]:
        for r in b["rows"]:
            if r["notes"]:
                notes.add(r["notes"])
            if r["transfer"]:
                transfer[(r["code"], r["term"])] = r["units"]
            elif r["grade"]:
                completed.setdefault((r["code"], r["term"]), {"code": r["code"], "grade": r["grade"]}
                                     | ({"term": r["term"]} if r["term"] else {}))
            elif r["term"] and r["code"] not in in_progress:
                in_progress.append(r["code"])
        if b["kind"] == "ge" and b["status"] == "done":
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
    if assumed:
        warnings.append("Met by transfer credit on the DPR (it prints only T, not the other school's grade), recorded at "
                        f"each requirement's minimum: {', '.join(assumed)}. Give the real grades if you know them")
    if notes:
        warnings.append(f"DPR Notes codes {', '.join(sorted(notes))} have no legend in the print; ask the Registrar or "
                        "an advisor what they mean")
    transfer_units = sum(transfer.values())
    if transfer_units:
        warnings.append(f"{transfer_units:g} transfer units counted from the transfer rows this DPR lists under requirements; if "
                        "you have more (your transcript's Transfer Totals), use that total for transfer_units")
    remaining = [{"requirement": b["title"], **({k: b["needed"][k] for k in ("what", "needed")} if b["needed"] else {})}
                 for b in dpr["requirements"] if b["status"] == "needed" and b["kind"] != "group"]
    return {"catalog_year": dpr["catalog_term"], "completed": list(completed.values()), "in_progress": in_progress,
            "ge_done": ge_done, "dpr_met": dpr_met, "transfer_units": transfer_units,
            **({"gpa": dpr["gpa"]} if dpr["gpa"] is not None else {}), "remaining": remaining, "warnings": warnings}


def cross_check(dpr: dict, audit: dict, university: dict) -> list[str]:
    """The DPR's status vs GatorPath's audit for every DPR requirement GatorPath also tracks: course requirements by
    code, GE areas through translate_ge, GWAR, and units toward the 120. One warning per disagreement, saying the DPR
    wins (catches rule bugs while the rules are verified: false); plus GE areas GatorPath has that the DPR doesn't list."""
    word = {"satisfied": "done", "remaining": "needed"}
    groups = {g["id"]: g for g in audit["groups"]}
    code_status: dict[str, str] = {}
    for g in audit["groups"]:
        code_status |= {c: "in_progress" for c in g.get("in_progress", []) if c not in code_status}
        code_status |= {c: "done" for c in g.get("counted", [])}
    by_area = {str(a): g["id"] for g in university["groups"] if isinstance(g.get("from"), dict) and "ge_area" in g["from"]
               for a in (g["from"]["ge_area"] if isinstance(g["from"]["ge_area"], list) else [g["from"]["ge_area"]])}
    out, seen = [], set()
    for b in dpr["requirements"]:
        if b["status"] in ("info", "waived", "collapsed"):
            if b["kind"] == "ge":
                seen.update(by_area[a] for a in translate_ge([b["title"]], university)[0] if a in by_area)
            continue
        if b["kind"] == "course":
            codes = re.findall(r"[A-Z]{1,5}(?: [A-Z]{1,3})? \d{3}[A-Z]{0,3}", b["title"])
            states = [code_status.get(c, "needed") for c in codes]
            ours = "done" if all(x == "done" for x in states) else "needed" if "needed" in states else "in_progress"
        elif b["kind"] == "ge" or "GWAR" in b["title"]:
            ids = ["gwar"] if "GWAR" in b["title"] else [by_area[a] for a in translate_ge([b["title"]], university)[0]
                                                           if a in by_area]
            if not ids or any(i not in groups for i in ids):
                continue
            seen.update(ids)
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
    if any(b["kind"] == "ge" for b in dpr["requirements"]):
        # GE areas only: SF State Studies and American Institutions aren't "Area …" titles on a DPR
        missing = [g["title"] for g in university["groups"]
                   if g["id"].startswith("ge_") and g["id"] in by_area.values() and g["id"] not in seen]
        if missing:
            out.append(f"Not found on this DPR: {', '.join(missing)}. If the DPR really doesn't have one (an older "
                       "catalog), add it to not_on_dpr; if the print was cut, print it again with View All")
    return out


def read_pdf(path: Path) -> str:
    """pdftotext -layout to memory; nothing written to disk."""
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
