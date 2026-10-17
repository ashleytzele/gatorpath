"""MCP tools (ARCHITECTURE §7). Thin: check input, read catalog.db and rules/, call engine/, add catalog_year + warnings."""

import difflib
import re
from functools import cache
from pathlib import Path
from typing import NotRequired, TypedDict

import yaml
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from gatorpath import db
from gatorpath.engine.prereq import prereq_chain, prereq_warnings
from gatorpath.engine.rules import RULES_DIR, audit, load_rules, number

YEAR = "2026-27"  # ponytail: one catalog year. Take it from the profile/tool input once a second year is ingested.
DB = Path(__file__).parents[2] / "data/catalog.db"
LEVELS = {"lower": (100, 300), "upper": (300, 700), "graduate": (700, 1000)}
NO_OFFERINGS = "Offering history isn't loaded yet (TASKS phase 5), so `offered` is 'unknown'; check Class Search"
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    "gatorpath",
    instructions=(
        f"SF State degree-planning tools for the {YEAR} Bulletin. Answers come only from the Bulletin and reviewed rules: "
        "don't add courses, prereqs or requirements the tools didn't return. Cite the `source`/`source_page` Bulletin "
        "pages, show every warning, and remind the student that the DPR and an advisor are the final word. "
        "Never guess what transfer credit covers or when a student will graduate: ask for the DPR, and use the planner "
        "tools when they exist. "
        "Student profiles are passed in per call and never stored."
    ),
)


class CourseTaken(TypedDict):
    code: str
    grade: str
    term: NotRequired[str]
    units: NotRequired[float]
    transfer: NotRequired[bool]


class Profile(TypedDict):
    program: str
    catalog_year: NotRequired[str]
    qr_pathway: NotRequired[str]
    completed: NotRequired[list[CourseTaken]]
    in_progress: NotRequired[list[str]]
    gpa: NotRequired[float]
    ge_done: NotRequired[list[str]]
    transfer_units: NotRequired[float]
    adt: NotRequired[bool]


@cache
def prereqs(path: Path, year: str) -> dict[str, dict]:
    return db.load_prereqs(path, year)


@cache
def catalog(path: Path, year: str) -> dict[str, dict]:
    return db.load_catalog(path, year)


@cache
def by_squashed(path: Path, year: str) -> dict[str, str]:
    return {c.replace(" ", ""): c for c in prereqs(path, year)}  # unique in 2026-27; test_server checks


def norm_code(code: str) -> str:
    """' csc653 ' -> 'CSC 653', 'AAS 210' -> 'AA S 210'. Unknown codes get a space before the number."""
    s = "".join(code.upper().split())
    return by_squashed(DB, YEAR).get(s) or re.sub(r"(?<=[A-Z])(?=\d)", " ", s, count=1)


def close_matches(code: str) -> list[str]:
    """Nearest numbers in the same subject ('CSC 210' -> CSC 215, CSC 220, …), else spelling matches."""
    codes = list(prereqs(DB, YEAR))
    m = re.fullmatch(r"(.+) (\d{3})\w*", code)
    same = [c for c in codes if m and c.rsplit(" ", 1)[0] == m[1]]
    if not same:
        return difflib.get_close_matches(code, codes, n=5)
    return sorted(same, key=lambda c: (abs(number(c) - int(m[2])), c))[:5]


def unknown_course(code: str) -> dict:
    return {"catalog_year": YEAR, "error": "unknown_course", "code": code, "close_matches": close_matches(code),
            "warnings": [f"{code} is not in the {YEAR} Bulletin; courses get renumbered, so check the close matches"]}


def programs() -> dict[str, dict]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted((RULES_DIR / "programs" / YEAR).glob("*.yaml"))}


def unknown_program(program: str) -> dict:
    return {"catalog_year": YEAR, "error": "unknown_program", "program": program, "programs": list(programs()),
            "warnings": [f"{program!r} has no reviewed rules for {YEAR}; GatorPath only answers for the listed programs"]}


def unverified(rules: dict, name: str) -> list[str]:
    return [] if rules.get("verified") else [f"{name} rules are not verified yet; confirm with an advisor and your DPR"]


@mcp.tool(annotations=READ_ONLY)
def search_courses(query: str, subject: str | None = None, level: str | None = None, limit: int = 10) -> dict:
    """Keyword search over Bulletin course codes, titles and descriptions.

    subject: e.g. 'CSC'. level: 'lower' (100-299), 'upper' (300-699), 'graduate' (700+), or a hundred like '600'.
    """
    if level and level not in LEVELS and not re.fullmatch(r"[1-8]00", level):
        return {"catalog_year": YEAR, "error": "bad_level", "warnings": ["level must be lower, upper, graduate or e.g. 600"]}
    lo, hi = LEVELS.get(level or "") or ((int(level), int(level) + 100) if level else (0, 1000))
    want = "".join((subject or "").upper().split())
    exact = norm_code(query)
    rows = [r | {"offered": "unknown"} for r in db.search_courses(DB, YEAR, query)
            if (not want or r["code"].rsplit(" ", 1)[0].replace(" ", "") == want) and lo <= number(r["code"]) < hi]
    rows.sort(key=lambda r: r["code"] != exact)  # stable: an exact code hit first, then FTS rank
    return {"catalog_year": YEAR, "results": rows[:max(1, min(limit, 50))], "total_matches": len(rows),
            "warnings": [NO_OFFERINGS]}


@mcp.tool(annotations=READ_ONLY)
def get_course(code: str) -> dict:
    """Full Bulletin record for one course: description, units, grading, GE areas, prereq (raw text + parsed tree +
    status), paired/cross-listed links, source_page."""
    code = norm_code(code)
    course = db.get_course(DB, YEAR, code)
    if course is None:
        return unknown_course(code)
    return course | {"offered_terms": "unknown", "warnings": prereq_warnings(code, course["prereq"]) + [NO_OFFERINGS]}


@mcp.tool(annotations=READ_ONLY)
def get_prereq_chain(code: str) -> dict:
    """Everything that must come before a course, all the way down.

    `requires` is the course's own prereq tree ({"all": […]} / {"any": […]} of course, standing, gpa, permission, …
    leaves). `chain` lists every course mentioned anywhere below it, alternatives included, prerequisites first and the
    course itself last; read each entry's `requires` for which are and/or. `conditions` are the non-course leaves;
    `verifiable: false` ones (permission, "or equivalent", …) can't be checked by GatorPath.
    """
    code = norm_code(code)
    rows = prereqs(DB, YEAR)
    if code not in rows:
        return unknown_course(code)
    return {"catalog_year": YEAR} | prereq_chain(code, rows)


@mcp.tool(annotations=READ_ONLY)
def list_programs() -> dict:
    """Programs GatorPath has reviewed requirement rules for."""
    return {"catalog_year": YEAR, "warnings": [],
            "programs": [{"id": k, "title": p["title"], "verified": bool(p.get("verified"))} for k, p in programs().items()]}


@mcp.tool(annotations=READ_ONLY)
def get_program_requirements(program: str) -> dict:
    """A program's requirement groups (as written in its rules YAML, each with its Bulletin page) plus the university
    graduation requirements every bachelor's degree shares: GE areas, SF State Studies, American Institutions, GWAR,
    unit/residence/GPA totals."""
    if program not in programs():
        return unknown_program(program)
    prog, univ = load_rules(YEAR, program)
    return {"catalog_year": YEAR, "program": prog, "university": univ,
            "warnings": unverified(prog, program) + unverified(univ, "University (GE and graduation)")}


@mcp.tool(annotations=READ_ONLY)
def get_roadmap(program: str, variant: str | None = None) -> dict:
    """The Bulletin's suggested semester-by-semester roadmap. Items are course codes or slots like
    {slot: GE, area: "1A", units: 3}. Without a valid variant, returns the variants to choose from (for BS CS the
    variant follows the student's QR pathway / math placement, or the ADT for transfer students)."""
    path = RULES_DIR / "roadmaps" / YEAR / f"{program}.yaml"
    if program not in programs() or not path.exists():
        return unknown_program(program)
    rm = yaml.safe_load(path.read_text())
    warnings = ["The roadmap is a suggestion and doesn't replace meeting with an advisor"] + unverified(rm, f"{program} roadmap")
    if variant not in rm["variants"]:
        return {"catalog_year": YEAR, "program": program, "needs_input": "variant", "warnings": warnings,
                "variants": {k: {"title": v["title"], "qr_pathway": v.get("qr_pathway")} for k, v in rm["variants"].items()}}
    return {"catalog_year": YEAR, "program": program, "variant": variant, **rm["variants"][variant], "warnings": warnings}


@mcp.tool(annotations=READ_ONLY)
def audit_progress(profile: Profile) -> dict:
    """Degree audit: per requirement group satisfied / in_progress / remaining / waived and which courses counted,
    plus university totals (120 units, upper-division, residence, CR cap, GPAs). Nothing is stored.

    profile: program (e.g. 'bs-cs'); completed: [{code, grade, term?, units? (variable-unit courses), transfer?
    (articulated transfer course)}], grades as SF State symbols (A..F, CR, NC, W, I); in_progress: [codes];
    ge_done: GE areas met by transfer/AP/IB credit (e.g. ["1A", "2"], also USH/USG/CSLG); transfer_units: total
    transfer units; adt: true for a verified AA-T/AS-T (waives SF State Studies); gpa optional.
    """
    if profile.get("catalog_year", YEAR) != YEAR:
        return {"catalog_year": YEAR, "error": "unsupported_catalog_year",
                "warnings": [f"only the {YEAR} Bulletin is loaded; {profile['catalog_year']} isn't"]}
    if profile["program"] not in programs():
        return unknown_program(profile["program"])
    program, university = load_rules(YEAR, profile["program"])
    assumed = [] if "catalog_year" in profile else [
        f"catalog_year not given, so this audit uses the {YEAR} Bulletin. Students are held to the year on their DPR "
        "('Requirement (Catalog) Term'); if it's earlier, requirements (GE areas especially) may differ"]
    profile = profile | {"catalog_year": YEAR,
                         "completed": [r | {"code": norm_code(r["code"])} for r in profile.get("completed", [])],
                         "in_progress": [norm_code(c) for c in profile.get("in_progress", [])]}
    out = audit(profile, program, university, catalog(DB, YEAR))
    out["warnings"] = assumed + out["warnings"] + unverified(university, "University (GE and graduation)")
    return out
