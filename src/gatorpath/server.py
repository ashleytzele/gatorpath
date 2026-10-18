"""MCP tools (ARCHITECTURE §7). Thin: check input, read catalog.db and rules/, call engine/, add catalog_year + warnings."""

import difflib
import json
import os
import re
from datetime import date
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
from gatorpath.engine.rules import RULES_DIR, audit, load_rules, number, translate_ge

YEAR = "2026-27"  # ponytail: one catalog year. Take it from the profile/tool input once a second year is ingested.
REPO = Path(__file__).parents[2]
DB = REPO / "data/catalog.db"
PROFILE_PATH = "~/.gatorpath/profile.yaml"
LEVELS = {"lower": (100, 300), "upper": (300, 700), "graduate": (700, 1000)}
NO_OFFERINGS = "Offering history isn't loaded yet (TASKS phase 5), so `offered` is 'unknown'; check Class Search"
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITES_FILE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    "gatorpath",
    instructions=(
        f"SF State degree-planning tools for the {YEAR} Bulletin. Answers come only from the Bulletin and reviewed rules: "
        "don't add courses, prereqs or requirements the tools didn't return. Cite the `source`/`source_page` Bulletin "
        "pages, show every warning, and remind the student that the DPR and an advisor are the final word. "
        "Never guess what transfer credit covers or when a student will graduate: ask for the DPR, and use the planner "
        "tools when they exist. "
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
    first_time: NotRequired[bool]
    ge_certified: NotRequired[bool]
    prior_bachelors: NotRequired[bool]
    transfer_units: NotRequired[float]
    adt: NotRequired[bool]
    f1: NotRequired[bool]
    max_units_per_term: NotRequired[float]
    include_summer: NotRequired[bool]
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


def year_warning(profile: dict) -> list[str]:
    given = profile.get("catalog_year")
    if given is None:
        return [f"catalog_year not given, so this uses the {YEAR} Bulletin. Students are held to the year on their DPR "
                "('Requirement (Catalog) Term'); if it's earlier, requirements (GE areas especially) may differ"]
    if str(given).strip() == YEAR:
        return []
    return [f"The student's catalog year is {given}, but GatorPath only has {YEAR} rules, so this uses them. "
            "Requirements may differ (older catalogs use GE Areas A-E). Where the DPR disagrees, the DPR wins. In "
            "continuous attendance a student may elect the graduation requirements in effect when they began their "
            "study, when they entered SF State, or when they graduate (p.2390); ask an advisor before relying on that"]


def prepare(profile: dict, university: dict) -> tuple[dict, list[str]]:
    """Normalize what a client sends (codes, DPR GE area names) and say what was assumed or translated."""
    ge_done, ge_warnings = translate_ge(profile.get("ge_done", []), university)
    # not_on_dpr: group ids, or GE areas in the DPR's or this Bulletin's codes ("6", "F", "Area 6")
    groups = {g["id"]: g for g in university["groups"]}
    by_area = {str(a): gid for gid, g in groups.items() if isinstance(g.get("from"), dict)
               for a in ([g["from"]["ge_area"]] if not isinstance(g["from"].get("ge_area"), list) else g["from"]["ge_area"])}
    left_out = []
    for x in profile.get("not_on_dpr", []):
        if str(x) in groups or str(x) in {g["id"] for g in load_rules(YEAR, profile["program"])[0]["groups"]}:
            left_out.append(str(x))
        else:
            areas, w = translate_ge([x], university)
            left_out += [by_area[a] for a in areas if a in by_area]
            ge_warnings += [m for m in w if "not recognized" in m]
    clean = profile | {"catalog_year": YEAR, "ge_done": ge_done, "not_on_dpr": list(dict.fromkeys(left_out)),
                       "completed": [r | {"code": norm_code(r["code"])} for r in profile.get("completed", [])],
                       "in_progress": [norm_code(c) for c in profile.get("in_progress", [])],
                       "dpr_met": [norm_code(c) for c in profile.get("dpr_met", [])]}
    return clean, year_warning(profile) + ge_warnings


def normalized_plan(plan: dict | None) -> dict | None:
    return plan and {"semesters": [s | {"courses": [norm_code(c) if isinstance(c, str) else c for c in s.get("courses", [])]}
                                   for s in plan.get("semesters", [])]}


def profile_error(profile: dict) -> dict | None:
    if profile["program"] not in programs():
        return unknown_program(profile["program"])
    return None


@mcp.tool(annotations=READ_ONLY)
def audit_progress(profile: Profile) -> dict:
    """Degree audit: per requirement group satisfied / in_progress / remaining / waived and which courses counted,
    plus university totals (120 units, upper-division, residence, CR cap, GPAs). Nothing is stored.

    profile: program (e.g. 'bs-cs'); catalog_year (the DPR's "Requirement (Catalog) Term"; another year than
    2026-27 is planned with 2026-27 rules and a warning); completed: [{code, grade, term?, units? (variable-unit
    courses), transfer? (articulated transfer course), credit? ('extension' | 'exam' | 'evaluation': counts for
    units, never residence)}], grades as SF State symbols (A..F, CR, NC, W, I);
    in_progress: [codes]; ge_done: GE areas met by transfer/AP/IB credit, as the DPR writes them (e.g. "1A", or an
    older catalog's "A2", "D", "UD-D": translated automatically), also USH/USG/CSLG; dpr_met: required courses the
    DPR shows met by a substitution or exception (e.g. MATH 225 met by MATH 325); not_on_dpr: requirements the
    tools list but the student's DPR doesn't have at all (an older catalog, e.g. GE "6" Ethnic Studies): left out and
    flagged for an advisor to confirm; first_time (began at SF State as a first-time college student; default: no
    transfer work); ge_certified (Cal-GETC certification of lower-division GE, p.2304); prior_bachelors (already holds
    a bachelor's or higher degree from a regionally accredited institution: GE and graduation requirements waived,
    p.2313); transfer_units: total transfer units; adt: true only for a verified AA-T/AS-T from a California Community
    College in a similar approved major (waives SF State Studies, p.2313); gpa optional.
    """
    if err := profile_error(profile):
        return err
    program, university = load_rules(YEAR, profile["program"])
    clean, notes = prepare(profile, university)
    out = audit(clean, program, university, catalog(DB, YEAR))
    out["warnings"] = notes + out["warnings"] + unverified(university, "University (GE and graduation)")
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
    profile.f1: true for an F-1 visa student: a spring/fall term under 12 units is an error (the plan's last term: a
    warning and the international office), and so is a skipped spring/fall term (pp.2390, 2393).

    plan: {semesters: [{term: '2027-fall', courses: ['CSC 413', {slot: 'senior_electives', units: 3}]}]}. A slot is an
    unfilled pick for a requirement group (group ids from get_program_requirements), or {slot: 'elective', units: 3,
    upper_division?: true} for free units. Terms are YYYY-spring/summer/fall, after the profile's completed terms.
    """
    if err := profile_error(profile):
        return err
    program, university = load_rules(YEAR, profile["program"])
    clean, notes = prepare(profile, university)
    out = engine_check_plan(clean, normalized_plan(plan), program, university, catalog(DB, YEAR), prereqs(DB, YEAR))
    out["warnings"] = notes + out["warnings"] + [NO_OFFERINGS] + unverified(university, "University (GE and graduation)")
    return out


@mcp.tool(annotations=READ_ONLY)
def build_plan(profile: Profile) -> dict:
    """Deterministic baseline plan to graduation: required courses ordered by the prereq chain (critical path first,
    corequisites together), then slots for what's open (GE areas, senior electives, free electives) to reach the 120
    and upper-division totals. Already run through check_plan: see `check`.

    Fill each slot with list_eligible_electives + the student's goal, then call check_plan again before presenting.
    Uses max_units_per_term (default 15, the normal load, p.2393), include_summer and f1 (F-1 visa: spring/fall
    terms filled toward 12 units, pp.2390, 2393). Returns needs_input
    (qr_pathway, start_term) instead of guessing. Each semester has `why`: per course, what it's needed before, the
    chain it starts, and whether delaying it pushes back graduation. `pace` says what sets the length: the longest
    prereq chain vs the units per term; with profile.graduate_by it says whether that term is reachable and, if
    not, why_not. For "3, 4 or 5 years", call it at different max_units_per_term / include_summer.
    """
    if err := profile_error(profile):
        return err
    program, university = load_rules(YEAR, profile["program"])
    path = RULES_DIR / "roadmaps" / YEAR / f"{profile['program']}.yaml"
    clean, notes = prepare(profile, university)
    out = engine_build_plan(clean, program, university, yaml.safe_load(path.read_text()), catalog(DB, YEAR), prereqs(DB, YEAR))
    out["warnings"] = notes + out["warnings"] + [NO_OFFERINGS] + unverified(university, "University (GE and graduation)")
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
    clean, notes = prepare(profile, university)
    out = eligible_options(clean, group_id, program, university, catalog(DB, YEAR), prereqs(DB, YEAR),
                           normalized_plan(plan), by_term, max(1, min(limit, 100)))
    if "options" in out:
        desc = db.descriptions(DB, YEAR, [o["code"] for o in out["options"]])
        out["options"] = [o | {"description": desc.get(o["code"])} for o in out["options"]]
    out["catalog_year"] = YEAR
    out["warnings"] = notes + out.get("warnings", []) + [NO_OFFERINGS]
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
        term, start = term_start(date.today())
        try:
            stale = date.fromisoformat(imported) < start
        except (TypeError, ValueError):
            stale, warnings = False, [f"dpr_imported {imported!r} isn't a date (YYYY-MM-DD)"]
        if stale:
            warnings.append(f"The DPR was imported {imported}, before the current term ({term}): ask for a fresh DPR "
                            "(Student Center → Degree Progress Report) so new grades and courses are included")
    return {"catalog_year": YEAR, "profile": profile, "path": str(file), "warnings": warnings}


PLAN_MY_DEGREE = """You're helping an SF State student plan their degree with GatorPath ({year} Bulletin). Every course, prereq,
requirement and date comes from the tools: never add one they didn't return, and never present a plan check_plan
hasn't passed.{goal}{deadline}

Keep it fast. Ask once, in one message, for everything still missing, then work through to a finished plan without
stopping for confirmation. Never ask one question at a time or re-ask what they gave. Fill optional gaps with stated
defaults (15 units per term, no summer) instead of asking.

1. Start with `load_profile` (no path: the default file). If it returns a profile, start from it and ask only what's
   missing or changed; if it warns the DPR is stale, ask for a fresh one. Otherwise ask for their record. The
   fastest is their DPR (Student Center → Degree Progress Report, printed or saved as a
   PDF, or its text pasted). In that same request, before they share anything, say once that an attached PDF includes
   their name and student ID, which go to the AI provider, so they may black those out or paste only the requirement
   sections. Never repeat it after they share. Then accept whatever they share; a
   typed course list works too. In the same message, ask only for what a DPR can't show and isn't given above: the
   goal, a graduation target, whether they're on an F-1 student visa (it sets a 12-unit minimum every spring and
   fall), and the math placement (QR "1/2" or "3/4") if lower-division math isn't done.
2. Build the profile:
   - catalog_year: the DPR's "Requirement (Catalog) Term", e.g. "Spring 2025". If it isn't {year}, keep going:
     the tools plan with {year} rules and warn. Where the DPR and the tools disagree, the DPR wins: say so.
   - completed: each course with a grade (code, grade, term). A course with a term and no grade is in_progress.
   - transfer: "MATH 100TR" listed under the "MATH 226" requirement means MATH 226 met by transfer:
     {{code: "MATH 226", grade, transfer: true}}. Use the other school's grade; with only the DPR's "T", use the
     requirement's minimum (C for the major) and say you assumed it. Never guess what transfer credit covers
     beyond what the DPR shows.
   - ge_done: GE areas the DPR shows complete, in the DPR's own codes ("A2", "D", "UD-D", or "1A"); the tools
     translate older codes. Plus USH / USG / CSLG when American Institutions are met.
   - dpr_met: required courses the DPR shows met by a different course (MATH 325 listed under "MATH 225").
   - not_on_dpr: requirements audit_progress lists that the DPR doesn't have at all (older catalogs, e.g. GE "6"
     Ethnic Studies). Compare after step 3's audit and re-run with them; tell the student to confirm.
   - gpa from the DPR; transfer_units; adt: true only for a verified AA-T/AS-T from a California Community College
     in a similar approved major; ge_certified: true for Cal-GETC certification of lower-division GE; first_time:
     false for transfer students; prior_bachelors: true if they already hold a bachelor's or higher degree from a
     regionally accredited institution; f1: true for an F-1 visa student.
   - exam credit (AP / CLEP): put US History and US Government in ge_done as USH / USG only when the DPR shows them;
     no AP or CLEP exam meets California government (CSLG), p.2350.
3. `audit_progress`, then `build_plan` (with graduate_by if given). If build_plan returns needs_input, ask for
   just that.
4. Fill every slot: `list_eligible_electives` with group_id = the slot, plan = the current plan, by_term = the slot's
   term. Pick by the goal: 'ready' first, 'check' only after saying what can't be checked. Prefer options whose
   also_covers clears other open requirements (one course can cover upper-division GE and SF State Studies).
   Senior electives: at least 12 of the 15 units in CSC. A 0-unit tag slot is met by a chosen course whose
   also_covers includes it (then drop the tag); otherwise fill it from its own group and add the units. Free
   `elective` slots: suggest courses that fit the goal.
5. `check_plan` the filled plan; fix every error and re-check until valid.
6. A graduation target or "3, 4 or 5 years?": `build_plan` at 12, 15 and 18 units per term + include_summer, then a
   table: load, est_graduation_term, on_time, why_not. Over 15 units is above the normal load (p.2393): advisor.
7. Present, briefly:
   - done / left, with Bulletin pages, and every point where the DPR and the tools disagree
   - one table per term, in the order to enter it in Student Center → Degree Planner: course, units, what it counts
     for, why
   - warnings, and every `see_advisor` item: who, why, link, how to book. For F-1 students, GatorPath knows only the
     Bulletin's 12-unit minimum and continuous enrollment: send every other visa question (I-20 dates, OPT, a
     lighter final term) to the international office without stating visa rules yourself
   - a checklist: confirm each course is offered that term in Class Search (no schedule data yet), compare with the
     DPR, see the advisor
   Then offer what-ifs: graduating earlier (step 6), a new direction (steps 4-5 with the new goal; required courses
   don't change). Switching majors isn't supported yet.
8. Offer once to save their profile so the next session starts here: `save_profile` with the goal, chosen_electives
   and the plan that passed check_plan. Only if they say yes; it writes one file on their machine (default
   ~/.gatorpath/profile.yaml, or a path they choose)."""


@mcp.prompt(title="Plan my degree")
def plan_my_degree(goal: str = "", graduate_by: str = "") -> str:
    """Step-by-step workflow: profile → audit → plan → electives by goal → check_plan → pace/what-ifs → advisor."""
    # ponytail: no import_dpr step yet. Add it to the workflow when the tool lands (TASKS phase 6).
    return PLAN_MY_DEGREE.format(year=YEAR, goal=f"\n\nThe student's goal: {goal}." if goal else "",
                                 deadline=f" They'd like to graduate by {graduate_by} (pass it as graduate_by)."
                                 if graduate_by else "")
