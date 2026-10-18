"""Plans: check_plan (ARCHITECTURE §7.3, the single source of truth for validity). Pure functions, no DB.

A plan is {"semesters": [{"term": "2027-spring", "courses": ["CSC 413", {"slot": "senior_electives", "units": 3}]}]}.
A slot is an unfilled pick for a choose-group, named by its group id; the AI fills it from list_eligible_electives.
`{"slot": "elective", "units": 3, "upper_division": true?}` is free units toward the 120 (the roadmaps' "elective").

Assumptions, reported as a warning on every check:
- in-progress and planned courses are passed with whatever grade their requirements and prereqs ask for;
- in-progress courses finish before the first planned term.
"""

import math
import re

from gatorpath.engine.prereq import leaves, prereq_warnings, reverse_index
from gatorpath.engine.rules import GRADE_POINTS, audit, blocks_repeat, number, rank

SEASONS = {"spring": 0, "summer": 1, "fall": 2}
TERM = re.compile(r"(\d{4})-(spring|summer|fall)")
ASSUMED = "A"  # stand-in grade for planned courses when simulating the audit; statuses only, never a GPA
OK, NO, UNVERIFIED = "ok", "no", "unverified"
UNVERIFIABLE = {"permission", "equivalent", "requirement", "high_school", "unknown"}


def term_key(term: str) -> tuple[int, int]:
    y, s = TERM.fullmatch(term).groups()
    return int(y), SEASONS[s]


def season_ok(c: str, term: str, catalog: dict, seasons=tuple(SEASONS)) -> tuple[bool, str | None]:
    """Class Search history (catalog[c]["offered"], ingest.offerings): False with a reason when the course ran in another
    of `seasons` but in none of the checked terms of this one. Never ran, or not in the last year: allowed with a note
    (rare isn't never)."""
    o = catalog.get(c, {}).get("offered")
    if not o:
        return True, None
    season, span = term[5:], f"Class Search {o['since']} to {o['until']}"
    if not o["last"]:
        return True, f"{c}: not offered in any term checked ({span}); ask the department when it runs"
    ran = [f"{s} {o[s][0]} of {o[s][1]}" for s in SEASONS if o[s][0]]
    if o[season][1] and not o[season][0] and any(o[s][0] for s in seasons if s != season):
        return False, (f"{c} in {term}: not offered in any of the last {o[season][1]} {season} terms (ran {', '.join(ran)}; "
                       f"{span}); check Class Search")
    y, s = term_key(o["until"])
    if term_key(o["last"]) <= (y - 1, s):
        return True, f"{c}: last offered {o['last']} ({span}); it may not run soon, so ask the department"
    return True, None


def passed(grade: str | None) -> bool:
    return rank(grade) is not None


def standing_ok(level: str, units: float, class_level: dict) -> bool:
    return {"lower": True, "upper": units >= class_level["upper"], "senior": units >= class_level["senior"],
            "graduate": False}.get(level, False)


def major_name(program: dict) -> str:
    return program["title"].split(" in ", 1)[-1]  # "Bachelor of Science in Computer Science" -> "Computer Science"


def evaluate(e: dict | None, ctx: dict) -> tuple[str, list[str]]:
    """Tri-state prereq check: ok / no / unverified, with the reasons behind anything not ok."""
    if e is None:
        return OK, []
    if "all" in e:
        parts = [evaluate(x, ctx) for x in e["all"]]
        state = NO if any(s == NO for s, _ in parts) else UNVERIFIED if any(s == UNVERIFIED for s, _ in parts) else OK
        return state, [r for s, rs in parts if s != OK for r in rs]
    if "any" in e:
        # "…; or permission of the instructor" never rescues a plan: it's reported, the other branches decide.
        perm = [x for x in e["any"] if "permission" in x]
        parts = [evaluate(x, ctx) for x in e["any"] if "permission" not in x]
        if not parts:
            return UNVERIFIED, [f"needs {x['permission']} permission" for x in perm]
        if any(s == OK for s, _ in parts):
            return OK, []
        state = UNVERIFIED if any(s == UNVERIFIED for s, _ in parts) else NO
        reasons = [r for _, rs in parts for r in rs]
        if state == NO and perm and all(r.startswith("GPA ") for r in reasons):
            state = UNVERIFIED  # ordering can't fix a GPA: the student needs permission (or a higher GPA)
        if len(parts) > 1:
            reasons = ["one of: " + "; ".join(reasons)]
        return state, reasons + [f"or {x['permission']} permission" for x in perm]
    if "course" in e:
        c = e["course"]
        if "max_grade" in e:  # retake branch: "MATH 226 … with a grade of C- or lower"
            g = ctx["grades"].get(c)
            ok = g is not None and (rank(g) or 0) <= GRADE_POINTS[e["max_grade"]]
            return (OK, []) if ok else (NO, [f"{c} taken with {e['max_grade']} or lower"])
        if c in ctx["done"] or (e.get("concurrent_ok") and c in ctx["same_term"]):
            g = ctx["grades"].get(c)  # None for planned / in-progress: assumed passed well enough
            if g == "CR" and "min_grade" in e and GRADE_POINTS[e["min_grade"]] > GRADE_POINTS["C-"]:
                return UNVERIFIED, [f"{c} with {e['min_grade']} or better (have CR, which means A through C-, p.2403)"]
            if g is not None and "min_grade" in e and (rank(g) or -1) < GRADE_POINTS[e["min_grade"]]:
                return NO, [f"{c} with {e['min_grade']} or better (have {g})"]
            return OK, []
        when = " (or the same term)" if e.get("concurrent_ok") else ""
        return NO, [f"{c}{' with ' + e['min_grade'] + ' or better' if 'min_grade' in e else ''} before this term{when}"]
    if "ge_area" in e:
        area = str(e["ge_area"])
        ok = (area in ctx["ge_done"] or area in ctx.get("slot_areas", ())
              or any(area in ctx["catalog"][c]["ge_areas"] for c in ctx["done"] if c in ctx["catalog"]))
        return (OK, []) if ok else (NO, [f"a GE Area {area} course"])
    if "qr_category" in e:
        qr = ctx["profile"].get("qr_pathway")
        if not qr:
            return UNVERIFIED, [f"QR category {e['qr_category']} (qr_pathway not given)"]
        mine = {int(x) for x in re.findall(r"\d", str(qr))}
        return (OK, []) if mine & set(e["qr_category"]) else (NO, [f"QR category {e['qr_category']}"])
    if "standing" in e:
        ok = standing_ok(e["standing"], ctx["units"], ctx["class_level"])
        return (OK, []) if ok else (NO, [f"{e['standing']} standing ({ctx['units']:g} units earned by then)"])
    if "gpa" in e:
        g = ctx["gpa"]
        if g is None:
            return UNVERIFIED, [f"GPA {e['gpa']} or higher (GPA not provided)"]
        ctx["gpa_used"] = True
        return (OK, []) if g >= e["gpa"] else (NO, [f"GPA {e['gpa']} or higher (have {g})"])
    if "restricted_to" in e:
        # ponytail: word match on the restriction text. Upgrade to a parsed {majors, standing, level} leaf if it misfires.
        text = e["restricted_to"]
        if re.search(r"(?<!under)graduate", text, re.I):
            return NO, [f"restricted to {text}"]
        if major_name(ctx["program"]).lower() not in text.lower():
            return UNVERIFIED, [f"restricted to {text}"]
        for level in ("senior", "upper"):
            if re.search(level, text, re.I) and not standing_ok(level, ctx["units"], ctx["class_level"]):
                return NO, [f"restricted to {text} ({ctx['units']:g} units earned by then)"]
        return OK, []
    kind = next(iter(UNVERIFIABLE & e.keys()), next(iter(e)))
    return UNVERIFIED, [f"{kind}: {e[kind]}"]


def upper_only(g: dict) -> bool:
    """True when every course that can fill the group is upper-division (300+), so its slots add upper-division units."""
    filters = g.get("from", [])
    filters = filters if isinstance(filters, list) else [filters]

    def up(f: dict) -> bool:
        if "ge_area" in f:
            areas = f["ge_area"] if isinstance(f["ge_area"], list) else [f["ge_area"]]
            return all(str(a).endswith("UD") for a in areas)
        if "list" in f:
            return all(300 <= number(c) <= 699 for c in f["list"])  # upper division = 300-699 (p.2391)
        level = str(f.get("level", "0"))
        return 300 <= int(level.rstrip("+")) <= 699 and not level.endswith("+")

    # A capped option ("one CSC graduate course", max_courses: 1) doesn't decide it: 700+ isn't upper division
    # (p.2391), and check_plan re-counts real units once the slot holds a course.
    main = [f for f in filters if "max_courses" not in f]
    return bool(main) and all(map(up, main))


def slot_ge_areas(slot: dict, groups: dict) -> set[str]:
    """GE areas a filled slot will carry (assumed for later "GE Area X" prereqs)."""
    f = groups.get(slot.get("slot"), {}).get("from", {})
    areas = f.get("ge_area", []) if isinstance(f, dict) else []
    return {str(a) for a in (areas if isinstance(areas, list) else [areas])}


def see_advisor(triggers: list[tuple[str, str]], program: dict, university: dict, into: list[dict] | None = None) -> list[dict]:
    """[(role, why)] -> who to see, with link and how to book, from the rules' `advising:` (ARCHITECTURE §7.5).
    A program's entry overrides the university's for the same role; reasons are merged per person."""
    entries = {a["role"]: a for a in university.get("advising", []) + program.get("advising", [])}
    out = {e["role"]: e for e in into or []}
    for role, why in triggers:
        a = entries.get(role) or entries.get("general_advising")
        if a is None:
            continue
        e = out.setdefault(a["role"], {k: v for k, v in a.items() if k != "when"} | {"why": []})
        if why not in e["why"]:
            e["why"].append(why)
    urgency = ["substitutions", "major_advisor", "international", "college_advising", "general_advising", "directory", "dpr"]
    return sorted(out.values(), key=lambda e: urgency.index(e["role"]) if e["role"] in urgency else len(urgency))


def ud_ge_ready(ctx: dict, university: dict) -> tuple[bool, list[str]]:
    """Upper-division GE needs GE 1A, 1B, 1C and 2 first (p.2319), checked like a prereq: done, ge_done, or slotted earlier."""
    ud = university.get("upper_division_ge")
    if not ud:
        return True, []
    groups = {g["id"]: g for g in university["groups"]}
    expr = {"all": [{"ge_area": a} for gid in ud["prerequisites"] for a in slot_ge_areas({"slot": gid}, groups)]}
    state, why = evaluate(expr, ctx)
    return state != NO, why


def check_plan(profile: dict, plan: dict, program: dict, university: dict, catalog: dict, prereqs: dict) -> dict:
    """{valid, errors, warnings, terms, remaining}. Errors make a plan invalid; warnings don't."""
    errors: list[dict] = []
    warnings: list[str] = ["Assumes in-progress and planned courses are passed with the grades their requirements need"]
    advise: list[tuple[str, str]] = []
    err = lambda kind, msg, **kw: errors.append({"error": kind, "message": msg, **kw})
    load, levels = university["academic_load"], university["class_level"]
    cap = profile.get("max_units_per_term", load["normal_max"])
    reps, most = university["repeats"], university["max_units"]
    f1_min = load["f1_min"]["undergraduate"] if profile.get("f1") else 0
    last_term = str((plan.get("semesters") or [{}])[-1].get("term", ""))

    completed = [r for r in profile.get("completed", []) if r["code"] in catalog]
    grades: dict[str, str] = {}
    for r in completed:  # best attempt
        if r["code"] not in grades or (rank(r["grade"]) or -1) > (rank(grades[r["code"]]) or -1):
            grades[r["code"]] = r["grade"]
    done = {c for c, g in grades.items() if passed(g)} | {c for c in profile.get("in_progress", []) if c in catalog}
    now = audit(profile, program, university, catalog)["totals"]  # repeats, transfer duplicates handled there
    units = now["units"]["value"] + now["units_in_progress"]
    gpa = profile.get("gpa", now["gpa_sf_state"]["value"])
    sfsu_gpa = now["gpa_sf_state"]["value"]

    groups = {g["id"]: g for g in program["groups"] + university["groups"]}
    last_taken = max((term_key(r["term"]) for r in completed if TERM.fullmatch(str(r.get("term", "")))), default=None)
    planned: list[dict] = []
    slots: list[dict] = []
    slot_areas: set[str] = set()
    seen_terms, terms_out = [], []
    for sem in plan.get("semesters", []):
        term = str(sem.get("term", ""))
        if not TERM.fullmatch(term):
            err("bad_term", f"{term!r} is not a term like 2027-fall")
            continue
        if seen_terms and term_key(term) <= term_key(seen_terms[-1]):
            err("term_order", f"{term} comes after {seen_terms[-1]} in the plan; list terms in order, once each", term=term)
        if last_taken and term_key(term) <= last_taken:
            err("term_in_past", f"{term} is not after the student's last completed term", term=term)
        seen_terms.append(term)

        codes = [c for c in sem.get("courses", []) if isinstance(c, str)]
        term_slots = [s for s in sem.get("courses", []) if isinstance(s, dict)]
        term_units = 0.0
        for c in codes:
            if c not in catalog:
                err("unknown_course", f"{c} is not in the {profile.get('catalog_year', '')} Bulletin", term=term, course=c)
                continue
            term_units += catalog[c]["units_min"]
            if not catalog[c]["repeatable"]:
                if codes.count(c) > 1 or c in done and (c in profile.get("in_progress", []) or c in {p["code"] for p in planned}):
                    err("duplicate", f"{c} is already in progress or planned earlier", term=term, course=c)
                elif c in grades and blocks_repeat(grades[c], reps):
                    err("already_passed", f"{c} was passed with {grades[c]}; it may not be repeated ({reps['source']})",
                        term=term, course=c)
                elif grades.get(c) in reps["no_repeat_while"]:
                    err("incomplete", f"{c} has an I (Incomplete); it can't be repeated until the I is converted to a "
                        f"grade ({reps['source']})", term=term, course=c)
        for s in term_slots:
            if s.get("slot") == "elective":
                slots.append(s | {"term": term})
                term_units += s.get("units", 0)
                continue
            g = groups.get(s.get("slot"))
            if g is None:
                err("unknown_slot", f"slot {s.get('slot')!r} is not a requirement group id", term=term)
                continue
            if "all_of" in g:
                err("bad_slot", f"{g['id']} lists exact courses; plan them instead of a slot", term=term)
                continue
            slots.append(s | {"term": term})
            term_units += s.get("units", 0)

        ctx = {"done": done, "same_term": set(codes), "grades": grades, "units": units, "profile": profile, "gpa": gpa,
               "ge_done": {str(a).upper() for a in profile.get("ge_done", [])}, "catalog": catalog,
               "program": program, "class_level": levels, "slot_areas": slot_areas}
        for c in codes:
            if c not in catalog:
                continue
            row = prereqs.get(c, {"expr": None, "status": "none", "raw_text": ""})
            state, why = evaluate(row["expr"], ctx)
            if state == NO:
                err("prereq_not_met", f"{c} in {term} needs: {'; '.join(why)}", term=term, course=c,
                    raw_text=row["raw_text"], source_page=catalog[c]["source_page"])
            elif state == UNVERIFIED:
                warnings.append(f"{c} in {term}: GatorPath can't check {'; '.join(why)}. Bulletin text: {row['raw_text']!r}")
                low_gpa = [r for r in why if r.startswith("GPA ") and "(have" in r]
                if low_gpa or why and all(r.startswith("needs ") and "permission" in r for r in why):
                    advise.append(("major_advisor", f"{c} in {term}: {'; '.join(low_gpa) or why[0]}; it needs the "
                                   "instructor's permission (ask the instructor, or plan another course)"))
            warnings.extend(w for w in prereq_warnings(c, row) if "partial" in w or "unparsed" in w)
            if note := season_ok(c, term, catalog)[1]:
                warnings.append(note)
        ud = university.get("upper_division_ge", {})
        for x in term_slots:
            if x.get("slot") in ud.get("groups", ()):
                ready, why = ud_ge_ready(ctx, university)
                if not ready:
                    warnings.append(f"{term}: {groups[x['slot']]['title']} slot before {'; '.join(why)} ({ud['source']}: "
                                    "upper-division GE courses require GE 1A, 1B, 1C and 2)")
                elif units < ud["recommended_after_units"]:
                    warnings.append(f"{term}: {groups[x['slot']]['title']} at {units:g} units; upper-division GE is designed "
                                    f"to be taken after {ud['recommended_after_units']} units ({ud['source']})")
        if ctx.get("gpa_used") and "gpa" not in profile:
            warnings.append(f"GPA-gated prereqs were checked with your SF State GPA ({gpa}); pass `gpa` if your overall GPA differs")

        summer = term.endswith("summer")
        if term_units > cap:
            err("over_cap", f"{term}: {term_units:g} units is over max_units_per_term ({cap:g})", term=term)
        ceiling = most["summer" if summer else "fall_spring"]
        if term_units > ceiling:
            why = (f"{term}: {term_units:g} units is over the {ceiling:g}-unit {'summer ' if summer else ''}maximum; more "
                   f"needs a cumulative SF State GPA of {most['above_needs_sf_state_gpa']:g} or better and an Exceed Maximum "
                   f"Units Petition signed by your major advisor, department chair and college dean ({most['source']})")
            if term_units >= most["dean_approval_from"]:
                why += f"; {most['dean_approval_from']:g}+ units need the {most['at_25_or_more']}"
            if sfsu_gpa is not None and sfsu_gpa < most["above_needs_sf_state_gpa"]:
                err("over_max_units", why + f" (SF State GPA {sfsu_gpa})", term=term)
            else:
                warnings.append(why)
                advise.append(("major_advisor", why))
        if not summer and term_units < f1_min:
            why = (f"{term}: {term_units:g} units; F-1 visa students must carry at least {f1_min:g} units every spring "
                   f"and fall ({load['source']})")
            if term == last_term:
                warnings.append(why + ". This is the plan's last term: the Bulletin gives no exception for it, so ask "
                                "the international office before planning a lighter final term")
                advise.append(("international", why + "; ask whether a lighter final term is allowed"))
            else:
                err("below_f1_minimum", why, term=term)
        elif not summer and 0 < term_units < load["normal_min"]:
            warnings.append(f"{term}: {term_units:g} units is below the normal {load['normal_min']:g}-{load['normal_max']:g} "
                            f"load, so it's part-time; F-1 visa students need at least {load['f1_min']['undergraduate']:g} "
                            f"in spring and fall, and it can matter for financial aid ({load['source']})")
        normal = load["summer_normal" if summer else "normal_max"]
        if term_units > normal:
            warnings.append(f"{term}: {term_units:g} units is above the normal load of {normal:g} ({load['source']}); "
                            "see an advisor before planning an overload")
            advise.append(("major_advisor", f"{term}: {term_units:g} units is above the normal load of {normal:g} "
                           f"({load['source']})"))
        if summer and not profile.get("include_summer", False):
            warnings.append(f"{term}: summer term planned but include_summer is false")
        terms_out.append({"term": term, "units": term_units, "units_before": units})
        planned += [{"code": c, "grade": ASSUMED, "term": term} for c in codes if c in catalog]
        done = done | {c for c in codes if c in catalog}
        for c in codes:  # a planned retake replaces the old grade for later prereqs
            grades.pop(c, None)
        slot_areas |= {a for x in term_slots for a in slot_ge_areas(x, groups)}
        units += term_units

    if f1_min and load.get("f1_continuous_enrollment") and len(seen_terms) > 1 and all(TERM.fullmatch(t) for t in seen_terms):
        term, skipped = seen_terms[0], []
        while term_key(term := next_term(term, False)) < term_key(seen_terms[-1]):
            if term not in seen_terms:
                skipped.append(term)
        if skipped:
            err("f1_gap", f"{', '.join(skipped)}: no courses planned; F-1 visa students must be continuously enrolled "
                f"every semester ({load['source']})")
    # Requirement coverage: audit as if everything in progress and planned is passed, then let slots fill the gaps.
    sim = profile | {"completed": profile.get("completed", []) + planned
                     + [{"code": c, "grade": ASSUMED} for c in profile.get("in_progress", []) if c in catalog],
                     "in_progress": []}
    result = audit(sim, program, university, catalog)
    slot_units: dict[str, float] = {}
    slot_count: dict[str, int] = {}
    for s in slots:
        slot_units[s["slot"]] = slot_units.get(s["slot"], 0) + s.get("units", 0)
        slot_count[s["slot"]] = slot_count.get(s["slot"], 0) + 1
    remaining = []
    for g in result["groups"]:
        if g["status"] in ("satisfied", "waived"):
            if g["id"] in slot_count:
                warnings.append(f"slot for {g['title']}: already satisfied without it")
            continue
        if "units_needed" in g and g["units_done"] + slot_units.get(g["id"], 0) >= g["units_needed"]:
            continue
        if "courses_needed" in g and len(g["counted"]) + slot_count.get(g["id"], 0) >= g["courses_needed"]:
            continue
        if "subjects" in g and (g["id"] in slot_count or any(i in slot_count for i in groups[g["id"]]["across"])):
            warnings.append(f"{g['title']}: depends on which courses fill the slots ({g['source']})")
            continue
        remaining.append(g["id"])
        err("requirement_not_covered", f"{g['title']} isn't covered by the plan", group=g["id"], source=g["source"])
    if slots:
        warnings.append(f"{len(slots)} slot(s) still to fill; pick each from list_eligible_electives for its group "
                        "(senior electives: at least 12 units must be CSC)")

    t = result["totals"]
    extra = sum(s.get("units", 0) for s in slots)
    extra_ud = sum(s.get("units", 0) for s in slots
                   if (s.get("upper_division") if s["slot"] == "elective" else upper_only(groups[s["slot"]])))
    for key, add in (("units", extra), ("upper_division_units", extra_ud)):
        if t[key]["value"] + add < t[key]["needed"]:
            err("units_short", f"{key.replace('_', ' ')}: {t[key]['value'] + add:g} after the plan, "
                f"{t[key]['needed']:g} needed ({t['source']})", total=key)
    warnings.extend(w for w in result["warnings"] if "not verified" in w or "DPR" in w)  # incl. not_on_dpr / dpr_met
    left_out = [g["title"] for g in program["groups"] + university["groups"] if g["id"] in profile.get("not_on_dpr", ())]
    years = university.get("major_course_currency_years")
    if years and seen_terms:
        last = term_key(seen_terms[-1])[0]
        major = {c for g in program["groups"] for c in g.get("all_of", [])}
        old = sorted({r["code"] for r in completed if r["code"] in major and TERM.fullmatch(str(r.get("term", "")))
                      and last - term_key(r["term"])[0] > years})
        if old:
            warnings.append(f"{', '.join(old)}: taken more than {years} years before graduation; the department may require "
                            "retaking it or showing currency in the subject (p.2393)")
    if left_out:
        advise.append(("general_advising", f"Confirm that {', '.join(left_out)} isn't required for your catalog year "
                       "(GatorPath left it out because your DPR doesn't list it)"))
    if not program.get("verified"):
        advise += [("major_advisor", f"GatorPath's {program['program']} rules aren't verified yet: review this plan "
                    "with an advisor before registering"), ("dpr", "Check what counts toward each requirement")]
    return {"catalog_year": program["catalog_year"], "valid": not errors, "errors": errors,
            "warnings": list(dict.fromkeys(warnings)), "see_advisor": see_advisor(advise, program, university),
            "terms": terms_out, "remaining": remaining}


def next_term(term: str, summer: bool) -> str:
    y, s = term_key(term)
    order = ["spring", "summer", "fall"] if summer else ["spring", "fall"]
    season = list(SEASONS)[s]
    if season not in order:  # a summer start when summers are off
        season = "spring"
    i = order.index(season) + 1
    return f"{y + i // len(order)}-{order[i % len(order)]}"


def pick_variant(profile: dict, roadmap: dict) -> str | None:
    if profile.get("adt") and "adt" in roadmap["variants"]:
        return "adt"
    qr = profile.get("qr_pathway")
    return next((k for k, v in roadmap["variants"].items() if qr and v.get("qr_pathway") == str(qr)), None)


def first_term(profile: dict) -> str | None:
    if profile.get("start_term"):
        return profile["start_term"]
    terms = [r["term"] for r in profile.get("completed", []) if TERM.fullmatch(str(r.get("term", "")))]
    if not terms:
        return None
    last = max(terms, key=term_key)
    if profile.get("in_progress"):  # this term's courses: the next spring/fall, not a summer the student may not plan
        last = next_term(last, False)  # ponytail: in progress in a summer term needs start_term
    return next_term(last, profile.get("include_summer", False))


def terms_through(start: str, end: str, summer: bool) -> int:
    """How many terms from start to end, inclusive (summers only when they're planned)."""
    n, t = 0, start
    while term_key(t) <= term_key(end) and n < 40:
        n += 1
        t = next_term(t, summer)
    return n


def chunks(units: float, size: float = 3) -> list[float]:
    out = [size] * int(units // size)
    return out + [units - size * len(out)] if units % size else out


def build_plan(profile: dict, program: dict, university: dict, roadmap: dict, catalog: dict, prereqs: dict) -> dict:
    """Deterministic baseline plan (ARCHITECTURE §8): required courses by critical path, then slots. Passes check_plan."""
    from gatorpath.engine.prereq import prereq_chain

    summer = profile.get("include_summer", False)
    seasons = ("spring", "summer", "fall") if summer else ("spring", "fall")  # a course waits only for these
    load, levels = university["academic_load"], university["class_level"]
    cap = profile.get("max_units_per_term", load["normal_max"])
    start = first_term(profile)
    if start is None:
        return {"catalog_year": program["catalog_year"], "needs_input": "start_term",
                "warnings": ["Give start_term (e.g. 2027-spring): no completed course has a term to plan from"]}
    if not TERM.fullmatch(str(start)):
        return {"catalog_year": program["catalog_year"], "error": "bad_term", "warnings": [f"{start!r} is not a term like 2027-fall"]}
    variant = pick_variant(profile, roadmap)
    in_prog = [c for c in profile.get("in_progress", []) if c in catalog]
    base = profile | {"completed": profile.get("completed", []) + [{"code": c, "grade": ASSUMED} for c in in_prog],
                      "in_progress": []}
    status = audit(base, program, university, catalog)
    required = [c for g in status["groups"] for c in g.get("remaining", []) if c in catalog]
    # The QR pathway only changes the math before MATH 226, so ask for it only while lower-division math is left.
    # ponytail: "MATH below 300" stands for the placement-dependent courses; read it from the roadmaps if a program differs.
    if variant is None and any(c.startswith("MATH ") and number(c) < 300 for c in required):
        return {"catalog_year": program["catalog_year"], "needs_input": "qr_pathway",
                "warnings": ["The roadmap (and the math courses before MATH 226) depends on the QR pathway / math "
                             "placement: give qr_pathway ('1/2' or '3/4'), or adt: true for a verified AA-T/AS-T"]}

    # Roadmap courses for this pathway that lead to a required course (QR 3/4: MATH 197, MATH 198 before MATH 226).
    ref = variant or next(iter(roadmap["variants"]))  # no pathway needed: any variant still orders the rest
    items = [i for sem in roadmap["variants"][ref]["semesters"] for i in sem["items"]]
    order = {c: n for n, c in enumerate(i for i in items if isinstance(i, str))}
    have = {r["code"] for r in profile.get("completed", []) if passed(r["grade"])} | set(in_prog)
    best = {}
    for r in profile.get("completed", []):
        if r["code"] not in best or (rank(r["grade"]) or -1) > (rank(best[r["code"]]) or -1):
            best[r["code"]] = r["grade"]
    stuck = [c for c in required if not catalog[c]["repeatable"] and blocks_repeat(best.get(c), university["repeats"])]
    warnings = [f"{c}: passed with {best[c]}, which doesn't count toward this requirement, and a course passed with CR "
                "or C or better can't be repeated (p.2392); see an advisor about a substitution or petition" for c in stuck]
    required = [c for c in required if c not in stuck]
    closure = {e["code"] for c in required if c in prereqs for e in prereq_chain(c, prereqs)["chain"]}
    todo = required + ([c for c in order if c in closure and c not in have and c not in required and c in catalog]
                       if variant else [])

    # Priority: longest chain of plan courses that depend on it (critical path), then roadmap order.
    needs = {c: {l["course"] for l in leaves(prereqs.get(c, {}).get("expr")) if "course" in l and l["course"] in todo and l["course"] != c}
             for c in todo}
    hard = {c: {l["course"] for l in leaves(prereqs.get(c, {}).get("expr"))
                if "course" in l and l["course"] in todo and not l.get("concurrent_ok") and l["course"] != c} for c in todo}
    depth: dict[str, int] = {}

    def chain(c: str, seen: frozenset = frozenset()) -> int:
        if c not in depth:
            depth[c] = 1 + max((chain(d, seen | {c}) for d in todo if c in hard[d] and d not in seen), default=0)
        return depth[c]

    rank_of = lambda c: (-chain(c), order.get(c, len(order)), c)

    # Slots for what the courses leave open, plus free electives up to the unit totals.
    sim = base | {"completed": base["completed"] + [{"code": c, "grade": ASSUMED} for c in todo]}
    after = audit(sim, program, university, catalog)
    slots: list[dict] = []
    groups = {g["id"]: g for g in program["groups"] + university["groups"]}
    for g in after["groups"]:
        if g["status"] in ("satisfied", "waived"):
            continue
        if "subjects" in g:  # GE Area 4 "in at least two different disciplines": one more course from another subject
            slots.append({"slot": g["id"], "units": 3, "_kind": "ge",
                          "note": f"a course for {', '.join(groups[g['id']]['across'])} in a subject other than "
                                  f"{', '.join(g['subjects'])} ({g['source']})"})
            continue
        if "units_needed" in g:
            kind = "major" if g["kind"] == "major" else "ud_ge" if upper_only(groups[g["id"]]) else "ge"
            slots += [{"slot": g["id"], "units": u, "_kind": kind} for u in chunks(g["units_needed"] - g["units_done"])]
        elif "courses_needed" in g:
            slots += [{"slot": g["id"], "units": 0, "_kind": "tag",
                       "note": "usually met by a GE or elective course that also carries this designation"}
                      for _ in range(g["courses_needed"] - len(g["counted"]))]
    t = after["totals"]
    slot_units = sum(s["units"] for s in slots)
    ud_slot_units = sum(s["units"] for s in slots if s["_kind"] in ("major", "ud_ge"))
    free = max(0, t["units"]["needed"] - t["units"]["value"] - slot_units)
    ud_short = max(0, t["upper_division_units"]["needed"] - t["upper_division_units"]["value"] - ud_slot_units)
    for u in chunks(free):
        upper = ud_short > 0
        ud_short -= u if upper else 0
        slots.append({"slot": "elective", "units": u, "_kind": "elective"} | ({"upper_division": True} if upper else {}))

    # Senior-elective slots wait for the courses the roadmap places before its first senior_elective slot.
    first_elective = next((n for n, sem in enumerate(roadmap["variants"][ref]["semesters"])
                           if any(isinstance(i, dict) and i.get("slot") == "senior_elective" for i in sem["items"])), None)
    before_electives = {i for sem in roadmap["variants"][ref]["semesters"][:first_elective] for i in sem["items"]
                        if isinstance(i, str)} if first_elective is not None else set()

    done = set(have)
    grades = {r["code"]: r["grade"] for r in profile.get("completed", [])}
    units = status["totals"]["units"]["value"]
    gpa = profile.get("gpa", status["totals"]["gpa_sf_state"]["value"])
    left = sorted(todo, key=rank_of)
    first_ok: dict[str, str] = {}  # the first term a course could have gone in
    semesters, term = [], start
    slot_areas: set[str] = set()
    for _ in range(20):
        if not left and not slots:
            break
        if term.endswith("summer") and not summer:
            term = next_term(term, summer)
            continue
        limit = min(cap, load["summer_normal"]) if term.endswith("summer") else cap
        placed: list[str] = []
        used = 0.0
        ctx = {"done": done, "grades": grades, "units": units, "profile": profile, "gpa": gpa,
               "ge_done": {str(a).upper() for a in profile.get("ge_done", [])}, "catalog": catalog,
               "program": program, "class_level": levels, "slot_areas": slot_areas}

        def ok(c: str, same: set) -> bool:
            state, _ = evaluate(prereqs.get(c, {}).get("expr"), ctx | {"same_term": same})
            # An unverifiable branch ("or equivalent", high-school courses) doesn't let a course jump ahead of a
            # prereq that's still in the plan: wait for it, in an earlier term (or this one, for corequisites).
            waiting = (hard[c] - done) | (needs[c] - hard[c] - done - same)
            return (state == OK or (state == UNVERIFIED and not waiting)) and season_ok(c, term, catalog, seasons)[0]

        changed = True
        while changed:
            changed = False
            for c in [c for c in left if c not in placed]:
                bundle = [c] + [d for d in needs[c] if d in left and d not in placed and c in needs.get(d, ()) and d not in hard[c]]
                u = sum(catalog[b]["units_min"] for b in bundle)
                same = set(placed) | set(bundle)
                if not all(ok(b, same) for b in bundle):
                    continue
                first_ok.setdefault(c, term)
                if used + u <= limit:
                    placed += bundle
                    used += u
                    changed = True
                    break
        left = [c for c in left if c not in placed]
        ready_electives = units >= levels["upper"] and before_electives & set(todo) <= done
        term_slots = []
        ud = university.get("upper_division_ge", {})
        ud_ok = units >= ud.get("recommended_after_units", levels["upper"]) and ud_ge_ready(ctx | {"same_term": set()}, university)[0]
        for kind in ("tag", "ge", "ud_ge", "major", "elective"):
            for s in [s for s in slots if s["_kind"] == kind]:
                if kind == "ud_ge" and not ud_ok:
                    continue
                if kind == "major" and units < levels["upper"]:
                    continue
                if kind == "major" and not ready_electives:
                    continue
                if kind == "elective" and s.get("upper_division") and units < levels["upper"]:
                    continue
                if used + s["units"] <= limit:
                    term_slots.append(s)
                    slots.remove(s)
                    used += s["units"]
        # F-1 (pp.2390, 2393): a spring/fall term with more to come is filled toward the minimum with elective slots
        # that would otherwise wait for the roadmap's order; check_plan flags what still falls short.
        f1_min = load["f1_min"]["undergraduate"] if profile.get("f1") and not term.endswith("summer") else 0
        if used < f1_min and (left or slots):
            for s in [s for s in slots if s["_kind"] in ("major", "elective")]:
                if units >= levels["upper"] or not (s["_kind"] == "major" or s.get("upper_division")):
                    if used < f1_min and used + s["units"] <= limit:
                        term_slots.append(s)
                        slots.remove(s)
                        used += s["units"]
        off_season = [c for c in left if not season_ok(c, term, catalog, seasons)[0]]
        if not placed and not any(s["units"] for s in term_slots) and off_season:
            warnings.append(f"{term}: nothing left runs in {term[5:]}; {', '.join(off_season)} wait for a term they run in")
            term = next_term(term, summer)
            continue
        if not placed and not any(s["units"] for s in term_slots):
            blocked = {c: evaluate(prereqs.get(c, {}).get("expr"), ctx | {"same_term": set()})[1] for c in left}
            warnings.append(f"Stopped at {term}: nothing more can be scheduled. Blocked: "
                            + "; ".join(f"{c} needs {', '.join(w) or 'more units per term'}" for c, w in blocked.items())
                            + ("; slots waiting: " + ", ".join(sorted({s['slot'] for s in slots})) if slots else ""))
            semesters += [{"term": term, "courses": [{k: v for k, v in s.items() if k != "_kind"} for s in term_slots], "units": 0}] if term_slots else []
            break
        semesters.append({"term": term, "units": used,
                          "courses": placed + [{k: v for k, v in s.items() if k != "_kind"} for s in term_slots]})
        done |= set(placed)
        for c in placed:  # a planned retake replaces the old grade
            grades.pop(c, None)
        slot_areas = slot_areas | {a for x in term_slots for a in slot_ge_areas(x, groups)}
        units += used
        term = next_term(term, summer)
    plan = {"semesters": semesters}
    check = check_plan(profile, plan, program, university, catalog, prereqs)

    # Why each course is where it is, and what sets the pace.
    from gatorpath.engine.rules import matches

    term_of = {c: i for i, s in enumerate(semesters) for c in s["courses"] if isinstance(c, str)}
    dependents = {c: sorted((d for d in todo if c in hard[d]), key=rank_of) for c in todo}
    coreqs = {c: sorted(d for d in needs[c] - hard[c] if c in needs.get(d, ())) for c in todo}
    elective_filters = [f for g in program["groups"] if "from" in g
                        for f in (g["from"] if isinstance(g["from"], list) else [g["from"]])]
    opens = {c: [d for d in reverse_index(prereqs).get(c, []) if d in catalog and d not in have and d not in todo
                 and any(matches(f, d, catalog[d]) for f in elective_filters)] for c in todo}

    def longest(c: str) -> list[str]:
        path = [c]
        while nxt := [d for d in dependents[path[-1]] if depth[d] == depth[path[-1]] - 1 and d not in path]:
            path.append(nxt[0])
        return path

    for s in semesters:
        notes = {}
        for c in (x for x in s["courses"] if isinstance(x, str)):
            path, parts = longest(c), []
            if c not in required:
                parts.append(f"on the {variant} roadmap for your QR pathway")
            if dependents[c]:
                parts.append(f"needed before {', '.join(dependents[c])} in this plan")
            if coreqs[c]:
                parts.append(f"corequisite of {', '.join(coreqs[c])}: take them in the same term")
            if opens[c]:
                more = f", +{len(opens[c]) - 5} more" if len(opens[c]) > 5 else ""
                parts.append(f"opens {len(opens[c])} senior-elective option(s): {', '.join(opens[c][:5])}{more}")
            if not (dependents[c] or coreqs[c] or opens[c]):
                parts.append("no later course in this plan needs it, so it can move if needed")
            if len(path) >= 3:
                parts.append(f"starts a {len(path)}-term chain: {' → '.join(path)}")
            if len(path) >= 2 and all(term_of.get(path[k + 1]) == term_of[path[k]] + 1 for k in range(len(path) - 1)):
                parts.append(f"no slack: delaying it pushes back {path[-1]}")
            if first_ok.get(c, s["term"]) != s["term"]:
                parts.append(f"could have started in {first_ok[c]}; waited for room under {cap:g} units per term")
            notes[c] = parts[0][0].upper() + "; ".join(parts)[1:]
        s["why"] = notes

    plan_units = sum(s["units"] for s in semesters)
    critical = min(todo, key=rank_of) if todo else None
    pace = {"terms": len(semesters), "units_per_term": cap, "include_summer": summer, "planned_units": plan_units,
            "min_terms_by_prereqs": depth[critical] if critical else 0,
            "longest_chain": longest(critical) if critical else [],
            "min_terms_by_units": math.ceil(plan_units / cap) if cap else 0}
    target = profile.get("graduate_by")
    if target and TERM.fullmatch(str(target)) and semesters:
        available = terms_through(start, target, summer)
        pace |= {"graduate_by": target, "terms_available": available,
                 "on_time": check["valid"] and term_key(semesters[-1]["term"]) <= term_key(target)}
        if not pace["on_time"]:
            why_not = []
            if pace["min_terms_by_prereqs"] > available:
                why_not.append(f"the prereq chain alone needs {pace['min_terms_by_prereqs']} terms "
                               f"({' → '.join(pace['longest_chain'])}); only {available} until {target}")
            if pace["min_terms_by_units"] > available:
                why_not.append(f"{plan_units:g} units at {cap:g} per term needs {pace['min_terms_by_units']} terms; only "
                               f"{available}: add summers or raise max_units_per_term (above {load['normal_max']:g} is "
                               f"an overload, {load['source']})")
            if not why_not:
                last = semesters[-1]
                held = [c if isinstance(c, str) else c["slot"] for c in last["courses"] if isinstance(c, str) or c["units"]]
                why_not.append(f"the plan needs {len(semesters)} terms; the last ({last['term']}) holds {', '.join(held)}. "
                               "Senior electives wait for the core courses the roadmap puts first, and upper-division GE "
                               f"for {levels['upper']} units" + ("" if summer else "; try include_summer"))
            pace["why_not"] = why_not
    return {"catalog_year": program["catalog_year"], "variant": variant, **plan,
            "est_graduation_term": semesters[-1]["term"] if semesters and check["valid"] else None, "pace": pace,
            "warnings": warnings + check["warnings"],
            "see_advisor": see_advisor([("substitutions", f"{c}: passed with {best[c]}, which this requirement doesn't "
                                         "accept, and it can't be repeated; ask about a substitution or petition")
                                        for c in stuck], program, university, check["see_advisor"]),
            "check": {"valid": check["valid"], "errors": check["errors"]}}


def eligible_options(profile: dict, group_id: str, program: dict, university: dict, catalog: dict, prereqs: dict,
                     plan: dict | None = None, by_term: str | None = None, limit: int = 25) -> dict:
    """Courses that can fill a choose-group, with readiness at `by_term` and the other open requirements each covers.

    Ranked: ready first, then courses that also cover the most other open requirements (ENVS 401 = 4UD + ESCA + GP),
    then the preferred subject while a `min_units_from` minimum is short (12 CSC units of senior electives).
    """
    from gatorpath.engine.rules import matches, subject

    groups = {g["id"]: g for g in program["groups"] + university["groups"]}
    kind = {g["id"]: k for k, rules in (("major", program), ("university", university)) for g in rules["groups"]}
    g = groups.get(group_id)
    if g is None:
        return {"error": "unknown_group", "groups": list(groups)}
    if "all_of" in g or "from" not in g:
        return {"error": "not_a_choice", "warnings": [f"{group_id} isn't a choose-group; see get_program_requirements"]}
    filters = g["from"] if isinstance(g["from"], list) else [g["from"]]

    in_prog = [c for c in profile.get("in_progress", []) if c in catalog]
    semesters = (plan or {}).get("semesters", [])
    planned = [(s["term"], c) for s in semesters for c in s.get("courses", []) if isinstance(c, str) and c in catalog]
    sim = profile | {"completed": profile.get("completed", []) + [{"code": c, "grade": ASSUMED} for c in in_prog]
                     + [{"code": c, "grade": ASSUMED, "term": t} for t, c in planned], "in_progress": []}
    after = audit(sim, program, university, catalog)
    status = {x["id"]: x for x in after["groups"]}
    open_groups = [i for i, x in status.items() if x["status"] not in ("satisfied", "waived") and i != group_id
                   and "from" in groups[i]]
    taken = {r["code"] for r in profile.get("completed", []) if passed(r["grade"])} | set(in_prog) | {c for _, c in planned}

    first = by_term or (semesters[0]["term"] if semesters else first_term(profile))
    if first is None or not TERM.fullmatch(str(first)):
        return {"error": "needs_input", "needs_input": "by_term",
                "warnings": ["Give by_term (e.g. 2027-fall), a plan, or completed courses with terms"]}
    now = audit(profile, program, university, catalog)["totals"]
    base_units = now["units"]["value"] + now["units_in_progress"]
    terms = sorted({first} | {s["term"] for s in semesters if term_key(s["term"]) >= term_key(first)}, key=term_key)
    gpa = profile.get("gpa", now["gpa_sf_state"]["value"])
    grades = {r["code"]: r["grade"] for r in profile.get("completed", [])}

    def ctx_at(term: str) -> dict:
        before = [s for s in semesters if term_key(s["term"]) < term_key(term)]
        done = taken - {c for t, c in planned if term_key(t) >= term_key(term)}
        units = base_units + sum(sum(catalog[c]["units_min"] if isinstance(c, str) and c in catalog
                                     else c.get("units", 0) if isinstance(c, dict) else 0 for c in s["courses"])
                                 for s in before)
        return {"done": done, "same_term": {c for t, c in planned if t == term}, "grades": grades, "units": units,
                "profile": profile, "gpa": gpa, "ge_done": {str(a).upper() for a in profile.get("ge_done", [])},
                "catalog": catalog, "program": program, "class_level": university["class_level"],
                "slot_areas": {a for s in semesters if term_key(s["term"]) < term_key(term)
                               for x in s["courses"] if isinstance(x, dict) for a in slot_ge_areas(x, groups)}}

    ctxs = {t: ctx_at(t) for t in terms}
    target = status[group_id]
    pref = g.get("min_units_from", {})
    pref_short = bool(pref) and target.get("min_units_from", {}).get("done", 0) < pref.get("units", 0)
    used = {i: sum(1 for c in target["counted"] + target["in_progress"] if matches(f, c, catalog[c]))
            for i, f in enumerate(filters)}
    options = []
    for code, course in catalog.items():
        if code in taken:
            continue
        hit = [i for i, f in enumerate(filters) if matches(f, code, course) and used[i] < f.get("max_courses", math.inf)]
        if not hit:
            continue
        expr = prereqs.get(code, {}).get("expr")
        state, why = evaluate(expr, ctxs[first])
        option = {"code": code, "title": course["title"], "units": course["units_min"], "source_page": course["source_page"],
                  "readiness": {OK: "ready", UNVERIFIED: "check", NO: "blocked"}[state],
                  "also_covers": [i for i in open_groups if not (kind[i] == kind[group_id] == "major")
                                  and any(matches(f, code, course) for f in (groups[i]["from"] if isinstance(groups[i]["from"], list) else [groups[i]["from"]]))],
                  "offered": "unknown"}
        if state != OK:
            option["blocked_by" if state == NO else "cannot_check"] = why
        if state == NO:
            later = next((t for t in terms[1:] if evaluate(expr, ctxs[t])[0] != NO), None)
            if later:
                option["ready_by"] = later
        if any("max_courses" in filters[i] for i in hit):
            option["note"] = f"at most {min(filters[i]['max_courses'] for i in hit)} course(s) from this part of the list"
        options.append(option)
    order = {"ready": 0, "check": 1, "blocked": 2}
    options.sort(key=lambda o: (order[o["readiness"]], -len(o["also_covers"]),
                                not (pref_short and subject(o["code"]) == pref.get("subject")), o["code"]))
    need = {k: target[k] for k in ("units_needed", "units_done", "courses_needed", "min_units_from") if k in target}
    return {"catalog_year": program["catalog_year"], "group": group_id, "title": g.get("title", group_id),
            "source": g["source"], "by_term": first, "status": target["status"], **need,
            "options": options[:max(1, limit)], "total_options": len(options),
            "warnings": [f"also_covers lists other open requirements a course would count for (GE, SF State Studies and "
                         f"American Institutions may overlap with each other and the major, p.2352)"]}

