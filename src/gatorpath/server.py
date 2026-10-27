"""MCP tools (ARCHITECTURE §7). Thin: check input, read catalog.db and rules/, call engine/, add catalog_year + warnings."""

import difflib
import json
import os
import re
import subprocess
from datetime import date
from functools import cache
from pathlib import Path
from typing import NotRequired, TypedDict
from urllib.parse import quote

import yaml
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from gatorpath import db, dpr, transcript
from gatorpath.engine.planner import build_plan as engine_build_plan
from gatorpath.engine.planner import compare_programs as engine_compare_programs
from gatorpath.engine.planner import check_plan as engine_check_plan
from gatorpath.engine.planner import TERM, cover_combinations, eligible_options, see_advisor
from gatorpath.engine.prereq import prereq_chain, prereq_warnings, reverse_index
from gatorpath.engine.rules import RULES_DIR, audit, load_rules, min_grade_of, number, translate_ge

# Requirements follow the student's catalog year (rules/<kind>/<year>/); course facts are the newest Bulletin's (D23).
YEARS = sorted(p.stem for p in (RULES_DIR / "university").glob("*.yaml"))
YEAR = YEARS[-1]
REPO = Path(__file__).parents[2]
DB = REPO / "data/catalog.db"
PROFILE_PATH = "~/.gatorpath/profile.yaml"
LEVELS = {"lower": (100, 300), "upper": (300, 700), "graduate": (700, 1000)}
NO_OFFERINGS = "Offering history isn't loaded (run ingest.offerings), so `offered` is 'unknown'; check Class Search"
RMP = "https://www.ratemyprofessors.com/search/professors/880?q="  # 880: SF State on RMP, checked 2026-10-27
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITES_FILE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    "gatorpath",
    instructions=(
        f"SF State degree-planning tools for the {', '.join(YEARS)} Bulletins: requirements follow the student's catalog "
        f"year, courses and prereqs are the newest ({YEAR}). Answers come only from the Bulletin and reviewed rules: "
        "don't add courses, prereqs or requirements the tools didn't return. Cite the `source`/`source_page` each answer "
        "comes with (Bulletin pages; a few office policies cite that office's page), show every warning, and remind "
        "the student that the DPR and an advisor are the final word. A course meets a GE, SF State Studies or American "
        "Institutions area only where a tool shows it (`ge_areas`, `counted`, `major_courses`): never infer one from "
        "a course's subject or title. "
        "Never guess what transfer credit covers or when a student will graduate: ask for the DPR, and use the planner "
        "tools when they exist. After a plan passes check_plan, show its first term's sections (class number, days, "
        "times, room, instructor, seats) with get_sections when that term's schedule is out. "
        "Student profiles are passed in per call and never stored, except by save_profile: one file on the student's "
        "machine, only when they ask."
    ),
)


class CourseTaken(TypedDict):
    code: str
    grade: str
    term: NotRequired[str]
    units: NotRequired[float]
    transfer: NotRequired[bool]
    credit: NotRequired[str]


class Profile(TypedDict):
    program: str
    catalog_year: NotRequired[str]
    qr_pathway: NotRequired[str]
    start_term: NotRequired[str]
    completed: NotRequired[list[CourseTaken]]
    in_progress: NotRequired[list[str]]
    gpa: NotRequired[float]
    ge_done: NotRequired[list[str]]
    dpr_met: NotRequired[list[str]]
    not_on_dpr: NotRequired[list[str]]
    approved: NotRequired[dict[str, list[str]]]
    first_time: NotRequired[bool]
    ge_certified: NotRequired[bool]
    prior_bachelors: NotRequired[bool]
    transfer_units: NotRequired[float]
    adt: NotRequired[bool]
    f1: NotRequired[bool]
    max_units_per_term: NotRequired[float]
    include_summer: NotRequired[bool]
    include_winter: NotRequired[bool]
    graduate_by: NotRequired[str]
    goal: NotRequired[str]
    chosen_electives: NotRequired[list[str]]
    plan: NotRequired["Plan"]
    dpr_imported: NotRequired[str]


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
def offering_note(path: Path, year: str) -> str:
    """What the Class Search history covers, said once per answer."""
    rows = [(c.rsplit(" ", 1)[0], r["offered"]) for c, r in catalog(path, year).items() if "offered" in r]
    if not rows:
        return NO_OFFERINGS
    spans = sorted({f"{o['since']} to {o['until']}" for _, o in rows})
    return (f"Offering history (Class Search, {', '.join(spans)}) covers {', '.join(sorted({s for s, _ in rows}))}; "
            "`offered` gives [terms it ran, terms checked] per season. Other subjects are unknown, and past terms don't "
            "promise future ones: check Class Search")


def offered(code: str) -> dict | str:
    """History per season, and whether it's on the latest scraped term's schedule (a published next term)."""
    o = catalog(DB, YEAR).get(code, {}).get("offered")
    return {k: v for k, v in o.items() if k != "schedule"} | {"schedule": {o["until"]: o["schedule"][o["until"]]}} if o else "unknown"


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


@cache  # parsed once per server process: rules/ doesn't change while it runs
def programs() -> dict[str, dict]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted((RULES_DIR / "programs" / YEAR).glob("*.yaml"))}


def unknown_program(program: str) -> dict:
    return {"catalog_year": YEAR, "error": "unknown_program", "program": program, "programs": list(programs()),
            "warnings": [f"{program!r} has no rules for {YEAR}; GatorPath only answers for the listed programs"]}


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
    rows = [r | {"offered": offered(r["code"])} for r in db.search_courses(DB, YEAR, query)
            if (not want or r["code"].rsplit(" ", 1)[0].replace(" ", "") == want) and lo <= number(r["code"]) < hi]
    rows.sort(key=lambda r: r["code"] != exact)  # stable: an exact code hit first, then FTS rank
    return {"catalog_year": YEAR, "results": rows[:max(1, min(limit, 50))], "total_matches": len(rows),
            "warnings": [offering_note(DB, YEAR)]}


@mcp.tool(annotations=READ_ONLY)
def get_course(code: str) -> dict:
    """Full Bulletin record for one course: description, units, grading, GE areas, prereq (raw text + parsed tree +
    status), paired/cross-listed links, source_page, and `unlocks`: courses whose prereqs name it (as a requirement or
    one of the alternatives), so a student sees what skipping or delaying it holds up. A '*' after a prereq item means
    registration enforces it; items without one may be enforced by the instructor up to the end of add/drop (p.2436)."""
    code = norm_code(code)
    course = db.get_course(DB, YEAR, code)
    if course is None:
        return unknown_course(code)
    return course | {"offered_terms": offered(code), "unlocks": unlocks(DB, YEAR).get(code, []),
                     "warnings": prereq_warnings(code, course["prereq"]) + [offering_note(DB, YEAR)]}


@mcp.tool(annotations=READ_ONLY)
def get_sections(term: str, codes: list[str]) -> dict:
    """Class Search sections of courses in one term (e.g. '2027-spring'), to show after a plan for its first term once
    that term's schedule is out: class number (class_nbr, what Student Center asks for), meetings (days, time,
    where), mode, instructor, seats_open, waitlist_open, enrolled, and attributes (permission numbers, GE tags; Class
    Search shows no capacity). rate_my_professors: {instructor: a Rate My Professors search} per named instructor, links for
    the student to open (anonymous student opinion, not SF State's). `not_offered`:
    no section that term (move it in the plan, then check_plan). `unknown`: GatorPath has no schedule for that
    subject and term (not out yet, or a subject it didn't scrape): check Class Search. A snapshot from scraped_at:
    seats, rooms and instructors change, so the student confirms in Class Search before registering."""
    if not TERM.fullmatch(term):
        return {"catalog_year": YEAR, "error": "bad_term", "warnings": ["term looks like 2027-spring"]}
    want = list(dict.fromkeys(norm_code(c) for c in codes))
    known = [c for c in want if c in catalog(DB, YEAR)]
    found, scraped = db.sections(DB, term, known)
    for sec in (x for xs in found.values() for x in xs):  # D26: links, never fetched (RMP's terms ban scraping)
        names = sec.get("instructor", "").split(", ")  # ingest.offerings joins a co-taught section's names
        if links := {n: RMP + quote(n) for n in names if n and n != "To be announced"}:
            sec["rate_my_professors"] = links
    subject = lambda c: c.rsplit(" ", 1)[0]
    stamp = min((scraped[subject(c)] for c in found), default=None)
    return {"catalog_year": YEAR, "term": term, "sections": found,
            "not_offered": [c for c in known if c not in found and subject(c) in scraped],
            "unknown": [c for c in known if c not in found and subject(c) not in scraped], "scraped_at": stamp,
            "warnings": ([f"Not in the {YEAR} Bulletin: {', '.join(c for c in want if c not in known)}"]
                         if len(known) < len(want) else [])
                        + [f"Class Search as of {stamp or 'never'}: seats, rooms and instructors change; confirm in "
                           "Class Search (webapps.sfsu.edu/public/classservices/classsearch) before registering"]}


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
    """Programs GatorPath has requirement rules for. verified: a person checked them against the Bulletin; drafted:
    AI-drafted from the Bulletin's text and checked by program (codes, pages, word-for-word quotes, units, a test plan),
    not yet by a person: say so when planning with one."""
    return {"catalog_year": YEAR, "catalog_years": YEARS, "warnings": [],
            "programs": [{"id": k, "title": p["title"], "verified": bool(p.get("verified")), "drafted": bool(p.get("drafted_by"))}
                         for k, p in programs().items()]}


@mcp.tool(annotations=READ_ONLY)
def get_program_requirements(program: str, catalog_year: str | None = None) -> dict:
    """A program's requirement groups (as written in its rules YAML, each with its Bulletin page) plus the university
    graduation requirements every bachelor's degree shares: GE areas, SF State Studies, American Institutions, GWAR,
    unit/residence/GPA totals. catalog_year: the student's (e.g. 'Fall 2025' or '2025-26'); default the newest."""
    if program not in programs():
        return unknown_program(program)
    year = rules_year({"program": program, "catalog_year": catalog_year or YEAR})
    prog, univ = load_rules(year, program)
    return {"catalog_year": year, "program": prog, "university": univ,
            "warnings": unverified(prog, program) + unverified(univ, "University (GE and graduation)")}


@mcp.tool(annotations=READ_ONLY)
def get_roadmap(program: str, variant: str | None = None, catalog_year: str | None = None) -> dict:
    """The Bulletin's suggested semester-by-semester roadmap. Items are course codes or slots like
    {slot: GE, area: "1A", units: 3}. Without a valid variant, returns the variants to choose from (for BS CS the
    variant follows the student's QR pathway / math placement, or the ADT for transfer students). catalog_year: the
    student's (e.g. 'Fall 2025'); default the newest."""
    if program not in programs():
        return unknown_program(program)
    year = rules_year({"program": program, "catalog_year": catalog_year or YEAR})
    path = RULES_DIR / "roadmaps" / year / f"{program}.yaml"
    if not path.exists():
        return unknown_program(program)
    rm = yaml.safe_load(path.read_text())
    warnings = ["The roadmap is a suggestion and doesn't replace meeting with an advisor"] + unverified(rm, f"{program} roadmap")
    if variant not in rm["variants"]:
        return {"catalog_year": year, "program": program, "needs_input": "variant", "warnings": warnings,
                "variants": {k: {"title": v["title"], "qr_pathway": v.get("qr_pathway")} for k, v in rm["variants"].items()}}
    return {"catalog_year": year, "program": program, "variant": variant, **rm["variants"][variant], "warnings": warnings}


def held_to(given) -> str | None:
    """A catalog term or year as a Bulletin year: "Fall 2025", "2025-fall", "2025-26" or "2025-2026" -> "2025-26" (a
    Bulletin runs fall to summer); None when it isn't one."""
    s = str(given or "").strip().lower()
    if m := re.fullmatch(r"(\d{4})-(\d{2}|\d{4})", s):
        start = int(m[1])
        if int(m[2]) % 100 != (start + 1) % 100:
            return None
    elif m := re.fullmatch(r"(fall|spring|summer|winter) (\d{4})|(\d{4})-(fall|spring|summer|winter)", s):
        season, y = (m[1], int(m[2])) if m[1] else (m[4], int(m[3]))
        start = y if season == "fall" else y - 1
    else:
        return None
    return f"{start}-{(start + 1) % 100:02d}"


def rules_year(profile: dict) -> str:
    """The Bulletin year the student is held to, when GatorPath has its rules for the program; else the newest
    (year_warning says so)."""
    year = held_to(profile.get("catalog_year"))
    return year if year and (RULES_DIR / "programs" / year / f"{profile['program']}.yaml").exists() else YEAR


def year_warning(profile: dict, year: str) -> list[str]:
    given = profile.get("catalog_year")
    have = [y for y in YEARS if (RULES_DIR / "programs" / y / f"{profile['program']}.yaml").exists()]
    if given is None:
        return [f"catalog_year not given, so this uses the {YEAR} Bulletin. Students are held to the year on their DPR "
                "('Requirement (Catalog) Term'); if it's earlier, requirements (GE areas especially) may differ"]
    if held_to(given) == year:  # the student's own year
        return [] if year == YEAR else [
            f"Requirements are the {year} Bulletin's (the student's catalog year, {given}); courses, prereqs and GE "
            f"tags are the {YEAR} Bulletin's, the one the remaining courses are taken under"]
    return [f"The student's catalog year is {given}, but GatorPath has {profile['program']} rules only for {', '.join(have)}, so this uses "
            f"{YEAR}. Requirements may differ (GE areas especially). Where the DPR disagrees, the DPR "
            "wins. In continuous attendance a student may elect the graduation requirements in effect when they began "
            "their study, when they entered SF State, or when they graduate (p.2390); ask an advisor before relying on that"]


def prepare(profile: dict, university: dict, year: str = YEAR) -> tuple[dict, list[str]]:
    """Normalize what a client sends (codes, DPR GE area names) and say what was assumed or translated."""
    ge_done, ge_warnings = translate_ge(profile.get("ge_done", []), university)
    # not_on_dpr: group ids, or GE areas in the DPR's or this Bulletin's codes ("6", "F", "Area 6")
    groups = {g["id"]: g for g in university["groups"]}
    by_area = {str(a): gid for gid, g in groups.items() if isinstance(g.get("from"), dict) and "ge_area" in g["from"]
               for a in ([g["from"]["ge_area"]] if not isinstance(g["from"]["ge_area"], list) else g["from"]["ge_area"])}
    left_out = []
    for x in profile.get("not_on_dpr", []):
        if str(x) in groups or str(x) in {g["id"] for g in load_rules(year, profile["program"])[0]["groups"]}:
            left_out.append(str(x))
        else:
            areas, w = translate_ge([x], university)
            left_out += [by_area[a] for a in areas if a in by_area]
            ge_warnings += [m for m in w if "not recognized" in m]
    # "QR 3/4", "Category 1/2", "3-4" -> the roadmaps' "3/4" / "1/2". ponytail: digits only; add "III/IV" if a client sends it
    digits = set(re.findall(r"[1-4]", str(profile.get("qr_pathway", ""))))
    qr = next((k for k in ("1/2", "3/4") if digits and digits <= set(k[::2])), profile.get("qr_pathway"))
    clean = profile | ({"qr_pathway": qr} if qr else {}) | {
                       "current_term": term_start(today())[0],  # the term underway: never plan on top of it
                       "catalog_year": year, "ge_done": ge_done, "not_on_dpr": list(dict.fromkeys(left_out)),
                       "completed": [r | {"code": norm_code(r["code"])} for r in profile.get("completed", [])],
                       "in_progress": [norm_code(c) for c in profile.get("in_progress", [])],
                       "dpr_met": [norm_code(c) for c in profile.get("dpr_met", [])],
                       "approved": {g: [norm_code(c) for c in cs] for g, cs in (profile.get("approved") or {}).items()}}
    return clean, year_warning(profile, year) + ge_warnings


def load_for(profile: dict) -> tuple[str, dict, dict, dict, list[str]]:
    """The student's rules year, its program and university rules, the cleaned profile and what was assumed."""
    year = rules_year(profile)
    program, university = load_rules(year, profile["program"])
    return year, program, university, *prepare(profile, university, year)


def catalog_for(profile: dict) -> dict[str, dict]:
    """The newest Bulletin's courses; a completed course dropped since keeps its row from the latest year that has it."""
    cat = catalog(DB, YEAR)
    gone = {r["code"] for r in profile.get("completed", [])} - cat.keys()
    for year in YEARS[:-1]:  # oldest first, so a later year's row wins
        cat = cat | {c: r for c, r in catalog(DB, year).items() if c in gone}
    return cat


def normalized_plan(plan: dict | None) -> dict | None:
    return plan and {"semesters": [s | {"courses": [norm_code(c) if isinstance(c, str) else c for c in s.get("courses", [])]}
                                   for s in plan.get("semesters", [])]}


def profile_error(profile: dict) -> dict | None:
    if profile["program"] not in programs():
        return unknown_program(profile["program"])
    return None


@mcp.tool(annotations=READ_ONLY)
def audit_progress(profile: Profile) -> dict:
    """Degree audit: per requirement group satisfied / in_progress / remaining / waived (or unparsed: a rule GatorPath
    can't check, with the Bulletin's `quote`) and which courses counted, plus university totals (120 units,
    upper-division, residence, CR cap, GPAs). Nothing is stored.

    profile: program (e.g. 'bs-cs'); catalog_year (the DPR's "Requirement (Catalog) Term", e.g. 'Fall 2025': that
    year's rules when GatorPath has them, else the newest with a warning); completed: [{code, grade, term?, units? (variable-unit
    courses), transfer? (articulated transfer course), credit? ('extension' | 'exam' | 'evaluation': counts for
    units, never residence)}], grades as SF State symbols (A..F, CR, NC, W, I);
    in_progress: [codes]; ge_done: GE areas met by transfer/AP/IB credit, as the DPR writes them (e.g. "1A", or an
    older catalog's "A2", "D", "UD-D": translated automatically), also USH/USG/CSLG; dpr_met: required courses the
    DPR shows met by a substitution or exception (e.g. MATH 225 met by MATH 325); not_on_dpr: requirements the
    tools list but the student's DPR doesn't have at all (an older catalog, e.g. GE "6" Ethnic Studies): left out and
    flagged for an advisor to confirm; first_time (began at SF State as a first-time college student; leave it out
    unless the student says: without it, transfer work decides); ge_certified (Cal-GETC certification of lower-division GE, p.2304); prior_bachelors (already holds
    a bachelor's or higher degree from a regionally accredited institution: GE and graduation requirements waived,
    p.2313); transfer_units: total transfer units; adt: true only for a verified AA-T/AS-T from a California Community
    College in a similar approved major (waives SF State Studies, p.2313); approved: {group id: [codes]}, the courses
    the student's advisor approved for a group with `approval` (BS Applied Mathematics application electives: no
    Bulletin list), from the DPR or the student; gpa optional. A group with `options` is a "Select One": `remaining`
    is one option, and the student may take another.
    """
    if err := profile_error(profile):
        return err
    year, program, university, clean, notes = load_for(profile)
    out = audit(clean, program, university, catalog_for(clean))
    out["warnings"] = notes + out["warnings"] + unverified(university, "University (GE and graduation)")
    out["see_advisor"] = see_advisor([("dpr", "Your DPR is the official audit; compare it with this one")]
                                     + ([("major_advisor", f"GatorPath's {profile['program']} rules aren't verified yet")]
                                        if not program.get("verified") else []), program, university)
    return out


@mcp.tool(annotations=READ_ONLY)
def check_plan(profile: Profile, plan: Plan) -> dict:
    """Validate a term-by-term plan. **Call this before presenting any plan, fix every error, and re-check until
    valid.** Errors (with Bulletin text/pages): prereq not met by that term, course already passed or planned twice,
    unknown course, units over the term's cap (profile.max_units_per_term, else the term's max_units, else 15),
    requirement or 120/upper-division units not covered. Warnings: unverifiable prereqs (GPA not given, permission),
    loads above the normal 15 (p.2393; "as on the Bulletin roadmap" with no advisor when the term's roadmap semester
    prints that load), unfilled slots.
    profile.f1: true for an F-1 visa student: a spring/fall term under 12 units is an error (the plan's last term: a
    warning and the international office), and so is a skipped spring/fall term (pp.2390, 2393).

    plan: {semesters: [{term: '2027-fall', courses: ['CSC 413', {slot: 'senior_electives', units: 3}]}]}. Pass
    build_plan's semesters back as returned: their max_units and roadmap {units, source} keep the roadmap's loads. A slot is an
    unfilled pick for a requirement group (group ids from get_program_requirements), or {slot: 'elective', units: 3,
    upper_division?: true} for free units. Terms are YYYY-spring/summer/fall, or YYYY-winter for Winter Session (January,
    between fall and spring, at most 4 units), after the profile's completed terms.
    """
    if err := profile_error(profile):
        return err
    year, program, university, clean, notes = load_for(profile)
    out = engine_check_plan(clean, normalized_plan(plan), program, university, catalog_for(clean), prereqs(DB, YEAR))
    out["warnings"] = notes + out["warnings"] + [offering_note(DB, YEAR)] + unverified(university, "University (GE and graduation)")
    return out


@mcp.tool(annotations=READ_ONLY)
def build_plan(profile: Profile) -> dict:
    """Deterministic baseline plan to graduation, laid out on the Bulletin roadmap: each term starts from its roadmap
    semester (what's done is skipped, what isn't ready carries over), then the remaining required courses by prereq
    chain (critical path first, corequisites together), then slots for what's open (GE areas, senior electives, free
    electives) to reach the 120 and upper-division totals. Already run through check_plan: see `check`.

    Fill each slot with list_eligible_electives + the student's goal, then call check_plan again before presenting.
    Unit loads follow the roadmap (D24): each spring/fall term's cap is the printed units of the roadmap semester the
    student's units have reached (16, 15, 16, … for a BS CS QR 1/2 freshman; the last semester's past its end; never
    under 12 for f1), shown as each semester's max_units and roadmap. max_units_per_term is the student's own cap and
    overrides it. Also include_summer, include_winter (Winter Session terms
    between fall and spring: up to 4 units of GE, American Institutions or free electives) and f1 (F-1 visa: spring/fall
    terms filled toward 12 units, pp.2390, 2393). Returns needs_input
    (qr_pathway, start_term) instead of guessing. Each semester has `why`: per course, what it's needed before, the
    chain it starts, and whether delaying it pushes back graduation. `pace` says what sets the length: the longest
    prereq chain vs the units per term (load: roadmap / max_units_per_term); normal_load is the lighter option at the
    normal 15 (terms, graduation term) when the roadmap goes above it; fold_last_term when a light last term fits into
    one earlier term (a term sooner at one heavier load). profile.graduate_by (D25) fits the loads to that goal: when the
    roadmap's loads end later, every term goes to the roadmap's heaviest semester, then one unit more at a time up to
    19, until the plan ends by then (load: graduate_by, pace.fit with the units and a note; above the roadmap's
    heaviest is an overload: advisor). pace says whether the term is reachable and, if not, why_not.
    For "3, 4 or 5 years", call it at different max_units_per_term / include_summer / include_winter.
    """
    if err := profile_error(profile):
        return err
    year, program, university, clean, notes = load_for(profile)
    path = RULES_DIR / "roadmaps" / year / f"{profile['program']}.yaml"
    out = engine_build_plan(clean, program, university, yaml.safe_load(path.read_text()), catalog_for(clean), prereqs(DB, YEAR))
    out["warnings"] = notes + out["warnings"] + [offering_note(DB, YEAR)] + unverified(university, "University (GE and graduation)")
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
    Environmental Sustainability + Global Perspectives). Re-run check_plan after filling slots. A group with
    `approval` (courses an advisor consents to, no Bulletin list) returns that text, no options, and see_advisor.
    """
    if err := profile_error(profile):
        return err
    year, program, university, clean, notes = load_for(profile)
    out = eligible_options(clean, group_id, program, university, catalog_for(clean), prereqs(DB, YEAR),
                           normalized_plan(plan), by_term, max(1, min(limit, 100)))
    if "options" in out:
        desc = db.descriptions(DB, YEAR, [o["code"] for o in out["options"]])
        out["options"] = [o | {"description": desc.get(o["code"]), "offered": offered(o["code"])} for o in out["options"]]
    out["catalog_year"] = year
    out["warnings"] = notes + out.get("warnings", []) + [offering_note(DB, YEAR)]
    return out


@mcp.tool(annotations=READ_ONLY)
def ge_combinations(profile: Profile, plan: Plan | None = None, by_term: str | None = None) -> dict:
    """Up to 8 ways (3 when more than 5 are open) to finish the open GE, SF State Studies and American Institutions
    requirements that one course can fill, fewest courses first; the first is the fewest a bounded search found, not
    a proven minimum: one course covering several (4UD + Environmental Sustainability + Global
    Perspectives), two that split them, or one each. Each part says what one course covers, how many courses fit, and
    examples (ready first, then recently offered). Show the student the ways; the parts can go in different terms.
    Pass the build_plan output as plan so planned courses count."""
    if err := profile_error(profile):
        return err
    year, program, university, clean, notes = load_for(profile)
    out = cover_combinations(clean, program, university, catalog_for(clean), prereqs(DB, YEAR), normalized_plan(plan), by_term)
    for way in out.get("ways", []):
        for part in way["parts"]:
            part["examples"] = [e | {"offered": offered(e["code"])} for e in part["examples"]]
    out["warnings"] = notes + out.get("warnings", []) + [offering_note(DB, YEAR)]
    return out


@mcp.tool(annotations=READ_ONLY)
def compare_programs(profile: Profile, target: str) -> dict:
    """What if the student changes major to `target` (a program id from list_programs)? Returns `current` and `target`:
    major units done / in progress / needed, and build_plan's terms and est_graduation_term at the profile's load;
    the target's major groups (what counts, what's left); `courses`: count_in_both, only_current (still count toward
    the 120 and GE), only_target; and `extra_terms` (target minus current). The new major is the Bulletin in effect
    when they change (quoted in warnings); GE and graduation requirements stay their catalog year's. Show the
    see_advisor items: the official check is the Student Center What-If report and the target department."""
    if err := profile_error(profile):
        return err
    if target not in programs():
        return unknown_program(target)
    if target == profile["program"]:
        return {"catalog_year": YEAR, "error": "same_program",
                "warnings": [f"{target} is already the student's program; use audit_progress and build_plan"]}
    year, program, university, clean, notes = load_for(profile)
    # "must fulfill the major requirements in effect at the time they declare or change their major": the current term's
    # Bulletin when GatorPath has the target's rules for it, else the newest
    change = held_to(clean["current_term"])
    t_year = rules_year({"program": target, "catalog_year": clean["current_term"]})
    t_program, t_university = load_rules(t_year, target)
    road = lambda y, name: yaml.safe_load((RULES_DIR / "roadmaps" / y / f"{name}.yaml").read_text())
    out = engine_compare_programs(clean, (program, road(year, profile["program"])), (t_program, road(t_year, target)),
                                  university, catalog_for(clean), prereqs(DB, YEAR))
    if "error" in out or "needs_input" in out:
        return out | {"warnings": notes + out.get("warnings", [])}
    rule = t_university.get("change_of_major")
    out["warnings"] = (notes + ([f"Changing major: \"{rule['rule']}\" How: \"{rule['how']}\" ({rule['source']}). So "
                                 f"{t_program['title']} uses the {t_year} Bulletin; GE and graduation requirements stay "
                                 f"your catalog year's ({year})"] if rule else [])
                       + ([f"GatorPath doesn't have the {change} Bulletin's {target} rules; this uses {t_year}"]
                          if change and change != t_year else [])
                       + out["warnings"] + unverified(t_program, target) + [offering_note(DB, YEAR)])
    return out


def profile_file(path: str | None) -> tuple[Path | None, str | None]:
    """The student's chosen profile file, or why it's refused (golden rule 5: never inside the repo)."""
    given = Path(path or PROFILE_PATH).expanduser()
    if not given.is_absolute():
        return None, f"give a full path, like {PROFILE_PATH}"
    resolved = given.resolve()  # follows symlinks, so the checks below see the real file
    if resolved.suffix not in (".yaml", ".yml"):
        return None, "the profile file must end in .yaml or .yml"
    if resolved.is_relative_to(REPO.resolve()):
        return None, "that path is inside the GatorPath folder, where student data never goes; pick one in your home folder"
    return resolved, None


def read_profile(path: Path) -> dict | None:
    """A saved GatorPath profile (a YAML mapping with a program), else None. Other files are never returned."""
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    return json.loads(json.dumps(data, default=str)) if isinstance(data, dict) and "program" in data else None  # dates -> str


def today() -> date:
    return date.today()  # one place for "now": tests pin it (tests/conftest.py)


def term_start(day: date) -> tuple[str, date]:
    # ponytail: month boundaries (spring Jan, summer Jun, fall Aug), not SF State's academic calendar.
    season, month = ("fall", 8) if day.month >= 8 else ("summer", 6) if day.month >= 6 else ("spring", 1)
    return f"{day.year}-{season}", date(day.year, month, 1)


def path_error(path: str | None, why: str, error: str = "bad_path") -> dict:
    return {"catalog_year": YEAR, "error": error, "path": path or PROFILE_PATH, "warnings": [why]}


@mcp.tool(annotations=WRITES_FILE)
def save_profile(profile: Profile, path: str | None = None) -> dict:
    """Save the student's profile so the next session starts from it. **Only when the student asks to save.**

    Writes one YAML file on the student's machine at `path` (default ~/.gatorpath/profile.yaml): plain text they can
    read, edit or delete, readable only by them. Replaces an earlier GatorPath profile at that path, never any other
    file; refuses paths inside the GatorPath folder. Keeps everything in the profile, plus goal, chosen_electives and
    the plan that last passed check_plan. Nothing else is stored anywhere.
    """
    file, why = profile_file(path)
    if why:
        return path_error(path, why)
    if file.exists() and read_profile(file) is None:
        return path_error(path, f"{file} exists and isn't a GatorPath profile, so it wasn't replaced", "not_a_profile")
    file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = file.with_name(file.name + ".tmp")
    try:
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as f:
            f.write("# GatorPath student profile, saved at your request. Yours to read, edit or delete.\n")
            yaml.safe_dump(dict(profile), f, sort_keys=False, allow_unicode=True)
        os.replace(tmp, file)  # all or nothing: an earlier profile survives a failed write
    except BaseException:
        tmp.unlink(missing_ok=True)  # no half-written copy of the student's grades left behind
        raise
    return {"catalog_year": YEAR, "saved": str(file),
            "warnings": [f"Saved to {file}. It holds your grades: delete it when you no longer need it"]}


@mcp.tool(annotations=READ_ONLY)
def load_profile(path: str | None = None) -> dict:
    """Read the profile the student saved with save_profile (default ~/.gatorpath/profile.yaml), to start a session
    from it. Returns `profile`, or error not_found. Warns when dpr_imported is before the current term: ask for a fresh
    DPR before planning."""
    file, why = profile_file(path)
    if why:
        return path_error(path, why)
    if not file.exists():
        return path_error(path, f"No saved profile at {file}", "not_found")
    if (profile := read_profile(file)) is None:
        return path_error(path, f"{file} isn't a GatorPath profile", "not_a_profile")
    warnings = []
    if imported := profile.get("dpr_imported"):
        term, start = term_start(today())
        try:
            stale = date.fromisoformat(imported) < start
        except (TypeError, ValueError):
            stale, warnings = False, [f"dpr_imported {imported!r} isn't a date (YYYY-MM-DD)"]
        if stale:
            warnings.append(f"The DPR was imported {imported}, before the current term ({term}): ask for a fresh DPR "
                            "(Student Center → Degree Progress Report) so new grades and courses are included")
    return {"catalog_year": YEAR, "profile": profile, "path": str(file), "warnings": warnings}


@mcp.tool(annotations=READ_ONLY)
def import_transcript(pdf_path: str) -> dict:
    """Read the student's SF State unofficial transcript PDF on their own machine (Student Center → Unofficial
    Transcript, saved as a PDF) and return only course codes, grades, units and terms: completed, in_progress,
    transfer_units. Name, ID, birthdate and the PDF text never leave this tool, so the student doesn't need to attach
    the PDF to the chat; ask for the file's path instead. Merge the result into the profile. Transfer courses show as
    totals only: their requirements come from the DPR."""
    path = local_pdf(pdf_path, "~/Downloads/SSR_TSRPT.pdf")
    if isinstance(path, dict):
        return path
    try:
        out = transcript.parse(transcript.read_pdf(path))
    except (OSError, subprocess.CalledProcessError):
        return {"catalog_year": YEAR, "error": "unreadable_pdf", "warnings": ["pdftotext couldn't read that PDF (or isn't installed: brew install poppler)"]}
    if "completed" in out:
        out["completed"] = [r | {"code": norm_code(r["code"])} for r in out["completed"]]
        out["in_progress"] = [norm_code(c) for c in out["in_progress"]]
    return {"catalog_year": YEAR} | out


def local_pdf(pdf_path: str, example: str) -> Path | dict:
    path = Path(pdf_path).expanduser()
    if not path.is_absolute() or path.suffix.lower() != ".pdf" or not path.is_file():
        return {"catalog_year": YEAR, "error": "bad_path",
                "warnings": [f"Give the full path to the PDF on this computer, e.g. {example}"]}
    return path


@mcp.tool(annotations=READ_ONLY)
def import_dpr(pdf_path: str) -> dict:
    """Read the student's Degree Progress Report on their own machine (Student Center → Degree Progress Report,
    printed to PDF; click Expand All and View All on long lists first) and return a ready `profile` (completed SF State and transfer
    courses, in_progress, ge_done, dpr_met substitutions, gpa, catalog_year from the DPR's "Requirement (Catalog)
    Term") plus `remaining`: what the DPR itself says is still needed, and `cross_check`: where GatorPath's audit
    disagrees with the DPR (the DPR wins). Name, ID and the PDF text never leave this tool,
    so the student doesn't need to attach the PDF to the chat; ask for the file's path. Add qr_pathway, goal and
    start_term, then use the profile with the other tools."""
    path = local_pdf(pdf_path, "~/Downloads/Degree Progress Report.pdf")
    if isinstance(path, dict):
        return path
    try:
        parsed = dpr.parse(dpr.read_pdf(path))
    except (OSError, subprocess.CalledProcessError):
        return {"catalog_year": YEAR, "error": "unreadable_pdf", "warnings": ["pdftotext couldn't read that PDF (or isn't installed: brew install poppler)"]}
    if not parsed["requirements"]:
        return {"catalog_year": YEAR, "error": "unrecognized_dpr_format",
                "warnings": ["No requirements found: is this the Degree Progress Report printed from Student Center?"]}
    program = next((k for k, p in programs().items() if p.get("dpr_plan") == parsed["plan"]), None)
    warnings = list(parsed["warnings"])
    if program is None:
        return {"catalog_year": YEAR, "error": "unknown_program", "programs": list(programs()),
                "warnings": warnings + [f"The DPR's plan isn't one GatorPath has rules for; it covers {', '.join(programs())}"]}
    year = rules_year({"program": program, "catalog_year": parsed["catalog_term"]})
    rules, university = load_rules(year, program)
    loose = "C-" if rules.get("global", {}).get("no_cr_nc") else "CR"
    min_grade = {c: min_grade_of(g, c) or loose for g in rules["groups"]
                 for c in g.get("all_of", []) + [c for opt in g.get("one_of", []) for c in opt]}
    units = {c: r["units_min"] for c, r in catalog(DB, YEAR).items()}
    got = dpr.to_profile(parsed, min_grade, units)
    profile = {"program": program, **{k: v for k, v in got.items() if k not in ("remaining", "warnings")}}
    profile["completed"] = [r | {"code": norm_code(r["code"])} for r in profile["completed"]]
    profile["in_progress"] = [norm_code(c) for c in profile["in_progress"]]
    profile["dpr_met"] = [norm_code(c) for c in profile["dpr_met"]]
    ours = audit_progress(profile)
    disagree = dpr.cross_check(parsed, ours, university)
    return {"catalog_year": year, "profile": profile, "remaining": got["remaining"], "cross_check": disagree,
            "warnings": warnings + got["warnings"] + disagree + year_warning(profile, year),
            "see_advisor": see_advisor([("dpr", "GatorPath's audit and your DPR disagree on what's listed in cross_check; "
                                         "the DPR is the official one")] if disagree else [], rules, university)}


PLAN_MY_DEGREE = """You're helping an SF State student plan their degree with GatorPath (Bulletins {years}). Every course, prereq,
requirement and date comes from the tools: never add one they didn't return, and never present a plan check_plan
hasn't passed.{goal}{deadline}

Keep it fast. Ask once, in one message, for everything still missing, then work through to a finished plan without
stopping for confirmation. Never ask one question at a time or re-ask what they gave. Fill optional gaps with stated
defaults (15 units per term, no summer or Winter Session) instead of asking. What the student doesn't mention is none: no prior degree,
no AP / IB or transfer credit, nothing in progress. Say so in one line and plan; don't ask them to confirm it.

1. Start with `load_profile` (no path: the default file). If it returns a profile, start from it and ask only what's
   missing or changed; if it warns the DPR is stale, ask for a fresh one. If their message already gives their record
   (their courses; what their transfer credit meets, e.g. a GE certification and no major courses; or that they have
   none yet), use it and don't ask for one; the answer says to compare with the DPR. A unit total alone isn't a
   record. Otherwise ask for their record. Best is the
   path to their DPR saved as a PDF on this computer (Student Center → Degree Progress Report → Expand All, View
   All on long lists → print to PDF): `import_dpr` reads it locally and returns a ready profile, and no name or ID reaches you.
   The unofficial transcript PDF works the same way (`import_transcript`), but it doesn't say which requirements
   transfer credit meets. If they'd rather attach or paste instead, say once, before they share, that an attached
   PDF includes their name and student ID, which go to the AI provider, so they may black those out or paste only
   the requirement sections; never repeat it after they share. A typed course list works too, and an incoming
   student with nothing yet needs no record at all: just their first term (start_term), plus the questions below,
   and AP / IB / transfer credit if any. In the same message, ask only for what a DPR can't show and isn't given
   above: the
   goal, a graduation target, whether they're on an F-1 student visa (it sets a 12-unit minimum every spring and
   fall), and the math placement (QR "1/2" or "3/4") if lower-division math isn't done.
2. Build the profile. From import_dpr, use its `profile` as is, and tell the student its warnings (grades it had
   to assume for transfer rows, Notes codes) and every cross_check line (where GatorPath disagrees with the DPR; the
   DPR wins). Otherwise build it from what they shared:
   - catalog_year: the DPR's "Requirement (Catalog) Term", e.g. "Fall 2025". The tools use that year's rules when
     they have them ({years}); otherwise they plan with {year} rules and warn: keep going. Where the DPR and the tools disagree, the DPR wins: say so.
   - completed: each course with a grade (code, grade, term). A course with a term and no grade is in_progress.
   - transfer: "MATH 100TR" listed under the "MATH 226" requirement means MATH 226 met by transfer:
     {{code: "MATH 226", grade, transfer: true}}. Use the other school's grade; with only the DPR's "T", use the
     requirement's minimum (C for the major) and say you assumed it. Never guess what transfer credit covers
     beyond what the DPR shows.
   - ge_done: GE areas the DPR shows complete, in the DPR's own codes ("A2", "D", "UD-D", or "1A"); the tools
     translate older codes. Plus USH / USG / CSLG when American Institutions are met.
   - dpr_met: required courses the DPR shows met by a different course (MATH 325 listed under "MATH 225").
   - not_on_dpr: requirements audit_progress lists that the DPR doesn't have at all (older catalogs, e.g. GE "6"
     Ethnic Studies); import_dpr's cross_check names them ("Not found on this DPR"). Add only those the student
     confirms their DPR lacks, re-run, and tell them to confirm with an advisor.
   - gpa from the DPR; transfer_units; adt: true only for a verified AA-T/AS-T from a California Community College
     in a similar approved major; ge_certified: true for Cal-GETC certification of lower-division GE; first_time:
     false for transfer students; prior_bachelors: true if they already hold a bachelor's or higher degree from a
     regionally accredited institution; f1: true for an F-1 visa student.
   - approved: for a group with `approval` (no Bulletin list, an advisor's consent), the courses the DPR lists under
     it or the student says their advisor approved: {{group id: [codes]}}.
   - exam credit (AP / CLEP): put US History and US Government in ge_done as USH / USG only when the DPR shows them;
     no AP or CLEP exam meets California government (CSLG), p.2350.
3. Ask when they want to graduate (a term, e.g. 2030-spring) unless they said, and pass it as graduate_by: the
   plan's loads fit that goal, starting from the roadmap's own (the normal range). Then `audit_progress`, then
   `build_plan`. If build_plan returns needs_input, ask for just that.
4. Fill every slot: `list_eligible_electives` with group_id = the slot, plan = the current plan, by_term = the slot's
   term. Pick by the goal: 'ready' first, 'check' only after saying what can't be checked. Prefer options whose
   also_covers clears other open requirements (one course can cover upper-division GE and SF State Studies), and
   options that ran recently in that term's season (`offered`: [terms it ran, terms checked] per season, and `last`).
   For an F-1 student, prefer options without that season in `offered.online_only` (its last run was fully online,
   and only 3 online units count toward their 12).
   GE and SF State Studies slots are the student's choice: call `ge_combinations` (with the plan) and show its ways
   as a short table, fewest courses first, with 2-3 example courses per part (one course can cover several, or they
   can split them, e.g. 4UD + Environmental Sustainability this term and Global Perspectives the next). Put the
   first way (the fewest courses found) in the plan by default and say any other way works.
   Major electives: meet any min_units_from (BS CS senior electives: at least 12 of the 15 units in CSC); name a
   backup for each. A group with `approval` has no options to list: keep its slots, say the advisor approves those
   courses before they're taken (see_advisor), and fill them only with courses the student says were approved. A
   "Select One" group (audit `options`) is the student's pick: build_plan plans the first, so name the others.
   A 0-unit tag slot is met by a
   chosen course whose also_covers includes it (then drop the tag); otherwise fill it from its own group and add the
   units. Free `elective` slots: suggest courses that fit the goal.
5. `check_plan` the filled plan; fix every error and re-check until valid. Before calling a course optional, take
   it out and re-check: it's optional only if the plan stays valid (units_short means it's needed). For an F-1
   student, don't add courses only to keep the last term at 12: the final-semester Reduced Course Load covers it
   (check_plan's warning says how to request it). If an error stays that no change to the plan fixes (a major
   course passed with CR that can't be repeated; a limit the student set, like F-1 with a 12-unit cap), stop
   re-checking: present no plan as final, say what causes it and what would lift it (a petition, a higher
   max_units_per_term, a summer or Winter Session), and show its see_advisor.
6. A graduation target or "3, 4 or 5 years?": `build_plan` as is (the roadmap's own loads, the default), then at 12 and
   18 units per term + include_summer (+ include_winter), then a table: load, est_graduation_term, on_time, why_not.
   A term over 15 that matches its roadmap semester is "as on the Bulletin roadmap": no advisor; above the roadmap's
   load (or 15 off it) is an overload (p.2393): advisor. When pace.normal_load is there, the normal 15 is the lighter
   row: offer it from its note. When pace.fold_last_term is there, moving the light last term
   into one earlier term finishes a term sooner with only that term heavier: offer it as a row, from its note.
   "What if I switch to <major>?": `compare_programs` with target = its id from list_programs. Show what counts in
   both, what only the current major used (still toward the 120), what the new one still needs, and extra_terms;
   quote its change-of-major warning (the new major is the Bulletin in effect when they change) and its see_advisor;
   the official check is the Student Center What-If report.
7. Present, briefly:
   - done / left, with Bulletin pages, and every point where the DPR and the tools disagree
   - one table per term, in the order to enter it in Student Center → Degree Planner: course, units, what it counts
     for, why
   - warnings, and every `see_advisor` item: who, why, link, how to book. For F-1 students, GatorPath knows only the
     Bulletin's 12-unit minimum and continuous enrollment, and the international office's final-semester Reduced
     Course Load (check_plan's warning): send every other visa question (I-20 dates, OPT) to the international
     office without stating visa rules yourself
   - the first term's schedule, after the plan: `get_sections` with that term and its courses (slots filled). Per
     course, a table of its sections: class number, days, time, where, mode, instructor (each name linked to
     its rate_my_professors search, labeled student opinion), seats open (0: full, give
     waitlist_open), and attributes (a permission number, GE tags); a lecture with labs shows both. The student
     picks the sections: list them all, and point out times that clash. A course in not_offered has no section that
     term: move it and re-run check_plan. For courses in unknown, and for later terms (their schedules aren't out
     yet), say to check Class Search. Say the seats are as of scraped_at and change
   - a checklist: confirm each course is offered that term in Class Search (GatorPath's history covers only some
     subjects, and past terms don't promise future ones), compare with the DPR, see the advisor
   Then offer what-ifs: graduating earlier (step 6; "a year early" means a year before the plan's
   est_graduation_term: say the term you used, and give why_not when it can't be reached), a new direction
   (steps 4-5 with the new goal; required courses don't change). Switching majors isn't supported yet.
8. Offer once to save their profile so the next session starts here: `save_profile` with the goal, chosen_electives
   and the plan that passed check_plan. Only if they say yes; it writes one file on their machine (default
   ~/.gatorpath/profile.yaml, or a path they choose)."""


@mcp.prompt(title="Plan my degree")
def plan_my_degree(goal: str = "", graduate_by: str = "") -> str:
    """Step-by-step workflow: profile → audit → plan → electives by goal → check_plan → pace/what-ifs → advisor."""
    return PLAN_MY_DEGREE.format(year=YEAR, years=", ".join(YEARS), goal=f"\n\nThe student's goal: {goal}." if goal else "",
                                 deadline=f" They'd like to graduate by {graduate_by} (pass it as graduate_by)."
                                 if graduate_by else "")
