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
import unicodedata
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
    table = {str(k).upper(): [str(x) for x in v] if isinstance(v, list) else [str(v)] for k, v in legacy.get("map", {}).items()}
    none = set(legacy.get("none", []))
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
                out += table[key]
                mapped.append(f"{key} → {'+'.join(table[key])}")
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


def amended(g: dict) -> dict:
    """The group with its `amendments` applied: changes after the Bulletin was published, each citing its memo (§6.2)."""
    for a in g.get("amendments", []):
        g = g | a["change"]
    return g


def min_grade_of(g: dict, code: str) -> str | None:
    """A group's minimum grade for one course: `min_grade: C` covers every course, `{CSC 510: C}` only those named."""
    m = g.get("min_grade")
    return m.get(code) if isinstance(m, dict) else m


def filters_for(g: dict, profile: dict) -> list[dict]:
    """A group's `from` filters for this student: `first_time_from` for a first-time student (US History, p.2313)."""
    source = g["first_time_from"] if "first_time_from" in g and first_time(profile) else g["from"]
    # {approved: true}: no Bulletin list, only the courses the student's advisor approved for this group (§6.2)
    return [f | {"courses": profile.get("approved", {}).get(g["id"], [])} if "approved" in f else f
            for f in (source if isinstance(source, list) else [source])]


def in_level(level: object, n: int) -> bool:
    """A filter's `level`: lower (below 300) | upper (300-699, p.2391) | "300+" | "300" (300-399) | a list of those
    ("Any three units at the 500 or 600-level", p.988: [500, 600]) | none."""
    if isinstance(level, list):
        return any(in_level(x, n) for x in level)
    level = str(level or "")
    if level in ("lower", "upper"):
        return n < 300 if level == "lower" else 300 <= n <= 699
    return not (level.endswith("+") and n < int(level[:-1])) and not (level.isdigit() and not int(level) <= n < int(level) + 100)


def matches(f: dict, code: str, course: dict) -> bool:
    """One `from` filter: {list} | {ge_area} (any of) | {ge_area_all} | {subject, level, paired} (either may be left out:
    {level: upper} is any upper-division course), each with `except`; {approved} matches the courses filters_for gave it."""
    if code in f.get("except", ()):
        return False
    if "approved" in f:  # a level narrows them: "Up to 6 units may be in ... lower-division coursework" (p.1264)
        return code in f.get("courses", ()) and in_level(f.get("level"), number(code))
    if "list" in f:
        return code in f["list"]
    if "ge_area_all" in f or "ge_area" in f:
        if "ge_area_all" in f:
            hit = {str(a) for a in f["ge_area_all"]} <= set(course["ge_areas"])
        else:
            areas = f["ge_area"] if isinstance(f["ge_area"], list) else [f["ge_area"]]
            hit = bool({str(a) for a in areas} & set(course["ge_areas"]))
        return hit and in_level(f.get("level"), number(code))
    return (f.get("subject", subject(code)) == subject(code) and in_level(f.get("level"), number(code))
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


def ge_areas(g: dict) -> list[str]:
    """The GE area labels a university group takes ("1A", "USH"), from its `from` filters."""
    return [str(a) for f in ([g["from"]] if isinstance(g.get("from"), dict) else g.get("from") or [])
            for a in ([f.get("ge_area")] if not isinstance(f.get("ge_area"), list) else f["ge_area"]) if a]


def ge_met_in_major(program: dict, done: set[str], doing: set[str] = frozenset()) -> dict[str, tuple[str, str]]:
    """{GE area: (status, source)} the major meets (`ge_met`, §6.2): satisfied once every course of one option is in
    `done`, in_progress while they're all in `done` or `doing`."""
    out = {}
    for m in program.get("ge_met", []):
        if any(set(o) <= done for o in m["one_of"]):
            out[str(m["area"])] = ("satisfied", m["source"])
        elif any(set(o) <= done | doing for o in m["one_of"]):
            out[str(m["area"])] = ("in_progress", m["source"])
    return out


def eval_group(g: dict, kind: str, taken: dict, profile: dict, catalog: dict, claimed: set | None,
               no_cr_nc: bool, done_groups: dict, warnings: list[str], certified: frozenset = frozenset()) -> dict:
    out = {"id": g["id"], "title": g.get("title", g["id"]), "kind": kind, "source": g["source"],
           "counted": [], "in_progress": []} | ({"exceptions": g["exceptions"]} if "exceptions" in g else {})
    if g.get("amendments"):
        out["amended_by"] = [a["source"] for a in g["amendments"]]
    if g.get("waived"):  # by an amendment
        return out | {"status": "waived", "waived_by": "; ".join(out["amended_by"])}
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
    if g.get("unparsed"):  # a drafted rule the vocabulary can't express (§6.2): flagged, never approximated
        warnings.append(f"{out['title']}: GatorPath can't check this requirement; the Bulletin says \"{g.get('quote', '')}\" "
                        f"({g['source']}). Check it on your DPR or with an advisor")
        return out | {"status": "unparsed", "quote": g.get("quote", "")}
    if "distinct_subjects" in g:
        return out | distinct_subjects(g, done_groups, warnings)
    if g["id"] in certified:  # Cal-GETC certification of lower-division GE (p.2304)
        return out | {"status": "satisfied", "met_by": "ge_certification"}

    in_progress = [c for c in profile.get("in_progress", []) if c in catalog]
    free = lambda c: claimed is None or c not in claimed
    bar = lambda c: GRADE_POINTS[min_grade_of(g, c)] if min_grade_of(g, c) else PASSING

    def ok(c: str) -> bool:
        t = taken.get(c)
        return bool(t) and free(c) and not (no_cr_nc and t["grade"] == "CR") and (rank(t["grade"]) or -1) >= bar(c)

    def note_grade(c: str) -> None:
        if c in taken and free(c) and not ok(c) and c not in in_progress:
            why = "CR/NC is not accepted in the major" if no_cr_nc and taken[c]["grade"] == "CR" else \
                f"needs {min_grade_of(g, c) or 'a passing grade'}" + (" or better" if min_grade_of(g, c) else "")
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

    if "one_of" in g:
        # "Select One" of course bundles: met when every course of one option counts. What's left is one option: the
        # most done or in progress, then one with no attempt that didn't count (a CR can't be retaken, p.2392), then one
        # an earlier major group isn't already planning (a course counts once: GEOG 604 in two NRM&C Select Ones,
        # pp.2065-2066), then the fewest units left, then the first printed (§6.2).
        planned = {c for x in done_groups.values() if x["kind"] == "major" for c in x.get("remaining", [])} \
            if claimed is not None else set()
        opts = []
        for opt in g["one_of"]:
            done = [c for c in opt if ok(c)]
            prog = [c for c in opt if c not in done and c in in_progress and free(c)]
            opts.append({"courses": opt, "done": done, "in_progress": prog, "left": [c for c in opt if c not in done + prog]})
        for c in {c for opt in g["one_of"] for c in opt}:
            note_grade(c)
        best = min(opts, key=lambda o: (bool(o["left"]), bool(o["in_progress"]), -len(o["done"] + o["in_progress"]),
                                        any(c in taken for c in o["left"]), any(c in planned for c in o["left"]),
                                        sum(catalog[c]["units_min"] for c in o["left"] if c in catalog)))
        if claimed is not None:
            claimed.update(best["done"] + best["in_progress"])
        status = "remaining" if best["left"] else "in_progress" if best["in_progress"] else "satisfied"
        return out | {"status": status, "counted": best["done"], "in_progress": best["in_progress"],
                      "remaining": best["left"]} | (
            {"options": [{"courses": o["courses"], "left": o["left"]} for o in opts]} if status != "satisfied" else {})

    filters = filters_for(g, profile)
    areas = lambda x: {str(a) for a in (x if isinstance(x, list) else [x])}
    ge_done = set(profile.get("ge_done", []))
    # An area in ge_done stands alone; ge_area_all needs one course carrying them all, so "4" isn't Area 4 with USH
    if any(areas(f["ge_area"]) & ge_done if "ge_area" in f else "ge_area_all" in f and areas(f["ge_area_all"]) <= ge_done
           for f in (g["from"] if isinstance(g["from"], list) else [g["from"]]) + filters):
        return out | {"status": "satisfied", "met_by": "ge_done"}

    need_units, need_n = g.get("choose_units"), g.get("choose_n")
    min_from = g.get("min_units_from")  # a filter + units: "at least 12 units in CSC", "at least six units upper-division"
    pref = lambda c: bool(min_from) and matches(min_from, c, catalog[c])
    units = lambda c: taken[c]["units"] if c in taken and ok(c) else catalog[c]["units_min"]
    units_met = lambda cs: sum(map(units, cs)) >= need_units if need_units is not None else len(cs) >= need_n
    pref_units = lambda cs: sum(units(c) for c in cs if pref(c))
    enough = lambda cs: units_met(cs) and (not min_from or pref_units(cs) >= min_from["units"])
    used, used_units = [0] * len(filters), [0.0] * len(filters)

    def pick(codes: list[str], chosen: list[str]) -> list[str]:
        # ponytail: greedy (preferred courses first, then code order), not an optimal matching; a course past a filter's
        # max_units doesn't count in part. Upgrade to bipartite matching if a profile shows a better assignment exists.
        chosen = list(chosen)
        for c in sorted(codes, key=lambda c: (not pref(c), c)):
            if enough(chosen):
                break
            if units_met(chosen) and not pref(c):
                continue
            fi = next((i for i, f in enumerate(filters)
                       if matches(f, c, catalog[c]) and used[i] < f.get("max_courses", math.inf)
                       and used_units[i] + units(c) <= f.get("max_units", math.inf)), None)
            if fi is not None:
                used[fi] += 1
                used_units[fi] += units(c)
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
    out |= {"units_needed": need_units} if need_units is not None else {"courses_needed": need_n}
    if min_from:
        out["min_units_from"] = min_from | {"done": pref_units(done)}
    return out


CHECKS = ("letter_grade", "max_cr", "max_below", "min_gpa", "min_units_from", "max_units_from", "distinct_subjects",
          "min_categories", "one_category")
GRADE_CHECKS = CHECKS[:4]  # grades a plan can't choose; the others are met or not by the courses chosen


def check_group(g: dict, done: dict, taken: dict, profile: dict, university: dict, catalog: dict, warnings: list[str]) -> dict:
    """A rule over the courses other major groups count (§6.2 check groups, `across` their ids or `major`): letter grades
    only, a CR cap, at most N courses below a grade, a GPA floor, at least or at most N units matching a filter, or
    courses from N subjects. A rule a student's courses break is `remaining` with a warning; until its groups are done
    it's `in_progress`."""
    out = {"id": g["id"], "title": g.get("title", g["id"]), "kind": "major", "source": g["source"], "counted": [],
           "in_progress": []}
    ids = [i for i, x in done.items() if x["kind"] == "major" and "check" not in x] if g["across"] == "major" else g["across"]
    parts = [done[i] for i in ids]
    counted = [c for p in parts for c in p["counted"] if c in taken]  # not a DPR-met course: no grade to check
    check = next(k for k in CHECKS if k in g)
    out |= {"check": check, "across": ids}
    # a units filter may also say where: `sf_state: true` ("at SF State"), `transfer: true` ("Nine transfer units ... may
    # count toward the Major", p.476)
    where = lambda f, c: (matches(f, c, catalog[c]) and not (f.get("sf_state") and taken.get(c, {}).get("transfer"))
                          and not (f.get("transfer") and not taken.get(c, {}).get("transfer")))
    broken = ""
    if check == "letter_grade":  # a course offered only CR/NC has no letter grade to take
        cr = [c for c in counted if taken[c]["grade"] == "CR" and catalog[c].get("grading") != "cr_nc"
              and c not in g.get("except", ())]
        broken = cr and f"{', '.join(cr)}: CR, but these courses must be taken for a letter grade"
    elif check == "max_cr":
        cap = g["max_cr"]
        cr = [c for c in counted if taken[c]["grade"] == "CR" and not (cap.get("except_exam") and taken[c].get("credit") == "exam")]
        n, limit = (sum(taken[c]["units"] for c in cr), cap["units"]) if "units" in cap else (len(cr), cap["courses"])
        broken = n > limit and f"{', '.join(cr)}: {n:g} {'units' if 'units' in cap else 'courses'} with CR, at most {limit:g}"
    elif check == "max_below":
        bar, most = GRADE_POINTS[g["max_below"]["grade"]], g["max_below"]["courses"]
        low = [c for c in counted if (rank(taken[c]["grade"]) or bar) < bar]
        broken = len(low) > most and f"{', '.join(low)}: below {g['max_below']['grade']}, at most {most} course(s) may be"
    elif check == "min_gpa":
        # As the major GPA (totals): SF State grades, a failed required course included, forgiven repeats left out
        codes = set(counted) | {c for p in parts for c in p.get("remaining", []) if c in taken}
        rows = [r for r in profile["completed"] if r["code"] in codes and not r.get("transfer")]
        out["gpa"] = value = gpa(rows, forgiven(rows, university["repeats"], catalog), catalog)
        broken = value is not None and value < g["min_gpa"] and f"GPA {value:.2f} in these courses, needs {g['min_gpa']:g}"
    elif check == "max_units_from":  # "A maximum of 3 units from AA S 685, AA S 688, or AA S 699 can count" (p.437)
        f = g["max_units_from"]
        over = [c for c in counted if where(f, c)]
        n, most, what = (len(over), f["courses"], "courses") if "courses" in f else (
            sum(taken[c]["units"] for c in over), f["units"], "units")
        broken = n > most and f"{', '.join(over)}: {n:g} {what}, at most {most:g} count"
    elif check in ("min_categories", "one_category"):  # `categories`: the printed lists ("A. Political Theory", ...)
        cats = [set(x) for x in g["categories"]]
        ahead = [c for p in parts for c in p["in_progress"]]
        if check == "min_categories":  # "at least one course in four of the following categories" (p.1640)
            need = g["min_categories"]
            status = "satisfied" if categories_met(cats, counted) >= need else \
                "in_progress" if categories_met(cats, counted + ahead) >= need else "remaining"
            return out | {"status": status, "categories_met": categories_met(cats, counted)}
        # "Select 9 units on advisement from one area below" (p.402): every course from the same list
        mixed = (counted + ahead) and not any(set(counted + ahead) <= cat for cat in cats)
        broken = mixed and f"{', '.join(counted + ahead)}: not all from one of its lists"
    elif check == "distinct_subjects":  # "drawn from at least two disciplines" (p.1264)
        return out | distinct_subjects(g | {"title": out["title"], "across": ids}, done, warnings)
    else:  # min_units_from: "a total of 30 Sociology units must be upper-division", "12 units in biology at SF State"
        f = g["min_units_from"]  # `courses: N` counts courses instead: "at least two of which must be upper-division"
        hit = lambda c: where(f, c)
        size = (lambda c: 1) if "courses" in f else (lambda c: taken[c]["units"] if c in taken else catalog[c]["units_min"])
        need = f.get("courses", f.get("units"))
        done_units = sum(size(c) for c in counted if hit(c))
        both = done_units + sum(size(c) for p in parts for c in p["in_progress"] if hit(c))
        out["min_units_from"] = f | {"done": done_units}
        return out | {"status": "satisfied" if done_units >= need else "in_progress" if both >= need else "remaining"}
    if broken:
        warnings.append(f"{out['title']}: {broken} ({g['source']})")
        return out | {"status": "remaining"}
    return out | {"status": "satisfied" if all(p["status"] in ("satisfied", "waived") for p in parts) else "in_progress"}


def categories_met(categories: list[set], courses: list[str]) -> int:
    """Most categories that each get a different course: a course printed in two lists counts for one (matching)."""
    owner: dict[str, int] = {}

    def place(i: int, seen: set) -> bool:
        for c in courses:
            if c in categories[i] and c not in seen:
                seen.add(c)
                if c not in owner or place(owner[c], seen):
                    owner[c] = i
                    return True
        return False

    return sum(place(i, set()) for i in range(len(categories)))


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
    if caps.get("all_transfer") and transfer_units > caps["all_transfer"]:  # 2024-25 states no total cap
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
    """Per-group status (satisfied / in_progress / remaining / waived / unparsed), university totals, warnings."""
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
    # GE areas the major's own courses meet (`ge_met`, §6.2: "Area 1B … is satisfied upon completion of ENGR 205 or …")
    in_major = ge_met_in_major(program, {c for c, t in taken.items() if (rank(t["grade"]) or -1) >= PASSING},
                               {c for c in profile.get("in_progress", []) if c in catalog})
    certified = frozenset(university.get("transfer", {}).get("certified_ld_ge", [])) if profile.get("ge_certified") else frozenset()
    if profile.get("ge_certified") and not certified:
        warnings.append(f"ge_certified: the {university['catalog_year']} Bulletin doesn't say which GE areas a transfer "
                        "certification meets, so it isn't applied; list the areas your DPR shows met in ge_done")
    for kind, rules in (("major", program), ("university", university)):
        # A requirement naming its courses (all_of, one_of) claims them before a choice does: an elective list that also
        # names a Select One's course doesn't take it from the Select One (BA Art History's ART 671, p.911)
        # … and a fill_to_total choice goes last: it's what the others leave of total_units (§6.2); a check reads them all
        for g in sorted(rules["groups"], key=lambda g: ("across" in g, kind == "major" and "from" in g, bool(g.get("fill_to_total")))):
            if kind == "major" and "across" in g:
                done[g["id"]] = check_group(amended(g), done, taken, profile, university, catalog, warnings)
                continue
            if kind == "major" and g.get("fill_to_total") and "total_units" in program:
                units = lambda c: taken[c]["units"] if c in taken else catalog[c]["units_min"] if c in catalog else 0
                given = sum(max(x["units_needed"], x.get("units_done", 0)) if "units_needed" in x else
                            sum(units(c) for c in x["counted"] + x["in_progress"] + x.get("remaining", []))
                            for x in done.values() if x["kind"] == "major")
                g = g | {"choose_units": max(g["choose_units"], program["total_units"] - given)}
            done[g["id"]] = r = eval_group(amended(g), kind, taken, profile, catalog, claimed if kind == "major" else None,
                                           no_cr_nc and kind == "major", done, warnings, certified)
            m = next((m for m in program.get("ge_met", []) if str(m["area"]) in ge_areas(g)), None) if kind == "university" else None
            if m and r["status"] in ("remaining", "in_progress"):  # still open: say which major courses will meet it
                status = in_major.get(str(m["area"]), ("remaining",))[0]
                if status == "satisfied" or status == "in_progress" and r["status"] == "remaining":
                    r = r | {"status": status, "met_by": "major"}
                done[g["id"]] = r | {"met_in_major": {"one_of": m["one_of"], "source": m["source"]}}
    groups = [done[g["id"]] for g in program["groups"] + university["groups"]]  # in the rules' order
    # A major course counts for GE too (p.2352): name the required ones still ahead that carry an open area, so the
    # client doesn't guess which open area a course meets.
    ahead = [c for g in groups if g["kind"] == "major" for c in g.get("remaining", []) if c in catalog]
    for g, rule in ((done[r["id"]], r) for r in university["groups"] if "from" in r):
        if g["status"] in ("remaining", "in_progress"):
            hit = [c for c in ahead if any(matches(f, c, catalog[c]) for f in filters_for(rule, profile))]
            if hit:
                g["major_courses"] = hit
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


# The §6.2 vocabulary a program file may use (check_program); `quote`, `unparsed` and `drafted_by` come from drafts.
PROGRAM_KEYS = {"program", "title", "catalog_year", "verified", "verified_by", "drafted_by", "total_units", "dpr_plan",
                "source", "global", "groups", "transfer_notes", "advising", "ge_met"}
GE_MET_KEYS = {"area", "one_of", "quote", "source"}
GROUP_KEYS = {"id", "title", "source", "quote", "unparsed", "all_of", "one_of", "choose_n", "choose_units", "from",
              "first_time_from", "min_grade", "min_units_from", "course_units", "exceptions", "approval", "waived_if",
              "fill_to_total", "across", "letter_grade", "max_cr", "max_below", "min_gpa", "max_units_from",
              "distinct_subjects", "min_categories", "one_category", "categories", "except",
              "waiver", "amendments", "after"}
FILTER_KEYS = {"list", "subject", "level", "except", "paired", "max_courses", "max_units", "ge_area", "ge_area_all", "approved"}
SELECTORS = ("list", "subject", "level", "ge_area", "ge_area_all", "approved")  # a filter needs one, else it takes anything
SHAPES = ("all_of", "one_of", "choose_n", "choose_units", "across", "unparsed")
PAGE = re.compile(r"p\.\s*(\d{1,4})(?:\s*[-–]\s*(\d{1,4}))?")  # the pages a source names: "p.152", "pp.1905-1906"


def squashed(text: str) -> str:
    """Text compared word for word, ignoring case, spacing and line breaks: a quote must survive pdftotext's wrapping."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def check_program(program: dict, catalog: dict, pages: set[int] | None = None, source: str | None = None,
                  university: dict | None = None) -> list[str]:
    """What a person must fix before a program file is used (§6.2 "AI-drafted rules"): keys outside the vocabulary, course
    codes not in the catalog, `source` pages outside the program's `pages`, a `quote` not in its `source` text, a group id
    the `university` rules use too, and groups whose minimum units don't add up to `total_units`. [] when it's clean."""
    out = [f"unknown key {k!r}" for k in program if k not in PROGRAM_KEYS]
    out += [f"missing {k!r}" for k in ("program", "title", "catalog_year", "total_units", "groups") if k not in program]
    ids, low, high = set(), 0.0, 0.0  # high: variable-unit courses at their most ("KIN 699 Independent Study", 1-3)

    def cites(label: str, x: dict) -> list[str]:
        """A page in `source`, inside the program's pages, and the Bulletin's own words where it's quoted."""
        found, cited = [], [int(p) for m in PAGE.findall(str(x.get("source", ""))) for p in m if p]
        if not cited:
            found.append(f"{label}: source must cite a page like \"p.2129\"")
        elif pages and not set(cited) <= pages:
            found.append(f"{label}: source {x['source']} is outside the program's pages ({min(pages)}-{max(pages)})")
        for key in ("quote", "approval", "exceptions"):  # shown to students as the Bulletin's own words
            for text in (x[key] if isinstance(x.get(key), list) else [x[key]] if key in x else []):
                if source is not None and squashed(text) not in squashed(source):
                    found.append(f"{label}: {key} isn't word for word in the Bulletin text: {text[:80]!r}")
        return found

    units = lambda cs, end="units_min": sum(catalog[c].get(end, catalog[c]["units_min"]) for c in cs if c in catalog)
    for g in program.get("groups", []):
        gid = g.get("id", "?")
        out += [f"{gid}: unknown key {k!r}" for k in g if k not in GROUP_KEYS]
        if gid in ids:
            out.append(f"{gid}: duplicate id")
        if university and gid in {x["id"] for x in university["groups"]}:  # the audit and planner look groups up by id
            out.append(f"{gid}: the university rules use this id too (their result would stand for this group); name it "
                       f"for the major, e.g. major_{gid}")
        if gid == "elective":  # build_plan's free electives are {"slot": "elective"}; a group's slot would merge into them
            out.append("elective: the planner names its free-elective slots this; name it for the major, e.g. major_elective")
        for a in g.get("after", []):  # build_plan and check_plan order exact courses, so only all_of / one_of groups
            other = next((x for x in program["groups"] if x.get("id") == a), None)
            if other is None:
                out.append(f"{gid}: after names {a!r}, not a group of this program")
            elif not ({"all_of", "one_of"} & other.keys() and {"all_of", "one_of"} & g.keys()):
                out.append(f"{gid}: after names {a!r}, which isn't an all_of or one_of group" if {"all_of", "one_of"} & g.keys()
                           else f"{gid}: after is only for an all_of or one_of group")
        ids.add(gid)
        shape = [k for k in SHAPES if k in g]
        if len(shape) != 1:
            out.append(f"{gid}: needs exactly one of {', '.join(SHAPES)} (has {', '.join(shape) or 'none'})")
        if g.get("unparsed"):
            out.append(f"{gid}: unparsed, a person writes this requirement from its quote")
        if ("choose_n" in g or "choose_units" in g) and "from" not in g:
            out.append(f"{gid}: a choose group needs `from`")
        if "choose_n" in g:  # in the university rules it's a designation (SF State Studies), met inside other courses
            out.append(f"{gid}: choose_n in a major is planned as a 0-unit designation slot; use choose_units, the units "
                       "the Bulletin prints for it")
        if "across" in g:
            checks = [k for k in CHECKS if k in g]
            if len(checks) != 1:
                out.append(f"{gid}: a check group needs exactly one of {', '.join(CHECKS)} (has {', '.join(checks) or 'none'})")
            courses = {x.get("id") for x in program.get("groups", []) if "across" not in x}
            if g["across"] != "major" and not (isinstance(g["across"], list) and g["across"] and set(g["across"]) <= courses):
                out.append(f"{gid}: across must be `major` or ids of this program's course groups (has {g['across']!r})")
            cap = g.get("max_cr", {})
            if "max_cr" in g and len({"units", "courses"} & set(cap)) != 1:
                out.append(f"{gid}: max_cr needs units or courses")
            if g.get("max_below", {}).get("grade", "C-") not in GRADE_POINTS or "max_below" in g and "courses" not in g["max_below"]:
                out.append(f"{gid}: max_below needs a grade and courses")
            if ("min_categories" in g or "one_category" in g) != ("categories" in g):
                out.append(f"{gid}: min_categories and one_category go with categories (the printed lists)")
        mins = [g[k] for k in ("min_units_from", "max_units_from") if k in g]
        out += [f"{gid}: {k} needs units" for k in ("min_units_from", "max_units_from") if k in g
                and len({"units", "courses"} & set(g[k]) if "across" in g else {"units"} & set(g[k])) != 1]
        filters = [f for key in ("from", "first_time_from") if key in g
                   for f in (g[key] if isinstance(g[key], list) else [g[key]])]
        out += [f"{gid}: unknown filter key {k!r}" for f in filters + mins for k in f
                if k not in FILTER_KEYS | ({"units", "courses", "sf_state", "transfer"} if f in mins else set())]
        out += [f"{gid}: a filter needs one of {', '.join(SELECTORS)}" for f in filters + mins
                if not set(SELECTORS) & set(f) and not (f in mins and {"sf_state", "transfer"} & set(f))]
        codes = (g.get("all_of", []) + [c for opt in g.get("one_of", []) for c in opt]
                 + [c for f in filters + mins for c in f.get("list", []) + f.get("except", [])] + g.get("except", [])
                 + [c for cat in g.get("categories", []) for c in cat]
                 + list(g["min_grade"] if isinstance(g.get("min_grade"), dict) else []))
        out += [f"{gid}: {c} is not in the {program.get('catalog_year', '')} catalog" for c in dict.fromkeys(codes) if c not in catalog]
        req = g.get("all_of", [])
        out += [f"{gid}: {a} and {b} are one cross-listed course, so all_of needs it twice; make it its own one_of group "
                f"[[{a}], [{b}]]" for i, a in enumerate(req) for b in req[i + 1:] if b in catalog.get(a, {}).get("crosslisted", ())]
        grades = g["min_grade"].values() if isinstance(g.get("min_grade"), dict) else [g["min_grade"]] if "min_grade" in g else []
        out += [f"{gid}: min_grade {m!r} isn't a grade" for m in grades if m not in GRADE_POINTS]
        out += cites(gid, g)
        low += (units(g.get("all_of", [])) + g.get("choose_units", 0)
                + min((units(opt) for opt in g.get("one_of", [])), default=0))
        high += (units(g.get("all_of", []), "units_max") + g.get("choose_units", 0)
                 + min((units(opt, "units_max") for opt in g.get("one_of", [])), default=0))
    labels = {a for x in (university or {}).get("groups", []) for a in ge_areas(x)}
    for m in program.get("ge_met", []):
        label, opts = f"ge_met {m.get('area', '?')}", m.get("one_of")
        out += [f"{label}: unknown key {k!r}" for k in m if k not in GE_MET_KEYS]
        out += [f"{label}: missing {k!r}" for k in sorted(GE_MET_KEYS - m.keys())]
        if university and str(m.get("area")) not in labels:
            out.append(f"{label}: not a GE area the university rules take")
        if not (isinstance(opts, list) and opts and all(isinstance(o, list) and o for o in opts)):
            out.append(f"{label}: one_of is a list of options, each a list of courses")
            opts = []
        out += [f"{label}: {c} is not in the {program.get('catalog_year', '')} catalog"
                for c in dict.fromkeys(c for o in opts for c in o) if c not in catalog]
        out += cites(label, m)
    if any("choose_n" in g or g.get("unparsed") for g in program.get("groups", [])):
        out.append(f"units: can't check total_units with choose_n or unparsed groups (the others add up to {low:g} of "
                   f"{program.get('total_units', 0):g}); a person adds them up")
    elif "total_units" in program and not low <= program["total_units"] <= (
            math.inf if any(g.get("fill_to_total") for g in program.get("groups", [])) else high):
        out.append(f"units: the groups' minimums add up to {low:g}"
                   + (f" ({high:g} with variable-unit courses at their most)" if high != low else "")
                   + f", total_units says {program['total_units']:g}")
    return out
