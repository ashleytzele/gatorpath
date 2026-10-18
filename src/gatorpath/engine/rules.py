"""Requirement YAML + student profile -> degree audit (ARCHITECTURE §6.2, §7.3). Pure functions, no DB.

Counting rules:
- Within the major a course counts toward one group only; groups are filled in YAML order.
- University groups (GE, SF State Studies, American Institutions, GWAR) may share a course with each other
  and with the major: "an unlimited number of courses used to meet General Education requirements may be
  used to fulfill major requirements" (p.2352). Units still count once toward the 120.
- Repeats: the best attempt counts and its units count once, unless the course is repeatable for credit.
- Grades: CR is "equivalent to grades A through C-" (p.2403), so it meets a C- minimum but not a C.
- `transfer: true` rows count toward requirements, not residence or GPA. Their units are inside
  `profile.transfer_units`.
"""

import math
import re
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).parents[3] / "rules"
GRADE_POINTS = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7, "C+": 2.3, "C": 2.0, "C-": 1.7,
                "D+": 1.3, "D": 1.0, "D-": 0.7, "F": 0.0, "IC": 0.0, "WU": 0.0}  # p.2405
PASSING = GRADE_POINTS["D-"]
GRADE_SYMBOLS = set(GRADE_POINTS) | {"CR", "NC", "W", "I", "AU", "RD", "RP"}  # p.2403


def load_rules(catalog_year: str, program: str) -> tuple[dict, dict]:
    """(program rules, university rules) from rules/**/*.yaml."""
    read = lambda p: yaml.safe_load((RULES_DIR / p).read_text())
    return read(f"programs/{catalog_year}/{program}.yaml"), read(f"university/{catalog_year}.yaml")


def translate_ge(areas: list, university: dict) -> tuple[list[str], list[str]]:
    """GE areas as a DPR writes them ("A2", "Area D - Social Sciences", "GE D/USH", "UD-D", "1A") -> this catalog's
    areas, plus warnings for what was translated, has no equivalent, or isn't a known area."""
    legacy = university.get("legacy_ge_areas", {})
    table, none = {str(k).upper(): str(v) for k, v in legacy.get("map", {}).items()}, set(legacy.get("none", []))
    known = {str(a).upper() for g in university["groups"] if "from" in g
             for f in (g["from"] if isinstance(g["from"], list) else [g["from"]]) if "ge_area" in f
             for a in (f["ge_area"] if isinstance(f["ge_area"], list) else [f["ge_area"]])}
    out, mapped, dropped, unknown = [], [], [], []
    for a in areas:
        text = re.sub(r"^(GE\s+)?(AREA\s+)?", "", str(a).strip().upper())
        text = re.split(r"\s+[-–:]\s+|:\s*", text)[0]  # "D - SOCIAL SCIENCES" -> "D"; keeps "UD-D"
        for key in [text] if text in table else text.split("/"):  # "D/USH" -> D, USH; but "C3 OR C2" stays whole
            key = key.strip()
            if key in table:
                out.append(table[key])
                mapped.append(f"{key} → {table[key]}")
            elif key in none:
                dropped.append(key)
            elif key in known:
                out.append(key)
            else:
                unknown.append(str(a))
    warnings = []
    if mapped:
        warnings.append(f"GE areas from an older catalog were read as this Bulletin's areas: {', '.join(mapped)} "
                        f"({legacy['source']})")
    if dropped:
        warnings.append(f"GE {', '.join(dropped)}: no {university['catalog_year']} equivalent, so nothing is planned "
                        "for it; your DPR shows its status")
    if unknown:
        warnings.append(f"ge_done entries not recognized as GE areas, ignored: {', '.join(unknown)}")
    return list(dict.fromkeys(out)), warnings


def rank(grade: str | None) -> float | None:
    """Comparable grade value if the grade earns credit, else None (F, NC, W, I, AU, RP, …)."""
    if grade == "CR":
        return GRADE_POINTS["C-"]
    return GRADE_POINTS.get(grade) or None


def subject(code: str) -> str:
    return code.rsplit(" ", 1)[0]


def number(code: str) -> int:
    return int(re.search(r"\d{3}", code.rsplit(" ", 1)[1]).group())


def first_time(profile: dict) -> bool:
    """Began at SF State as a first-time college student: profile.first_time, else no transfer work at all."""
    if "first_time" in profile:
        return bool(profile["first_time"])
    return not (profile.get("transfer_units") or profile.get("adt") or any(r.get("transfer") for r in profile.get("completed", [])))


def matches(f: dict, code: str, course: dict) -> bool:
    """One `from` filter: {list} | {ge_area} (any of) | {ge_area_all} | {subject, level, paired}, each with `except`."""
    if code in f.get("except", ()):
        return False
    if "list" in f:
        return code in f["list"]
    if "ge_area_all" in f or "ge_area" in f:
        if "ge_area_all" in f:
            hit = {str(a) for a in f["ge_area_all"]} <= set(course["ge_areas"])
        else:
            areas = f["ge_area"] if isinstance(f["ge_area"], list) else [f["ge_area"]]
            hit = bool({str(a) for a in areas} & set(course["ge_areas"]))
        level, n = f.get("level"), number(code)
        return hit and (level != "lower" or n < 300) and (level != "upper" or 300 <= n <= 699)
    level, n = str(f.get("level", "")), number(code)
    return (subject(code) == f["subject"]
            and not (level.endswith("+") and n < int(level[:-1]))
            and not (level.isdigit() and not int(level) <= n < int(level) + 100)
            and not (f.get("paired") is False and course["paired"]))


def best_attempts(profile: dict, catalog: dict, warnings: list[str], repeats: dict) -> dict[str, dict]:
    """{code: {grade, units, transfer}}: best attempt per course; repeatable courses add up their passing units."""
    by_code: dict[str, list[dict]] = {}
    for row in profile.get("completed", []):
        if row["code"] not in catalog:
            warnings.append(f"{row['code']}: unknown_course, not in the {profile.get('catalog_year', '')} catalog; ignored")
            continue
        by_code.setdefault(row["code"], []).append(row)
    taken = {}
    for code, rows in by_code.items():
        course = catalog[code]
        units = []
        for r in rows:
            if r["grade"] not in GRADE_SYMBOLS:
                warnings.append(f"{code}: grade {r['grade']!r} is not an SF State grade symbol (p.2403); counted as no credit. "
                                "For a pass/credit grade from another school, enter CR")
            if "units" not in r and course["units_min"] != course["units_max"]:
                warnings.append(f"{code}: variable units ({course['units_min']:g}-{course['units_max']:g}); "
                                f"counted {course['units_min']:g}, pass `units` to be exact")
            units.append(r.get("units", course["units_min"]))
        earned = [(rank(r["grade"]) or 0, u) for r, u in zip(rows, units)]
        best = max(range(len(rows)), key=lambda i: earned[i][0])
        repeatable = course["repeatable"]
        transfer_credit = [u for r, (e, u) in zip(rows, earned) if r.get("transfer") and e]
        taken[code] = {
            "grade": rows[best]["grade"],
            "units": sum(u for e, u in earned if e) if repeatable else (units[best] if earned[best][0] else 0),
            "transfer": bool(rows[best].get("transfer")),
            "credit": rows[best].get("credit"),  # extension / exam / evaluation: units, but no residence (p.2391)
            # Passed at a transfer school, then repeated at SF State: those units are already in transfer_units.
            "transfer_dup_units": max(transfer_credit) if transfer_credit and not rows[best].get("transfer") and not repeatable else 0,
        }
        retaking = code in profile.get("in_progress", [])
        attempts = len(rows) + retaking
        if attempts > 1 and not repeatable:
            src = repeats["source"]
            msg = f"{code}: attempt {attempts}; the best grade counts and its units count once ({src})"
            if attempts > repeats["attempts_without_consent"]:
                msg += (f". {repeats['attempts_without_consent'] + 1} or more attempts need the consent of the instructor "
                        "and department chair")
            if any(blocks_repeat(r["grade"], repeats) for r in (rows if retaking else rows[:-1])):
                msg += f". A course passed with {repeats['no_repeat_at_or_above']} or better or CR may not be repeated unless it is repeatable for credit"
            if any(r["grade"] in repeats["no_repeat_while"] for r in (rows if retaking else rows[:-1])):
                msg += ". A course with an I (Incomplete) can't be repeated until the I is converted to a grade"
            warnings.append(msg)
    repeated = sum(r.get("units", catalog[c]["units_min"]) for c in by_code if not catalog[c]["repeatable"]
                   for r in by_code[c][1:] if not r.get("transfer"))
    if repeated > repeats["max_repeated_units"]:
        warnings.append(f"{repeated:g} SF State units of repeats: no course can be repeated after "
                        f"{repeats['max_repeated_units']} repeated units unless it is repeatable for credit ({repeats['source']})")
    return taken


def blocks_repeat(grade: str | None, repeats: dict) -> bool:
    """A grade at or above the bar (or CR) means the course may not be repeated (p.2392)."""
    return (grade == "CR" and repeats["cr_blocks_repeat"]) or (rank(grade) or 0) >= GRADE_POINTS[repeats["no_repeat_at_or_above"]]


def eval_group(g: dict, kind: str, taken: dict, profile: dict, catalog: dict, claimed: set | None,
               no_cr_nc: bool, done_groups: dict, warnings: list[str], certified: frozenset = frozenset()) -> dict:
    out = {"id": g["id"], "title": g.get("title", g["id"]), "kind": kind, "source": g["source"],
           "counted": [], "in_progress": []}
    if g.get("waived_if") and profile.get(g["waived_if"]):
        return out | {"status": "waived"} | ({"waived_by": g["waiver"]} if "waiver" in g else {})
    if kind == "university" and profile.get("prior_bachelors"):  # p.2313: no GE or other graduation requirements
        return out | {"status": "waived", "waived_by": "prior bachelor's degree"}
    if g["id"] in profile.get("not_on_dpr", ()):
        # DPR-first: an older catalog the student is held to may not have this requirement at all (GE 6 for a
        # Spring 2025 transfer GE pattern). Left out, flagged, never silently.
        warnings.append(f"{out['title']}: left out because the student's DPR doesn't list it (their catalog year); "
                        f"confirm with an advisor that it isn't required ({g['source']})")
        return out | {"status": "waived", "waived_by": "not on the student's DPR"}
    if "distinct_subjects" in g:
        return out | distinct_subjects(g, done_groups, warnings)
    if g["id"] in certified:  # Cal-GETC certification of lower-division GE (p.2304)
        return out | {"status": "satisfied", "met_by": "ge_certification"}

    in_progress = [c for c in profile.get("in_progress", []) if c in catalog]
    free = lambda c: claimed is None or c not in claimed
    bar = GRADE_POINTS[g["min_grade"]] if "min_grade" in g else PASSING

    def ok(c: str) -> bool:
        t = taken.get(c)
        return bool(t) and free(c) and not (no_cr_nc and t["grade"] == "CR") and (rank(t["grade"]) or -1) >= bar

    def note_grade(c: str) -> None:
        if c in taken and free(c) and not ok(c) and c not in in_progress:
            why = "CR/NC is not accepted in the major" if no_cr_nc and taken[c]["grade"] == "CR" else \
                f"needs {g.get('min_grade', 'a passing grade')}" + (" or better" if "min_grade" in g else "")
            warnings.append(f"{c}: grade {taken[c]['grade']} doesn't count toward {out['title']}; {why} ({g['source']})")

    if "all_of" in g:
        # dpr_met: required courses the student's DPR shows met another way (a substitution such as MATH 325 for
        # MATH 225, or an exception). One student's record, never a rule; prereqs still need the real course.
        met = [c for c in g["all_of"] if c in profile.get("dpr_met", ()) and not ok(c)]
        for c in met:
            warnings.append(f"{c}: counted for {out['title']} because the DPR shows it met (substitution or "
                            f"exception); GatorPath can't verify that ({g['source']})")
        done = [c for c in g["all_of"] if ok(c) or c in met]
        prog = [c for c in g["all_of"] if c not in done and c in in_progress and free(c)]
        left = [c for c in g["all_of"] if c not in done and c not in prog]
        for c in left:
            note_grade(c)
        if claimed is not None:
            claimed.update(done + prog)
        status = "remaining" if left else "in_progress" if prog else "satisfied"
        return out | {"status": status, "counted": done, "in_progress": prog, "remaining": left} | (
            {"met_per_dpr": met} if met else {})

    source = g["first_time_from"] if "first_time_from" in g and first_time(profile) else g["from"]
    filters = source if isinstance(source, list) else [source]
    ge_areas = {str(a) for f in (g["from"] if isinstance(g["from"], list) else [g["from"]]) + filters
                for key in ("ge_area", "ge_area_all") if key in f
                for a in (f[key] if isinstance(f[key], list) else [f[key]])}
    if ge_areas & set(profile.get("ge_done", [])):
        return out | {"status": "satisfied", "met_by": "ge_done"}

    need_units, need_n = g.get("choose_units"), g.get("choose_n")
    min_from = g.get("min_units_from")
    pref = min_from["subject"] if min_from else None
    units = lambda c: taken[c]["units"] if c in taken and ok(c) else catalog[c]["units_min"]
    units_met = lambda cs: sum(map(units, cs)) >= need_units if need_units else len(cs) >= need_n
    pref_units = lambda cs: sum(units(c) for c in cs if subject(c) == pref)
    enough = lambda cs: units_met(cs) and (not min_from or pref_units(cs) >= min_from["units"])
    used = [0] * len(filters)

    def pick(codes: list[str], chosen: list[str]) -> list[str]:
        # ponytail: greedy (preferred subject first, then code order), not an optimal matching.
        # Upgrade to bipartite matching if a profile shows a better assignment exists.
        chosen = list(chosen)
        for c in sorted(codes, key=lambda c: (subject(c) != pref, c)):
            if enough(chosen):
                break
            if units_met(chosen) and subject(c) != pref:
                continue
            fi = next((i for i, f in enumerate(filters)
                       if matches(f, c, catalog[c]) and used[i] < f.get("max_courses", math.inf)), None)
            if fi is not None:
                used[fi] += 1
                chosen.append(c)
        return chosen

    for c in taken:
        if any(matches(f, c, catalog[c]) for f in filters):
            note_grade(c)
    done = pick([c for c in taken if ok(c)], [])
    both = pick([c for c in in_progress if free(c) and c not in done and not ok(c)], done)
    if claimed is not None:
        claimed.update(both)
    status = "satisfied" if enough(done) else "in_progress" if enough(both) else "remaining"
    if "course_units" in g:
        for c in both:
            if units(c) < g["course_units"]:
                warnings.append(f"{c}: {units(c):g} units counted toward {out['title']}, which asks for "
                                f"{g['course_units']:g}-unit courses; confirm with a senior advisor ({g['source']})")
    if "first_time_from" in g and first_time(profile) and status != "satisfied":
        later = [c for c in taken if ok(c) and any(matches(f, c, catalog[c]) for f in (g["from"] if isinstance(g["from"], list) else [g["from"]]))]
        if later:
            warnings.append(f"{', '.join(later)}: carries the area but doesn't meet {out['title']} for a student who began "
                            f"at SF State as a first-time college student ({g['source']})")
    eligible = [c for c in taken if ok(c) and any(matches(f, c, catalog[c]) for f in filters)]
    out |= {"status": status, "counted": done, "in_progress": both[len(done):], "eligible": eligible,
            "units_done": sum(map(units, done))}
    out |= {"units_needed": need_units} if need_units else {"courses_needed": need_n}
    if min_from:
        out["min_units_from"] = min_from | {"done": pref_units(done)}
    return out


def distinct_subjects(g: dict, done_groups: dict, warnings: list[str]) -> dict:
    parts = [done_groups[i] for i in g["across"]]
    if any(p.get("met_by") in ("ge_done", "ge_certification") for p in parts):
        warnings.append(f"{g['title']}: can't check with transfer/exam credit; confirm on your DPR ({g['source']})")
        return {"status": "satisfied"}
    # ponytail: counts subjects over every course that qualifies for these groups, not over one consistent pick.
    # Upgrade to a joint pick if a profile shows enough subjects but no valid 3-course combination.
    counted = {subject(c) for p in parts for c in p.get("eligible", p["counted"])}
    both = counted | {subject(c) for p in parts for c in p["in_progress"]}
    n = g["distinct_subjects"]
    return {"status": "satisfied" if len(counted) >= n else "in_progress" if len(both) >= n else "remaining",
            "subjects": sorted(both)}


def forgiven(rows: list[dict], repeats: dict, catalog: dict) -> set[int]:
    """ids of repeated attempts whose lower grade leaves the GPA, up to the forgiveness units (p.2392). Repeats before
    `forgiveness_from_term` (fall 2017) aren't forgiven this way (Academic Renewal, pp.2398-2399)."""
    limit, since = repeats["forgiveness_units"], repeats.get("forgiveness_from_term")
    key = lambda t: (int(t[:4]), ("spring", "summer", "fall").index(t[5:])) if re.fullmatch(r"\d{4}-(spring|summer|fall)", str(t)) else None
    # ponytail: applied in profile order, not by term; fine until a profile repeats past 16 units.
    best: dict[str, dict] = {}
    for r in rows:
        if r["grade"] in GRADE_POINTS and (r["code"] not in best or GRADE_POINTS[r["grade"]] > GRADE_POINTS[best[r["code"]]["grade"]]):
            best[r["code"]] = r
    out, used = set(), 0.0
    later = {r["code"]: [x for x in rows if x["code"] == r["code"] and x is not r] for r in rows}
    for r in rows:
        u = r.get("units", catalog[r["code"]]["units_min"])
        repeat_terms = [key(x.get("term")) for x in later[r["code"]] if key(x.get("term"))]
        if since and repeat_terms and max(repeat_terms) < key(since):
            continue  # the repeat came before fall 2017
        if (r["grade"] in GRADE_POINTS and r is not best[r["code"]] and not catalog[r["code"]]["repeatable"]
                and used + u <= limit):
            used += u
            out.add(id(r))
    return out


def gpa(rows: list[dict], skip: set[int], catalog: dict) -> float | None:
    """A–F grades only (p.2405), leaving out forgiven attempts."""
    points = units = 0.0
    for r in rows:
        if r["grade"] in GRADE_POINTS and id(r) not in skip:
            u = r.get("units", catalog[r["code"]]["units_min"])
            points, units = points + GRADE_POINTS[r["grade"]] * u, units + u
    return round(points / units, 3) if units else None


def totals(profile: dict, taken: dict, groups: list[dict], university: dict, catalog: dict, warnings: list[str]) -> dict:
    t = university["totals"]
    caps = t.get("max_units_from", {})
    no_res = set(t["residence"].get("no_residence_credit", ()))
    sfsu = {c: r for c, r in taken.items() if not r["transfer"]}
    resident = {c: r for c, r in sfsu.items() if r.get("credit") not in no_res}
    major_groups = [g for g in groups if g["kind"] == "major"]
    major = {c for g in major_groups for c in g["counted"]}
    # Major GPA covers required courses (passed or not), counted electives and courses being retaken.
    # ponytail: a failed elective that was never retaken is left out; add it if the DPR is shown to include it.
    major_gpa = major | {c for g in major_groups for c in g["in_progress"] + g.get("remaining", [])}
    lo, hi = t.get("upper_division_numbers", [300, 999])
    upper = lambda c: lo <= number(c) <= hi  # "courses numbered 300-699 at SF State" (p.2391)
    if (ccc := t.get("community_college_upper_division")) and not ccc["allowed"]:
        if ud_transfer := [c for c, r in taken.items() if r["transfer"] and upper(c)]:
            warnings.append(f"{', '.join(ud_transfer)}: transfer credit counted as upper division, but community college "
                            f"work never is ({ccc['source']}); check how the DPR applied it")
    sfsu_units = sum(r["units"] for r in sfsu.values())
    sfsu_ud_units = sum(r["units"] for c, r in resident.items() if upper(c))
    ud_ge_ids = set(university.get("upper_division_ge", {}).get("groups", []))
    sfsu_ud_ge = sum(resident[c]["units"] for g in groups if g["id"] in ud_ge_ids for c in g["counted"] if c in resident)
    # "Major courses only offered as CR/NC are not included in the 24 unit maximum" (p.2313)
    cr_units = sum(r["units"] for c, r in sfsu.items()
                   if r["grade"] == "CR" and not (c in major and catalog[c].get("grading") == "cr_nc"))
    rows = [r for r in profile.get("completed", []) if r["code"] in catalog and not r.get("transfer")]
    skip = forgiven(rows, university["repeats"], catalog)
    gpa_sfsu = gpa(rows, skip, catalog)
    gpa_major = gpa([r for r in rows if r["code"] in major_gpa], skip, catalog)
    gpa_all = profile.get("gpa")
    if gpa_all is None:
        gpa_all = gpa_sfsu
        if profile.get("transfer_units"):
            warnings.append("Overall GPA includes transfer work; using the SF State GPA. Pass `gpa` to be exact")
    min_gpa = t["min_gpa"]
    check = lambda v, need: {"value": v, "needed": need, "ok": v is not None and v >= need}
    transfer_units = profile.get("transfer_units", 0)
    if caps and transfer_units > caps["all_transfer"]:
        warnings.append(f"{transfer_units:g} transfer units: at most {caps['all_transfer']} can be transferred from all "
                        f"sources, so {caps['all_transfer']} count toward the 120 ({caps['source']})")
        transfer_units = caps["all_transfer"]
    elif caps and transfer_units > caps["community_college"]:
        warnings.append(f"{transfer_units:g} transfer units: no more than {caps['community_college']} from community "
                        f"colleges count toward the 120; units past that apply only {caps['over_cap']} ({caps['source']})")
    teaching = [c for c in sfsu if c.endswith(" 685") and catalog[c]["title"].lower().startswith("projects in teaching")]
    over_685 = max(0, sum(sfsu[c]["units"] for c in teaching) - caps.get("projects_in_teaching_685", float("inf")))
    if over_685:
        warnings.append(f"{', '.join(teaching)}: only {caps['projects_in_teaching_685']} units of \"Projects in Teaching\" "
                        f"685 courses apply to the degree ({caps['source']})")
    return {
        "units": check(sfsu_units - over_685 + transfer_units - sum(r["transfer_dup_units"] for r in taken.values()),
                       t["min_units"]),
        "units_in_progress": sum(catalog[c]["units_min"] for c in profile.get("in_progress", []) if c in catalog),
        "upper_division_units": check(sum(r["units"] for c, r in taken.items() if upper(c)), t["min_upper_division_units"]),
        "residence_units": check(sum(r["units"] for r in resident.values()), t["residence"]["units"]),
        "residence_upper_division_units": check(sfsu_ud_units, t["residence"]["upper_division"]),
        "residence_major_units": check(sum(resident[c]["units"] for c in major if c in resident), t["residence"]["major"]),
        **({"residence_upper_division_ge_units": check(sfsu_ud_ge, t["residence"]["upper_division_ge"])}
           if "upper_division_ge" in t["residence"] else {}),
        "cr_units": {"value": cr_units, "max": t["max_cr_units"], "ok": cr_units <= t["max_cr_units"]},
        "gpa_all": check(gpa_all, min_gpa["all"]),
        "gpa_sf_state": check(gpa_sfsu, min_gpa["sf_state"]),
        "gpa_major": check(gpa_major, min_gpa["major"]),
        "source": t["source"],
    }


def audit(profile: dict, program: dict, university: dict, catalog: dict) -> dict:
    """Per-group status (satisfied / in_progress / remaining / waived), university totals, warnings."""
    warnings: list[str] = []
    norm = lambda x: str(x).strip().upper()  # 'b ' -> 'B'; ge_done [2] -> '2'
    profile = profile | {"completed": [r | {"grade": norm(r["grade"])} for r in profile.get("completed", [])],
                         "ge_done": [norm(a) for a in profile.get("ge_done", [])]}
    taken = best_attempts(profile, catalog, warnings, university["repeats"])
    temporary = [r["code"] for r in profile["completed"] if r["grade"] in university.get("grading", {}).get("temporary", ())]
    if temporary:
        warnings.append(f"{', '.join(temporary)}: temporary grade (I, RD or RP); it must be changed to a final grade before "
                        f"the degree can be confirmed, and an I not completed in time becomes IC, counted as F "
                        f"({university['grading']['source']})")
    if profile.get("transfer_units") and not profile["ge_done"] and not any(r.get("transfer") for r in profile["completed"]):
        warnings.append(f"{profile['transfer_units']:g} transfer units count toward the 120 only: no transfer courses or ge_done "
                        "were given, so no requirement is credited for them. Don't assume which requirements they cover; "
                        "the DPR shows how each transfer course was applied")
    for c in profile.get("in_progress", []):
        if c not in catalog:
            warnings.append(f"{c}: unknown_course, not in the catalog; ignored")
    done: dict[str, dict] = {}
    claimed: set[str] = set()
    no_cr_nc = program.get("global", {}).get("no_cr_nc", False)
    certified = frozenset(university.get("transfer", {}).get("certified_ld_ge", [])) if profile.get("ge_certified") else frozenset()
    for kind, rules in (("major", program), ("university", university)):
        for g in rules["groups"]:
            done[g["id"]] = eval_group(g, kind, taken, profile, catalog, claimed if kind == "major" else None,
                                       no_cr_nc and kind == "major", done, warnings, certified)
    groups = list(done.values())
    tot = totals(profile, taken, groups, university, catalog, warnings)
    prior = bool(profile.get("prior_bachelors"))
    if prior:
        warnings.append("Prior bachelor's degree: GE and the other graduation requirements don't apply; only courses "
                        f"required for the major do ({university['prior_degree']['source']}). Confirm with the Registrar")
    if not program.get("verified"):
        warnings.append(f"{program['program']} rules are not verified yet; confirm with an advisor and your DPR")
    return {
        "catalog_year": program["catalog_year"],
        "program": program["program"],
        "verified": bool(program.get("verified")),
        "complete": all(g["status"] in ("satisfied", "waived") for g in groups)
                    and (prior or all(v["ok"] for v in tot.values() if isinstance(v, dict))),
        "groups": groups,
        "totals": tot,
        "warnings": warnings,
    }
