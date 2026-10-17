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
from gatorpath.engine.planner import build_plan as engine_build_plan
from gatorpath.engine.planner import check_plan as engine_check_plan
from gatorpath.engine.planner import eligible_options, see_advisor
from gatorpath.engine.prereq import prereq_chain, prereq_warnings, reverse_index
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
    start_term: NotRequired[str]
    completed: NotRequired[list[CourseTaken]]
    in_progress: NotRequired[list[str]]
    gpa: NotRequired[float]
    ge_done: NotRequired[list[str]]
    transfer_units: NotRequired[float]
    adt: NotRequired[bool]
    max_units_per_term: NotRequired[float]
    include_summer: NotRequired[bool]
    graduate_by: NotRequired[str]


class Slot(TypedDict):
    slot: str
    units: float
    upper_division: NotRequired[bool]


class Semester(TypedDict):
    term: str
    courses: list[str | Slot]


class Plan(TypedDict):
    semesters: list[Semester]


@cache
def prereqs(path: Path, year: str) -> dict[str, dict]:
    return db.load_prereqs(path, year)


@cache
def catalog(path: Path, year: str) -> dict[str, dict]:
    return db.load_catalog(path, year)


@cache
def unlocks(path: Path, year: str) -> dict[str, list[str]]:
    return reverse_index(prereqs(path, year))


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
    status), paired/cross-listed links, source_page, and `unlocks`: courses whose prereqs name it (as a requirement or
    one of the alternatives), so a student sees what skipping or delaying it holds up."""
    code = norm_code(code)
    course = db.get_course(DB, YEAR, code)
    if course is None:
        return unknown_course(code)
    return course | {"offered_terms": "unknown", "unlocks": unlocks(DB, YEAR).get(code, []),
                     "warnings": prereq_warnings(code, course["prereq"]) + [NO_OFFERINGS]}


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


def normalized(profile: dict) -> dict:
    return profile | {"catalog_year": YEAR,
                      "completed": [r | {"code": norm_code(r["code"])} for r in profile.get("completed", [])],
                      "in_progress": [norm_code(c) for c in profile.get("in_progress", [])]}


def year_warning(profile: dict) -> list[str]:
    return [] if "catalog_year" in profile else [
        f"catalog_year not given, so this uses the {YEAR} Bulletin. Students are held to the year on their DPR "
        "('Requirement (Catalog) Term'); if it's earlier, requirements (GE areas especially) may differ"]


def profile_error(profile: dict) -> dict | None:
    if profile.get("catalog_year", YEAR) != YEAR:
        return {"catalog_year": YEAR, "error": "unsupported_catalog_year",
                "warnings": [f"only the {YEAR} Bulletin is loaded; {profile['catalog_year']} isn't"]}
    if profile["program"] not in programs():
        return unknown_program(profile["program"])
    return None


@mcp.tool(annotations=READ_ONLY)
def audit_progress(profile: Profile) -> dict:
    """Degree audit: per requirement group satisfied / in_progress / remaining / waived and which courses counted,
    plus university totals (120 units, upper-division, residence, CR cap, GPAs). Nothing is stored.

    profile: program (e.g. 'bs-cs'); completed: [{code, grade, term?, units? (variable-unit courses), transfer?
    (articulated transfer course)}], grades as SF State symbols (A..F, CR, NC, W, I); in_progress: [codes];
    ge_done: GE areas met by transfer/AP/IB credit (e.g. ["1A", "2"], also USH/USG/CSLG); transfer_units: total
    transfer units; adt: true for a verified AA-T/AS-T (waives SF State Studies); gpa optional.
    """
    if err := profile_error(profile):
        return err
    program, university = load_rules(YEAR, profile["program"])
    out = audit(normalized(profile), program, university, catalog(DB, YEAR))
    out["warnings"] = year_warning(profile) + out["warnings"] + unverified(university, "University (GE and graduation)")
    out["see_advisor"] = see_advisor([("dpr", "Your DPR is the official audit; compare it with this one")]
                                     + ([("major_advisor", f"GatorPath's {profile['program']} rules aren't verified yet")]
                                        if not program.get("verified") else []), program, university)
    return out


@mcp.tool(annotations=READ_ONLY)
def check_plan(profile: Profile, plan: Plan) -> dict:
    """Validate a term-by-term plan. **Call this before presenting any plan, fix every error, and re-check until
    valid.** Errors (with Bulletin text/pages): prereq not met by that term, course already passed or planned twice,
    unknown course, units over max_units_per_term, requirement or 120/upper-division units not covered. Warnings:
    unverifiable prereqs (GPA not given, permission), loads above the normal 15 (p.2393), unfilled slots.

    plan: {semesters: [{term: '2027-fall', courses: ['CSC 413', {slot: 'senior_electives', units: 3}]}]}. A slot is an
    unfilled pick for a requirement group (group ids from get_program_requirements), or {slot: 'elective', units: 3,
    upper_division?: true} for free units. Terms are YYYY-spring/summer/fall, after the profile's completed terms.
    """
    if err := profile_error(profile):
        return err
    program, university = load_rules(YEAR, profile["program"])
    plan = {"semesters": [s | {"courses": [norm_code(c) if isinstance(c, str) else c for c in s.get("courses", [])]}
                          for s in plan.get("semesters", [])]}
    out = engine_check_plan(normalized(profile), plan, program, university, catalog(DB, YEAR), prereqs(DB, YEAR))
    out["warnings"] = year_warning(profile) + out["warnings"] + [NO_OFFERINGS] + unverified(university, "University (GE and graduation)")
    return out


@mcp.tool(annotations=READ_ONLY)
def build_plan(profile: Profile) -> dict:
    """Deterministic baseline plan to graduation: required courses ordered by the prereq chain (critical path first,
    corequisites together), then slots for what's open (GE areas, senior electives, free electives) to reach the 120
    and upper-division totals. Already run through check_plan: see `check`.

    Fill each slot with list_eligible_electives + the student's goal, then call check_plan again before presenting.
    Uses max_units_per_term (default 15, the normal load, p.2393) and include_summer. Returns needs_input
    (qr_pathway, start_term) instead of guessing. Each semester has `why`: per course, what it's needed before, the
    chain it starts, and whether delaying it pushes back graduation. `pace` says what sets the length: the longest
    prereq chain vs the units per term; with profile.graduate_by it says whether that term is reachable and, if
    not, why_not. For "3, 4 or 5 years", call it at different max_units_per_term / include_summer.
    """
    if err := profile_error(profile):
        return err
    program, university = load_rules(YEAR, profile["program"])
    path = RULES_DIR / "roadmaps" / YEAR / f"{profile['program']}.yaml"
    out = engine_build_plan(normalized(profile), program, university, yaml.safe_load(path.read_text()),
                            catalog(DB, YEAR), prereqs(DB, YEAR))
    out["warnings"] = year_warning(profile) + out["warnings"] + [NO_OFFERINGS] + unverified(university, "University (GE and graduation)")
    return out


@mcp.tool(annotations=READ_ONLY)
def list_eligible_electives(profile: Profile, group_id: str, plan: Plan | None = None, by_term: str | None = None,
                            limit: int = 25) -> dict:
    """Courses that can fill one requirement group's slot (e.g. 'senior_electives', 'ge_4ud', 'sfss_esca'), with the
    Bulletin description, so you can pick by the student's goal.

    Each option has readiness at by_term (default: the plan's first term, or the next term): 'ready' (prereqs met),
    'check' (met except what GatorPath can't verify: GPA, permission, unparsed text: see cannot_check), or 'blocked'
    (blocked_by, plus ready_by: the first plan term it opens up, when a plan is given). Pass the build_plan output as
    `plan` and the slot's term as by_term, so planned courses count. Options are ranked ready-first, then by
    also_covers: other open requirements the same course would satisfy (one course can do triple duty, e.g. 4UD +
    Environmental Sustainability + Global Perspectives). Re-run check_plan after filling slots.
    """
    if err := profile_error(profile):
        return err
    program, university = load_rules(YEAR, profile["program"])
    if plan:
        plan = {"semesters": [s | {"courses": [norm_code(c) if isinstance(c, str) else c for c in s.get("courses", [])]}
                              for s in plan.get("semesters", [])]}
    out = eligible_options(normalized(profile), group_id, program, university, catalog(DB, YEAR), prereqs(DB, YEAR),
                           plan, by_term, max(1, min(limit, 100)))
    if "options" in out:
        desc = db.descriptions(DB, YEAR, [o["code"] for o in out["options"]])
        out["options"] = [o | {"description": desc.get(o["code"])} for o in out["options"]]
    out["catalog_year"] = YEAR
    out["warnings"] = year_warning(profile) + out.get("warnings", []) + [NO_OFFERINGS]
    return out


PLAN_MY_DEGREE = """You're helping an SF State student plan their degree with GatorPath ({year} Bulletin). Every course, prereq,
requirement and date comes from the tools: never add one they didn't return, and never present a plan check_plan
hasn't passed.{goal}{deadline}

1. Profile. Ask only for what's missing, one short question at a time:
   - program (`list_programs`) and catalog year, the "Requirement (Catalog) Term" on their DPR. If it isn't {year},
     say the plan uses {year} rules and theirs may differ.
   - completed courses (code, grade, term) and in-progress courses. Don't ask them to upload a transcript or DPR PDF
     into the chat: that sends their name and ID to the AI provider. Ask them to type or paste just the course rows.
   - transfer students: courses the DPR lists under a requirement count as that course with `transfer: true` (DPR
     row "MATH 100TR" under "MATH 226" = MATH 226). Use the grade from the other school's transcript. If they only
     have the DPR's "T", use the requirement's minimum (C for the major) and tell them you assumed it. Transfer GE
     areas go in `ge_done`, total transfer units in `transfer_units`. Never guess what transfer credit covers.
   - qr_pathway (math placement "1/2" or "3/4") unless they're done with lower-division math or have an ADT
     (`adt: true`); gpa if they know it; max_units_per_term (default 15) and include_summer.
2. `audit_progress`: summarize done / in progress / left, with Bulletin pages and every warning.
3. `build_plan`. If it returns needs_input, ask for it. Use each semester's `why` to explain key placements
   ("CSC 413 opens 13 senior electives; delaying it pushes back CSC 648").
4. Fill every slot. For each one call `list_eligible_electives` with group_id = the slot, plan = the current plan
   and by_term = the slot's term. Pick by the student's goal: 'ready' first; 'check' only after saying what can't be
   checked (cannot_check). Prefer options whose also_covers clears other open requirements: one course can cover
   upper-division GE and SF State Studies at once. Senior electives: at least 12 of the 15 units in CSC. A 0-unit tag
   slot (SF State Studies, American Institutions) is met by a chosen course whose also_covers includes it: then drop
   the tag. Otherwise fill it from its own group and add the units. Free `elective` slots: any course; suggest ones
   that fit the goal.
5. `check_plan` the filled plan. Fix every error and re-check until valid.
6. Pace ("3, 4 or 5 years?", "graduate early?"): call `build_plan` with graduate_by and at 12, 15 and 18 units per
   term + include_summer. Show a table: load, est_graduation_term, on_time, why_not. Over 15 units is above the
   normal load (p.2393), so it needs an advisor.
7. What-ifs: earlier graduation → step 6. New direction (AI, security, …) → steps 4-5 with the new goal; required
   courses don't change. Switching majors isn't supported yet: say so.
8. Present:
   - one table per term, in the order to enter it in Student Center → Degree Planner: course, units, what it counts
     for, why
   - warnings and Bulletin pages
   - every `see_advisor` item: who, why, link, and how to book
   - a checklist: confirm each course is offered that term in Class Search (GatorPath has no schedule data yet),
     compare with the DPR, and see the advisor
Keep it short; offer details instead of dumping them."""


@mcp.prompt(title="Plan my degree")
def plan_my_degree(goal: str = "", graduate_by: str = "") -> str:
    """Step-by-step workflow: profile → audit → plan → electives by goal → check_plan → pace/what-ifs → advisor."""
    # ponytail: no load_profile / import_dpr steps yet. Add them to the workflow when those tools land (TASKS phase 4, 6).
    return PLAN_MY_DEGREE.format(year=YEAR, goal=f"\n\nThe student's goal: {goal}." if goal else "",
                                 deadline=f" They'd like to graduate by {graduate_by} (pass it as graduate_by)."
                                 if graduate_by else "")
