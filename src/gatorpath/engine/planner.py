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
from collections import Counter

from gatorpath.engine.prereq import leaves, prereq_warnings, reverse_index
from gatorpath.engine.rules import GRADE_CHECKS, GRADE_POINTS, audit, blocks_repeat, ge_areas, ge_met_in_major, number, rank

# Winter Session runs "during the intersession between the Fall and Spring term" (2026-27 p.1716): 2027-winter is
# January 2027, after 2026-fall and before 2027-spring.
SEASONS = {"winter": 0, "spring": 1, "summer": 2, "fall": 3}
TERM = re.compile(r"(\d{4})-(winter|spring|summer|fall)")
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
    if term in o.get("schedule", {}):  # that term's own schedule was scraped (a published next term): a fact, not history
        return (True, None) if o["schedule"][term] else (False, f"{c} in {term}: not on the {term} Class Search schedule; "
                                                                 "check Class Search")
    season, span = term[5:], f"Class Search {o['since']} to {o['until']}"
    if season not in o:  # Winter Session isn't in the offering history
        return True, f"{c}: Class Search history doesn't cover {season} terms; check that term's schedule"
    if not o["last"]:
        return True, f"{c}: not offered in any term checked ({span}); ask the department when it runs"
    ran = [f"{s} {o[s][0]} of {o[s][1]}" for s in SEASONS if s in o and o[s][0]]
    if o[season][1] and not o[season][0] and any(o[s][0] for s in seasons if s != season and s in o):
        return False, (f"{c} in {term}: not offered in any of the last {o[season][1]} {season} terms (ran {', '.join(ran)}; "
                       f"{span}); check Class Search")
    y, s = term_key(o["until"])
    if term_key(o["last"]) <= (y - 1, s):
        return True, f"{c}: last offered {o['last']} ({span}); it may not run soon, so ask the department"
    return True, None


def passed(grade: str | None) -> bool:
    return rank(grade) is not None


def known_grades(completed: list[dict], in_progress: list[str]) -> dict[str, str]:
    """Best grade per completed course. A course in progress again (a retake) has none: like any in-progress course,
    it's assumed passed with the grade later prereqs need."""
    grades: dict[str, str] = {}
    for r in completed:
        if r["code"] not in grades or (rank(r["grade"]) or -1) > (rank(grades[r["code"]]) or -1):
            grades[r["code"]] = r["grade"]
    return {c: g for c, g in grades.items() if c not in in_progress}


def standing_ok(level: str, units: float, class_level: dict) -> bool:
    return {"lower": True, "upper": units >= class_level["upper"], "senior": units >= class_level["senior"],
            "graduate": False}.get(level, False)


def major_name(program: dict) -> str:
    return program["title"].split(" in ", 1)[-1]  # "Bachelor of Science in Computer Science" -> "Computer Science"


def itep(ctx: dict) -> bool:
    """An Integrated Teacher Education Program: a bachelor's blended with a preliminary credential (`global: itep`, D27)."""
    return bool(ctx.get("program", {}).get("global", {}).get("itep"))


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
        elif state == NO and perm and itep(ctx) and all(r.startswith("graduate standing") for r in reasons):
            # D27: an ITEP student takes graduate credential courses by permission; what ordering fixes still waits
            return UNVERIFIED, [f"needs {x['permission']} permission" for x in perm]
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
        if c in ctx["profile"].get("dpr_met", ()):
            return UNVERIFIED, [f"{c}, which your DPR shows met by a substitution; ask the instructor whether that "
                                "counts for this prerequisite"]
        when = " (or the same term)" if e.get("concurrent_ok") else ""
        return NO, [f"{c}{' with ' + e['min_grade'] + ' or better' if 'min_grade' in e else ''} before this term{when}"]
    if "ge_area" in e:
        area = str(e["ge_area"])
        ok = (area in ctx["ge_done"] or area in ctx.get("slot_areas", ())
              or any(area in ctx["catalog"][c]["ge_areas"] for c in ctx["done"] if c in ctx["catalog"])
              or ge_met_in_major(ctx.get("program", {}), set(ctx["done"])).get(area, ("",))[0] == "satisfied")
        if not ok and ctx["profile"].get("prior_bachelors"):  # GE is waived for them (p.2313); a prereq isn't
            return UNVERIFIED, [f"GE Area {area} (your prior bachelor's degree waives GE; confirm it covers this "
                                "prerequisite)"]
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
    if "not_after" in e:  # "Not open to students who have completed ERTH 112"
        c = e["not_after"]
        return (NO, [f"no {c} before this term (not open to students who have completed it)"]) if c in ctx["done"] \
            else (OK, [])
    if "restricted_to" in e:
        # ponytail: word match on the restriction text. Upgrade to a parsed {majors, standing, level} leaf if it misfires.
        text = e["restricted_to"]
        # graduate-only unless it also opens to undergraduates: "upper-division and graduate … majors" (MUS 434), "graduate
        # standing or KIN ITEP credential students" (KIN 750, taken in the integrated teacher education program)
        if re.search(r"(?<!under)graduate", text, re.I) and not re.search(r"upper|undergraduate|junior|senior|\bor\b", text, re.I) \
                and not (itep(ctx) and re.search(r"credential", text, re.I)):  # "graduate and … credential students": ITEP's are
            return NO, [f"restricted to {text}"]
        if major_name(ctx["program"]).lower() not in text.lower():
            return UNVERIFIED, [f"restricted to {text}"]
        for level in ("senior", "upper"):
            if re.search(level, text, re.I) and not standing_ok(level, ctx["units"], ctx["class_level"]):
                return NO, [f"restricted to {text} ({ctx['units']:g} units earned by then)"]
        return OK, []
    kind = next(iter(UNVERIFIABLE & e.keys()), next(iter(e)))
    return UNVERIFIED, [f"{kind}: {e[kind]}"]


def exact_courses(g: dict) -> list[str]:
    """The courses an all_of or one_of group names (every option of a Select One)."""
    return g.get("all_of", []) + [c for o in g.get("one_of", []) for c in o]


def upper_only(g: dict) -> bool:
    """True when every course that can fill the group is upper-division (300+), so its slots add upper-division units."""
    filters = g.get("from", [])
    filters = filters if isinstance(filters, list) else [filters]

    def up(f: dict) -> bool:
        if isinstance(f.get("level"), list):  # "500 or 600-level": upper division when each is
            return all(up(f | {"level": x}) for x in f["level"])
        if f.get("level") in ("lower", "upper"):  # a GE filter's level (2024-25 D2: Area 4 + USH, lower division)
            return f["level"] == "upper"
        if "ge_area_all" in f:  # the course carries every area: one UD area makes it upper division
            return any(str(a).endswith("UD") for a in f["ge_area_all"])
        if "ge_area" in f:
            areas = f["ge_area"] if isinstance(f["ge_area"], list) else [f["ge_area"]]
            return all(str(a).endswith("UD") for a in areas)
        if "list" in f:
            return all(300 <= number(c) <= 699 for c in f["list"])  # upper division = 300-699 (p.2391)
        level = str(f.get("level", "0"))
        return 300 <= int(level.rstrip("+")) <= 699 and not level.endswith("+")

    # A capped option ("one CSC graduate course", max_courses: 1; "up to 9 units of lower-division", max_units: 9) doesn't
    # decide it: 700+ isn't upper division (p.2391), and check_plan re-counts real units once the slot holds a course.
    main = [f for f in filters if "max_courses" not in f and "max_units" not in f]
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


def ge_done_areas(profile: dict, university: dict) -> set[str]:
    """GE areas met outside SF State courses: ge_done, plus every lower-division area when Cal-GETC certified (p.2304)."""
    done = {str(a).upper() for a in profile.get("ge_done", [])}
    if profile.get("ge_certified"):
        groups = {g["id"]: g for g in university["groups"]}
        done |= {str(a).upper() for gid in university.get("transfer", {}).get("certified_ld_ge", [])
                 for a in slot_ge_areas({"slot": gid}, groups)}
    return done


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
    fixed = profile.get("max_units_per_term")  # the student's cap; else each term's max_units (build_plan), else 15
    reps, most = university["repeats"], university["max_units"]
    f1_min = load["f1_min"]["undergraduate"] if profile.get("f1") else 0
    rcl = university.get("f1_final_term")
    last_term = str((plan.get("semesters") or [{}])[-1].get("term", ""))
    this_term = profile.get("current_term") if TERM.fullmatch(str(profile.get("current_term", ""))) else None  # by the server

    completed = [r for r in profile.get("completed", []) if r["code"] in catalog]
    grades = known_grades(completed, profile.get("in_progress", []))
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
            err("bad_term", f"{term!r} is not a term like 2027-fall (or 2027-winter for Winter Session)")
            continue
        if seen_terms and term_key(term) <= term_key(seen_terms[-1]):
            err("term_order", f"{term} comes after {seen_terms[-1]} in the plan; list terms in order, once each", term=term)
        if last_taken and term_key(term) <= last_taken:
            err("term_in_past", f"{term} is not after the student's last completed term", term=term)
        elif this_term and term_key(term) < term_key(this_term):
            err("term_in_past", f"{term} has already passed (it's {this_term} now)", term=term)
        elif term == this_term and profile.get("in_progress"):
            err("term_in_progress", f"{term} is the current term, and the in-progress courses already fill it; plan "
                f"from {next_term(this_term, False)}", term=term)
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
            if "all_of" in g or "one_of" in g:
                err("bad_slot", f"{g['id']} lists exact courses; plan them instead of a slot", term=term)
                continue
            slots.append(s | {"term": term})
            term_units += s.get("units", 0)

        ctx = {"done": done, "same_term": set(codes), "grades": grades, "units": units, "profile": profile, "gpa": gpa,
               "ge_done": ge_done_areas(profile, university), "catalog": catalog,
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

        summer, winter = term.endswith("summer"), term.endswith("winter")
        regular = not (summer or winter)  # spring or fall: the F-1 minimum and the normal load apply
        ws = most.get("winter_session", {})
        cap = fixed if fixed is not None else sem.get("max_units", load["normal_max"])
        if term_units > cap:
            err("over_cap", f"{term}: {term_units:g} units is over {'max_units_per_term' if fixed is not None else 'max_units'} "
                f"({cap:g})", term=term)
        if winter and term_units > ws.get("units", 0):
            err("over_max_units", f"{term}: {term_units:g} units is over the {ws.get('units', 0):g}-unit Winter Session maximum "
                f"({ws.get('source', 'no Winter Session in this Bulletin')})", term=term)
        ceiling = most["summer" if summer else "fall_spring"]
        if not winter and term_units > ceiling:
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
        if regular and term_units < f1_min:
            why = (f"{term}: {term_units:g} units; F-1 visa students must carry at least {f1_min:g} units every spring "
                   f"and fall ({load['source']})")
            if term == last_term and rcl:
                warnings.append(why + f". As the last term it's {rcl['reduced_load']}: {rcl['apply']} "
                                f"({rcl['source']}). Not for {rcl['not_for']}, so don't add courses only to reach "
                                f"{f1_min:g}")
                advise.append(("international", f"{term}: request a final-semester Reduced Course Load before the "
                                                "add/drop deadline"))
            elif term == last_term:
                warnings.append(why + ". This is the plan's last term: ask the international office before planning "
                                "a lighter final term")
                advise.append(("international", why + "; ask whether a lighter final term is allowed"))
            else:
                err("below_f1_minimum", why, term=term)
        elif regular and 0 < term_units < load["normal_min"]:
            warnings.append(f"{term}: {term_units:g} units is below the normal {load['normal_min']:g}-{load['normal_max']:g} "
                            f"load, so it's part-time; F-1 visa students need at least {load['f1_min']['undergraduate']:g} "
                            f"in spring and fall, and it can matter for financial aid ({load['source']})")
        online = [c for c in codes if c in catalog and term[5:] in (catalog[c].get("offered") or {}).get("online_only", ())]
        if f1_min and rcl and online and regular and term != last_term:  # the last term has the Reduced Course Load
            counted = term_units - max(0, sum(catalog[c]["units_min"] for c in online) - rcl["online_units_count"])
            if counted < f1_min <= term_units:
                warnings.append(f"{term}: {', '.join(online)} ran only fully online the last time they ran in {term[5:]}; "
                                f"only {rcl['online_units_count']:g} units of online classes count for F-1, so this term "
                                f"counts as {counted:g} of the {f1_min:g} if they stay online. Look for in-person or "
                                f"hybrid sections in Class Search, or swap one ({rcl['source']})")
        normal, road = load["summer_normal" if summer else "normal_max"], sem.get("roadmap")
        if regular and road and normal < term_units <= road["units"]:  # D24: the roadmap's own load, not an overload
            warnings.append(f"{term}: {term_units:g} units, above the normal {normal:g}, as on the Bulletin roadmap "
                            f"({road['source']})")
        elif not winter and term_units > normal:
            warnings.append(f"{term}: {term_units:g} units is above the normal load of {normal:g} ({load['source']}); "
                            "see an advisor before planning an overload")
            advise.append(("major_advisor", f"{term}: {term_units:g} units is above the normal load of {normal:g} "
                           f"({load['source']})"))
        if summer and not profile.get("include_summer", False):
            warnings.append(f"{term}: summer term planned but include_summer is false")
        if winter and not profile.get("include_winter", False):
            warnings.append(f"{term}: Winter Session term planned but include_winter is false")
        terms_out.append({"term": term, "units": term_units, "units_before": units})
        planned += [{"code": c, "grade": ASSUMED, "term": term} for c in codes if c in catalog]
        done = done | {c for c in codes if c in catalog}
        for c in codes:  # a planned retake replaces the old grade for later prereqs
            grades.pop(c, None)
        slot_areas |= {a for x in term_slots for a in slot_ge_areas(x, groups)}
        units += term_units

    if f1_min and rcl:
        warnings.append(f"F-1: a fully online class counts for only {rcl['online_units_count']:g} units toward the "
                        f"{f1_min:g}-unit minimum each spring and fall, so pick in-person or hybrid sections "
                        f"({rcl['source']})")
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
    # `after` (§6.2): a group's courses in a later term than every planned course of the groups it names (KIN ITEP's
    # credential courses after its prerequisites, core and concentration, p.725)
    when = {x["code"]: x["term"] for x in planned}
    for g in (g for g in program["groups"] if "after" in g):
        for c in (c for c in exact_courses(g) if c in when):
            late = [d for a in g["after"] for d in exact_courses(groups[a]) if term_key(when.get(d, "0000-spring")) >= term_key(when[c])]
            if late:
                err("order", f"{c} in {when[c]} comes before {', '.join(late)} finish: {g['title']} follows "
                    f"{', '.join(groups[a].get('title', a) for a in g['after'])} ({g['source']})", term=when[c], course=c)

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
        if g["status"] == "unparsed":  # can't be checked, so it neither passes nor fails the plan
            warnings.append(f"{g['title']}: not checked, GatorPath can't read this requirement; the Bulletin says "
                            f"\"{g['quote']}\" ({g['source']})")
            continue
        if "check" in g:  # a rule over other groups' courses (§6.2): grades a plan doesn't choose, units its slots may
            if g["check"] in GRADE_CHECKS:
                if g["status"] == "remaining":
                    warnings.append(f"{g['title']}: not met by the grades so far, and a plan can't change them; see an "
                                    f"advisor ({g['source']})")
                continue
            if any(i in slot_count for i in g["across"]):
                warnings.append(f"{g['title']}: depends on which courses fill the slots ({g['source']})")
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
        mins = [f"{g['title']}: at least {g['min_units_from']['units']} units must be {described(g['min_units_from'])}"
                for g in program["groups"] if "min_units_from" in g and "across" not in g]  # a choice's, not a check's
        warnings.append(f"{len(slots)} slot(s) still to fill; pick each from list_eligible_electives for its group"
                        + (f" ({'; '.join(mins)})" if mins else ""))

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


def next_term(term: str, summer: bool, winter: bool = False) -> str:
    """The next planned term: spring and fall always, summer and Winter Session only when they're planned."""
    y, i = term_key(term)
    seasons = list(SEASONS)
    while True:
        i += 1
        if i == len(seasons):
            y, i = y + 1, 0
        if seasons[i] in ("spring", "fall") or (seasons[i] == "summer" and summer) or (seasons[i] == "winter" and winter):
            return f"{y}-{seasons[i]}"


def area_groups(label: str, university: dict) -> list[str]:
    """The university groups a roadmap area label stands for: "1" -> 1A/1B/1C, "5UD/2UD" -> both, "USH/USG/CSLG"."""
    labels = label.split("/")
    return [g["id"] for g in university["groups"] if any(a == l or (len(l) == 1 and a[0] == l and len(a) == 2)
                                                         for a in ge_areas(g) for l in labels)]


# Variants the planner reads (pick_variant): first-time by QR pathway (or one for every first-time student), and the ADT.
VARIANTS = {"qr-1-2": "1/2", "qr-3-4": "3/4", "first-time": None, "adt": None}
ROADMAP_KEYS = {"program", "catalog_year", "verified", "verified_by", "variants", "drafted_by"}
SLOTS = {"GE", "ai", "major", "senior_elective", "sfss_or_elective", "elective"}


def check_roadmap(roadmap: dict, program: dict, university: dict, catalog: dict, pages: set[int] | None = None,
                  source: str | None = None) -> list[str]:
    """What a person must fix before a roadmap file is used (§6.2 "AI-drafted rules"): variants the planner doesn't
    read, items it can't place (unknown slot, GE label or major group, a code not in the catalog or not in the
    `source` text), semesters that don't add up to their printed units, pages outside `pages`, roadmap pages no variant
    covers, and a first-time roadmap missing a required course. [] when it's clean."""
    from gatorpath.engine.rules import PAGE, squashed
    out = [f"unknown key {k!r}" for k in roadmap if k not in ROADMAP_KEYS]
    choose = {g["id"] for g in program["groups"] if "from" in g or "one_of" in g}  # a one_of: its course goes there
    unparsed = {g["id"] for g in program["groups"] if g.get("unparsed")}
    text = squashed(source or "")

    def printed(code: str) -> bool:  # as itself or in a cross-listing: "MUS/TH A 221" has MUS 221 and TH A 221
        subj, num = (squashed(x) for x in code.rsplit(" ", 1))
        return bool(re.search(rf"{re.escape(subj)}(?:/[a-z]+)*{re.escape(num)}", text))

    required = [c for g in program["groups"] for c in g.get("all_of", [])]
    cited = lambda text: {n for m in PAGE.findall(str(text)) for n in range(int(m[0]), int(m[1] or m[0]) + 1)}
    covered: set[int] = set()

    def bad(where: str, x) -> list[str]:
        if isinstance(x, str):
            return [f"{where}: {x} is not in the {program['catalog_year']} catalog"] if x not in catalog else \
                [f"{where}: {x} isn't in the roadmap text"] if source is not None and not printed(x) else []
        if not isinstance(x, dict):
            return [f"{where}: {x!r} isn't a course code or a slot"]
        if "one_of" in x:
            return [p for o in x["one_of"] for p in bad(where, o)]
        if x.get("slot") not in SLOTS:
            return [f"{where}: unknown slot {x.get('slot')!r} (one of {', '.join(sorted(SLOTS))})"]
        if x["slot"] in ("GE", "ai") and not area_groups(str(x.get("area", "")), university):
            return [f"{where}: area {x.get('area')!r} matches no GE or American Institutions group"]
        if x["slot"] == "major" and x.get("group") in unparsed:
            return [f"{where}: group {x['group']!r} is unparsed in the program rules: write it there first"]
        if x["slot"] == "major" and x.get("group") not in choose:
            return [f"{where}: group {x.get('group')!r} isn't a choose or Select One group of {program['program']}"]
        return []

    for key, v in roadmap.get("variants", {}).items():
        if key not in VARIANTS:
            out.append(f"{key}: the planner reads only the variants {', '.join(VARIANTS)}")
        elif v.get("qr_pathway") != VARIANTS[key]:
            out.append(f"{key}: qr_pathway should be {VARIANTS[key]!r}")
        codes = set()
        for i, sem in enumerate(v.get("semesters", []), 1):
            where = f"{key} semester {i}"
            for x in sem.get("items", []):
                out += bad(where, x)
                codes |= {o for o in (x.get("one_of", []) if isinstance(x, dict) else [x]) if isinstance(o, str)}
            # A variable-unit course ("AIS 694 Community Service Learning", 1-3) may be printed at more than its minimum,
            # as check_program allows for a program total.
            # ponytail: the plan still counts its minimum; carry the printed units on the item if a plan's load matters.
            add = lambda end: sum(catalog[x].get(end, catalog[x]["units_min"]) if isinstance(x, str) else x.get("units", 0)
                                  for x in sem.get("items", []) if not isinstance(x, str) or x in catalog)
            units, most = add("units_min"), add("units_max")
            if not units <= (sem.get("units") or 0) <= most:
                out.append(f"{where}: the items add up to {units:g}" + (f" ({most:g} with variable-unit courses at their "
                           "most)" if most != units else "") + f", units says {sem.get('units')}")
            if not cited(sem.get("source")):
                out.append(f"{where}: source must cite a page like \"p.2132\"")
            covered |= cited(sem.get("source"))
        if sum(s.get("units", 0) for s in v.get("semesters", [])) != v.get("total_units"):
            out.append(f"{key}: the semesters add up to {sum(s.get('units', 0) for s in v.get('semesters', [])):g}, "
                       f"total_units says {v.get('total_units')}")
        if key != "adt" and (missing := [c for c in required if c not in codes]):
            out.append(f"{key}: required but not on this roadmap: {', '.join(missing)}")
        covered |= cited(v.get("source"))
    if pages and (outside := sorted(covered - pages)):
        out.append(f"source pages {', '.join(map(str, outside))} are outside the roadmap pages ({min(pages)}-{max(pages)})")
    if pages and (left := sorted(pages - covered)):
        out.append(f"roadmap pages {', '.join(map(str, left))} aren't in any variant: a roadmap the planner doesn't read "
                   "(a 5-year or 2-year one)? A person checks nothing is lost")
    return out


def described(f: dict) -> str:
    """A min_units_from filter in words: "CSC", "upper-division SOC", "BIOL at SF State"."""
    level = "/".join(map(str, f["level"])) if isinstance(f.get("level"), list) else f.get("level")
    words = [{"lower": "lower-division", "upper": "upper-division"}.get(str(level), f"{level}-level" if level else ""),
             f.get("subject", "" if "list" in f else "courses"), " or ".join(f.get("list", [])),
             "at SF State" if f.get("sf_state") else ""]
    return " ".join(w for w in words if w)


def approval_only(g: dict) -> bool:
    """A group only an advisor's approval fills (§6.2): `approval` text and no list or filter of courses. With a printed
    list too ("Other appropriate courses may be selected with prior written consent of an advisor"), the list's courses
    are the options and the approval covers the rest."""
    fs = g.get("from", [])
    return bool(g.get("approval")) and all("approved" in f for f in (fs if isinstance(fs, list) else [fs]))


def pick_variant(profile: dict, roadmap: dict) -> str | None:
    if profile.get("adt") and "adt" in roadmap["variants"]:
        return "adt"
    qr = profile.get("qr_pathway")
    # A first-time roadmap without a qr_pathway (2024-25 has one, p.1947) fits every first-time student
    return next((k for k, v in roadmap["variants"].items() if k != "adt"
                 and (v.get("qr_pathway") is None or qr and v["qr_pathway"] == str(qr))), None)


def first_term(profile: dict) -> str | None:
    now = profile.get("current_term")  # set by the server from today's date
    after = (next_term(now, False, profile.get("include_winter", False))  # Winter Session can follow the fall underway
             if profile.get("in_progress") and TERM.fullmatch(str(now or "")) else None)
    later = lambda t: after if after and t and TERM.fullmatch(str(t)) and term_key(t) < term_key(after) else t
    if profile.get("start_term"):  # the in-progress courses fill the current term: never plan on top of them
        return later(profile["start_term"])
    terms = [r["term"] for r in profile.get("completed", []) if TERM.fullmatch(str(r.get("term", "")))]
    if not terms:
        return after
    last = max(terms, key=term_key)
    if profile.get("in_progress"):  # this term's courses: the next spring/fall, not a summer the student may not plan
        last = next_term(last, False)  # ponytail: in progress in a summer term needs start_term
    return later(next_term(last, profile.get("include_summer", False), profile.get("include_winter", False)))


def terms_through(start: str, end: str, summer: bool, winter: bool = False) -> int:
    """How many terms from start to end, inclusive (summers and winters only when they're planned)."""
    n, t = 0, start
    while term_key(t) <= term_key(end) and n < 40:
        n += 1
        t = next_term(t, summer, winter)
    return n


def chunks(units: float, size: float = 3) -> list[float]:
    out = [size] * int(units // size)
    return out + [units - size * len(out)] if units % size else out


def build_plan(profile: dict, program: dict, university: dict, roadmap: dict, catalog: dict, prereqs: dict) -> dict:
    """Deterministic baseline plan (ARCHITECTURE §8): roadmap semester first, then required courses by critical path,
    then slots. Passes check_plan."""
    summer, winter = profile.get("include_summer", False), profile.get("include_winter", False)
    seasons = ("spring", "summer", "fall") if summer else ("spring", "fall")  # a course waits only for these
    winter_max = university["max_units"].get("winter_session", {}).get("units", 0)
    load, levels = university["academic_load"], university["class_level"]
    fixed = profile.get("max_units_per_term")  # the student's cap overrides the roadmap's loads (D24)
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
    # D24: the roadmap's loads are the default. A spring/fall term takes the printed units of the roadmap semester the
    # student's units have reached (the nearest cumulative boundary, so a 62-unit transfer starts at semester 5; on the
    # ADT roadmap, which starts at transfer, SF State units), the last semester's past the end, at most the
    # fall/spring maximum. The student's max_units_per_term overrides.
    road_sems = roadmap["variants"][ref]["semesters"]
    ends = [sum(x["units"] for x in road_sems[:k]) for k in range(len(road_sems) + 1)]  # 0, 16, 32, …
    away = status["totals"]["units"]["value"] - status["totals"]["residence_units"]["value"] if ref == "adt" else 0

    def road_at(units: float) -> int:
        """The roadmap semester (from 0) the student's units have reached: the nearest end of one, the last past it."""
        return min(min(range(len(ends)), key=lambda k: (abs(ends[k] - (units - away)), -k)), len(road_sems) - 1)

    def road_load(units: float) -> dict | None:
        if not road_sems:
            return None
        sem = road_sems[road_at(units)]
        return {"units": min(sem["units"], university["max_units"]["fall_spring"]), "source": sem["source"]}

    def cap_for(term: str, cap: float | None, units: float) -> float:
        """A term's unit cap with `units` earned before it: `cap` when one is set (the student's, or the normal 15 for
        the lighter plan), else the roadmap's load. Summer and Winter Session keep their own limits."""
        if term.endswith("summer") or term.endswith("winter"):
            return min(math.inf if cap is None else cap, load["summer_normal"] if term.endswith("summer") else winter_max)
        if cap is not None:
            return cap
        # F-1 students carry at least 12 every spring and fall (p.2390): a lighter roadmap semester doesn't lower that
        return max((road_load(units) or {"units": load["normal_max"]})["units"],
                   load["f1_min"]["undergraduate"] if profile.get("f1") else 0)
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
    if profile.get("start_term") and start != profile["start_term"]:
        warnings.append(f"start_term {profile['start_term']} isn't after the current term ({profile.get('current_term')}), "
                        f"which the in-progress courses fill; the plan starts in {start}")
    required = [c for c in required if c not in stuck]
    met = have | set(profile.get("dpr_met", ()))

    # A prereq nothing in the plan or roadmap meets is a course to add: PHYS 330 needs MATH 376, WGS 300GW one of WGS
    # 200/210/220/280. One per "one of" (the fewest units, then first printed), all of an "all", and their own prereqs.
    def missing(e: dict | None, planned: set) -> list[str]:
        if not e:
            return []
        if "all" in e:
            return [c for x in e["all"] for c in missing(x, planned)]
        if "any" in e:
            if any(not missing(x, planned) for x in e["any"]):  # a branch already met (or not a course: checked later)
                return []
            options = sorted((x for x in e["any"] if x.get("course") in catalog),
                             key=lambda x: (catalog[x["course"]]["units_min"], e["any"].index(x)))
            return missing(options[0], planned) if options else []
        c = e.get("course")
        return [c] if c and c not in planned and c in catalog and "max_grade" not in e else []

    def added(courses: list[str], planned: set) -> list[str]:
        """What `courses` bring into a plan of `planned`: their prereqs nothing in it meets, and those prereqs' own."""
        planned, queue, out = planned | set(courses), list(courses), []
        while queue:
            for d in missing(prereqs.get(queue.pop(), {}).get("expr"), planned):
                if d not in planned:
                    planned.add(d)
                    out.append(d)
                    queue.append(d)
        return out

    # A "Select One" (one_of) plans the audit's option, by its order (the most done, no attempt that didn't count, no
    # course another group plans) but with the prereqs each option adds in its units (CHEM 349 needs CHEM 130, already
    # planned; CHEM 340 needs CHEM 233 and CHEM 235, p.1796), among the options that leave every planned course ready:
    # not a prereq nothing in the plan or roadmap meets (MATH 400 needs CSC 215 or MATH 209, not CSC 309), nor one the
    # student can't meet (another placement, graduate standing).
    later = {"same_term": set(), "grades": {}, "profile": profile, "gpa": profile.get("gpa"),
             "ge_done": ge_done_areas(profile, university), "slot_areas": {a for g in university["groups"] for a in ge_areas(g)},
             "catalog": catalog, "program": program, "class_level": levels, "units": university["totals"]["min_units"]}

    def reachable(left: list[str], instead: list[str]) -> bool:
        plan = set(required) - set(instead) | set(left)
        plan |= set(added(list(plan), met | plan | set(order)))  # with the prereqs the plan will add, which must be ready too
        return all(evaluate(prereqs.get(c, {}).get("expr"), later | {"done": met | plan | set(order)})[0] != NO for c in plan)

    for g in status["groups"]:
        if "options" in g and g["remaining"]:
            rest = [c for c in required if c not in g["remaining"]]
            others = met | set(rest) | set(added(rest, met))
            cost = lambda o: sum(catalog[c]["units_min"] for c in o["left"] + added(o["left"], others) if c in catalog)
            ok = [o for o in g["options"] if o["left"] and reachable(o["left"], g["remaining"])]
            order_of = lambda o: (len(o["left"]) - len(o["courses"]), any(c in best for c in o["left"]),
                                  any(c in rest for c in o["left"]), cost(o), o["left"] != g["remaining"])
            pick = min(ok, key=order_of)["left"] if ok else g["remaining"]
            if pick != g["remaining"]:
                why = "which leaves a prereq in this plan unmet" if not reachable(g["remaining"], g["remaining"]) else \
                    f"fewer units with the prereqs each adds ({cost({'left': pick}):g}, not {cost({'left': g['remaining']}):g})"
                required = rest + [c for c in pick if c in catalog]
                warnings.append(f"{g['title']}: planned {', '.join(pick)}, not {', '.join(g['remaining'])}, {why} "
                                f"({g['source']})")

    def still_needed(e: dict | None) -> list[str]:
        """Courses a prereq tree still needs: a chain stops at what's done or met, and "one of" stops at a done one."""
        if not e:
            return []
        if "all" in e or "any" in e:
            parts = e.get("all") or e["any"]
            if "any" in e and any(x.get("course") in met for x in parts):
                return []
            return [c for x in parts for c in still_needed(x)]
        return [e["course"]] if "course" in e and e["course"] not in met and "max_grade" not in e else []

    closure: set[str] = set()  # courses still needed below a required one
    stack = list(required)
    while stack:
        for d in still_needed(prereqs.get(stack.pop(), {}).get("expr")):
            if d not in closure:
                closure.add(d)
                stack.append(d)
    todo = required + ([c for c in order if c in closure and c not in have and c not in required and c in catalog]
                       if variant else [])
    todo += added(todo, met)

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
    # `after` (§6.2): {course: the planned courses of the groups its group follows}
    mine = {g["id"]: g for g in program["groups"]}
    follows = {c: {d for a in g["after"] for d in exact_courses(mine[a]) if d in todo}
             for g in program["groups"] if "after" in g for c in exact_courses(g) if c in todo}

    # Slots for what the courses leave open, plus free electives up to the unit totals.
    sim = base | {"completed": base["completed"] + [{"code": c, "grade": ASSUMED} for c in todo]}
    after = audit(sim, program, university, catalog)
    slots: list[dict] = []
    groups = {g["id"]: g for g in program["groups"] + university["groups"]}
    for g in after["groups"]:
        if g["status"] in ("satisfied", "waived") or "check" in g:  # a check group reads other groups' courses: no slot
            continue
        if "subjects" in g:  # GE Area 4 "in at least two different disciplines"
            # A rule on which subjects the Area 4 courses come from; an extra course only once they're all done.
            extra = all(x["status"] in ("satisfied", "waived") for x in after["groups"] if x["id"] in groups[g["id"]]["across"])
            slots.append({"slot": g["id"], "units": 3 if extra else 0, "_kind": "ge" if extra else "tag",
                          "note": f"{'a course' if extra else 'pick the courses'} for {', '.join(groups[g['id']]['across'])} "
                                  f"from at least two subjects{' other than ' + ', '.join(g['subjects']) if g['subjects'] else ''} "
                                  f"({g['source']})"})
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
    # as check_plan counts them: a major slot adds upper-division units only when its options all are (not "Select One
    # lower-division course")
    ud_slot_units = sum(s["units"] for s in slots if s["_kind"] == "ud_ge" or s["_kind"] == "major" and upper_only(groups[s["slot"]]))
    free = max(0, t["units"]["needed"] - t["units"]["value"] - slot_units)
    ud_short = max(0, t["upper_division_units"]["needed"] - t["upper_division_units"]["value"] - ud_slot_units)
    for u in chunks(free):
        upper = ud_short > 0
        ud_short -= u if upper else 0
        slots.append({"slot": "elective", "units": u, "_kind": "elective"} | ({"upper_division": True} if upper else {}))

    # A major choose-slot (senior electives) goes in a term once enough of its real options are ready then: prereqs met
    # by earlier terms and offered that season. Options already in the plan or done don't count.
    from gatorpath.engine.rules import matches as _matches
    choice_options = {g["id"]: [c for c in catalog if c not in have and c not in todo and any(
        _matches(f, c, catalog[c]) for f in (g["from"] if isinstance(g["from"], list) else [g["from"]]))]
        for g in program["groups"] if "from" in g}

    grades0 = known_grades(profile.get("completed", []), profile.get("in_progress", []))
    units0 = status["totals"]["units"]["value"]
    gpa = profile.get("gpa", status["totals"]["gpa_sf_state"]["value"])
    slots0 = slots

    # The Bulletin roadmap as the foundation (its GE areas by semester, e.g. "GE Area 1A" in term 2): a roadmap label
    # maps to the university groups taking that GE area ("1" -> 1A/1B/1C, preferring areas the roadmap doesn't name
    # elsewhere; "5UD/2UD" -> the group taking either), or an American Institutions / SF State Studies designation.
    # A roadmap "Select One" ({one_of: [...]}) is its first option still needed: a course to do, or a slot (§6.2). A
    # major slot naming a one_of group ("Select One (Major Core)") is that group's courses.
    pick_one = lambda i: next((o for o in i["one_of"] if not isinstance(o, str) or o in todo), None) \
        if isinstance(i, dict) and "one_of" in i else i
    as_one_of = lambda i: {"one_of": [c for o in groups[i["group"]]["one_of"] for c in o], "units": i.get("units")} \
        if isinstance(i, dict) and i.get("slot") == "major" and "one_of" in groups.get(i.get("group"), {}) else i
    road = [sem | {"items": [x for x in (pick_one(as_one_of(i)) for i in sem["items"]) if x is not None]}
            for sem in roadmap["variants"][ref]["semesters"]]
    named = {str(i.get("area")) for sem in road for i in sem["items"] if isinstance(i, dict)}
    printed_in: dict[str, int] = {}  # each roadmap course's semester (a Select One's: the option planned)
    for k, sem in enumerate(road):
        for i in sem["items"]:
            if isinstance(i, str):
                printed_in.setdefault(i, k)

    def groups_for(label: str) -> list[str]:
        return sorted(area_groups(label, university), key=lambda i: any(a in named for a in ge_areas(groups[i])))

    def take(item: dict, pool: list[dict]) -> list[dict]:
        """The open slots a roadmap item stands for (removed from `pool` by the caller once placed)."""
        free = lambda u: [x for x in pool if x["_kind"] == "elective"][:max(1, math.ceil(u / 3))] if u else []
        if item["slot"] == "GE":
            ids = groups_for(str(item["area"]))
            out = [x for i in ids for x in pool if x["slot"] == i][:max(1, item["units"] // 3)]
            if str(item["area"]) == "4":  # footnote 2: one of the lower-division Area 4 courses meets USH
                out += [x for x in pool if x["_kind"] == "tag" and x["slot"] in groups_for("USH")][:1]
            return out
        if item["slot"] in ("senior_elective", "major"):  # `major` names its choose-group; CS's senior_elective takes any
            return [x for x in pool if x["_kind"] == "major" and x["slot"] == item.get("group", x["slot"])][:item.get("count", 1)]
        if item["slot"] == "ai":
            tags = [x for x in pool if x["_kind"] == "tag" and x["slot"] in groups_for(str(item["area"]))]
            return tags + free(item["units"]) if tags else []
        if item["slot"] == "sfss_or_elective":
            return [x for x in pool if x["_kind"] == "tag" and x["slot"].startswith("sfss_")] + free(item["units"])
        return free(item.get("units", 3))

    def schedule(queue: list[list], cap: float | None) -> tuple[list, dict, list]:
        """Term by term from `start`: a term first takes its roadmap semester's items (still needed and ready; the
        rest carry to the next term), then the greedy fills what's left under its cap (cap_for), critical path first."""
        slots = [dict(x) for x in slots0]
        done, grades, units = set(have), dict(grades0), units0
        left = sorted(todo, key=rank_of)
        first_ok: dict[str, str] = {}  # the first term a course could have gone in
        waited: set[str] = set()  # D28: waited for the roadmap semester
        semesters, notes, term, slot_areas, carry, queue = [], [], start, set(), [], list(queue)
        regular = 0  # spring/fall terms planned: the roadmap semesters gone by (D28)
        for _ in range(20):
            if not left and not slots:
                break
            if term.endswith("summer") and not summer or term.endswith("winter") and not winter:
                term = next_term(term, summer, winter)
                continue
            # ponytail: a Winter Session term takes only GE, American Institutions and free-elective slots: Class Search
            # history has no winter terms, so which major courses run then is unknown. Upgrade: scrape the winter schedule.
            in_winter = term.endswith("winter")
            limit = cap_for(term, cap, units)
            on_road = road_load(units) if term[5:] in ("spring", "fall") else None
            limits = {"max_units": limit} | ({"roadmap": on_road} if on_road else {})
            placed: list[str] = []
            term_slots: list[dict] = []
            used = 0.0
            ctx = {"done": done, "grades": grades, "units": units, "profile": profile, "gpa": gpa,
                   "ge_done": ge_done_areas(profile, university), "catalog": catalog,
                   "program": program, "class_level": levels, "slot_areas": slot_areas}

            def ok(c: str, same: set) -> bool:
                if follows.get(c, set()) - done:  # `after`: those groups' courses in an earlier term first
                    return False
                state, _ = evaluate(prereqs.get(c, {}).get("expr"), ctx | {"same_term": same})
                # An unverifiable branch ("or equivalent", high-school courses) doesn't let a course jump ahead of a
                # prereq that's still in the plan: wait for it, in an earlier term (or this one, for corequisites).
                waiting = (hard[c] - done) | (needs[c] - hard[c] - done - same)
                # D28: nor more than a semester before its roadmap semester (AA S 696, "24 upper-division units in AA S
                # courses": semester 7, so term 6, not 1). The student's semester: where their units start them, one more
                # per spring/fall term, or their units' when further (summer terms)
                early = printed_in.get(c, -1) > max(road_at(units), road_at(units0) + regular) + 1
                if state == UNVERIFIED and not waiting and early:
                    waited.add(c)
                return (state == OK or (state == UNVERIFIED and not waiting and not early)) and season_ok(c, term, catalog, seasons)[0]

            def ready_options(gid: str) -> float:
                if approval_only(groups[gid]):  # the advisor's pick: no options to check, so ready at the standing
                    return math.inf
                if not any("course" in leaf for c in choice_options.get(gid, ())
                           for leaf in leaves(prereqs.get(c, {}).get("expr"))):
                    return math.inf  # no option waits on a course (ensembles: "Audition."): ready at the standing
                return sum(1 for c in choice_options.get(gid, ())
                           if evaluate(prereqs.get(c, {}).get("expr"), ctx | {"same_term": set()})[0] == OK
                           and season_ok(c, term, catalog, seasons)[0])

            ready_count: dict[str, int] = {}
            ud = university.get("upper_division_ge", {})
            ud_ok = units >= ud.get("recommended_after_units", levels["upper"]) and ud_ge_ready(ctx | {"same_term": set()}, university)[0]

            def allowed(x: dict) -> bool:
                if x["_kind"] == "major":
                    if x["slot"] not in ready_count:
                        ready_count[x["slot"]] = ready_options(x["slot"])
                    taken_now = sum(1 for y in term_slots if y["slot"] == x["slot"])
                    return units >= levels["upper"] and ready_count[x["slot"]] > taken_now
                return not ((x["_kind"] == "ud_ge" and not ud_ok)
                            or (x["_kind"] == "elective" and x.get("upper_division") and units < levels["upper"]))

            # Roadmap semester first (skipping semesters with nothing left); what can't go now carries over.
            while not in_winter and queue and not any((i in left) if isinstance(i, str) else take(i, slots) for i in queue[0]):
                queue.pop(0)
            if in_winter:  # roadmap semesters are fall/spring: what carries over waits for the next one
                pins = []
            else:
                pins, carry = carry + (queue.pop(0) if queue else []), []
            for item in pins:
                if isinstance(item, str):
                    if item not in left or item in placed:
                        continue
                    # corequisites go together or not at all (PHYS 220 with PHYS 222)
                    bundle = [item] + [d for d in needs[item] if d in left and d not in placed
                                       and item in needs.get(d, ()) and d not in hard[item]]
                    u = sum(catalog[b]["units_min"] for b in bundle)
                    if all(ok(b, set(placed) | set(bundle)) for b in bundle) and used + u <= limit:
                        placed += bundle
                        used += u
                    else:
                        carry += [b for b in bundle if b not in carry]
                    continue
                picked = take(item, slots)
                if not picked:
                    continue
                if all(allowed(x) for x in picked) and used + sum(x["units"] for x in picked) <= limit:
                    for x in picked:
                        slots.remove(x)
                    term_slots += picked
                    used += sum(x["units"] for x in picked)
                else:
                    carry.append(item)
            for c in placed:
                first_ok.setdefault(c, term)

            changed = not in_winter
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
            for kind in ("ge", "ud_ge", "elective") if in_winter else ("ge", "ud_ge", "major", "elective"):  # tags wait
                for x in [x for x in slots if x["_kind"] == kind]:
                    if allowed(x) and used + x["units"] <= limit:
                        term_slots.append(x)
                        slots.remove(x)
                        used += x["units"]
                    elif kind == "elective" and allowed(x) and limit - used >= 1:
                        # free units are any course's units: fill the term, keep the rest for later
                        part = x | {"units": float(int(limit - used))}
                        x["units"] -= part["units"]
                        term_slots.append(part)
                        used += part["units"]
            # F-1 (pp.2390, 2393): a spring/fall term with more to come is filled toward the minimum with elective slots
            # that fit (free units split); check_plan flags what still falls short.
            f1_min = load["f1_min"]["undergraduate"] if profile.get("f1") and term[5:] in ("spring", "fall") else 0
            if used < f1_min and (left or slots):
                for x in [x for x in slots if x["_kind"] in ("major", "elective")]:
                    if units >= levels["upper"] or not (x["_kind"] == "major" or x.get("upper_division")):
                        if used < f1_min and used + x["units"] <= limit:
                            term_slots.append(x)
                            slots.remove(x)
                            used += x["units"]
                        elif used < f1_min and x["_kind"] == "elective":  # free units fill to the minimum exactly
                            part = x | {"units": float(min(x["units"], f1_min - used, int(limit - used)))}
                            if part["units"] >= 1:
                                x["units"] -= part["units"]
                                term_slots.append(part)
                                used += part["units"]
            if in_winter and not placed and not any(x["units"] for x in term_slots):  # nothing for winter: skip it
                slots += term_slots
                term = next_term(term, summer, winter)
                continue
            off_season = [c for c in left if not season_ok(c, term, catalog, seasons)[0]]
            if not placed and not any(x["units"] for x in term_slots) and off_season:
                notes.append(f"{term}: nothing left runs in {term[5:]}; {', '.join(off_season)} wait for a term they run in")
                term = next_term(term, summer, winter)
                continue
            if not placed and not any(x["units"] for x in term_slots):
                blocked = {c: evaluate(prereqs.get(c, {}).get("expr"), ctx | {"same_term": set()})[1] for c in left}
                notes.append(f"Stopped at {term}: nothing more can be scheduled. Blocked: "
                             + "; ".join(f"{c} needs {', '.join(w) or 'more units per term'}" for c, w in blocked.items())
                             + ("; slots waiting: " + ", ".join(sorted({x['slot'] for x in slots})) if slots else ""))
                semesters += [{"term": term, "courses": [{k: v for k, v in x.items() if k != "_kind"} for x in term_slots],
                               "units": 0} | limits] if term_slots else []
                break
            if not left and slots and all(x["units"] == 0 for x in slots):
                term_slots += slots  # designation tags never make a term of their own
                slots = []
            free: dict[bool, dict] = {}  # one free-elective slot per term (per upper-division flag)
            for x in [x for x in term_slots if x["slot"] == "elective"]:
                key = bool(x.get("upper_division"))
                free[key] = free[key] | {"units": free[key]["units"] + x["units"]} if key in free else dict(x)
            term_slots = [x for x in term_slots if x["slot"] != "elective"] + list(free.values())
            semesters.append({"term": term, "units": used,
                              "courses": placed + [{k: v for k, v in x.items() if k != "_kind"} for x in term_slots]} | limits)
            done |= set(placed)
            for c in placed:  # a planned retake replaces the old grade
                grades.pop(c, None)
            slot_areas = slot_areas | {a for x in term_slots for a in slot_ge_areas(x, groups)}
            units += used
            regular += term[5:] in ("spring", "fall")
            term = next_term(term, summer, winter)
        return semesters, first_ok, notes, waited

    # Build both and keep the roadmap-led plan unless the plain greedy finishes sooner. Both use the same caps, and each
    # term carries its own (max_units), so the plan passes check_plan as given.
    def plan_at(cap: float | None) -> tuple[list, dict, list, set]:
        semesters, first_ok, notes, waited = schedule([], cap)
        if not summer:
            led = schedule([list(sem["items"]) for sem in road], cap)
            if check_plan(profile, {"semesters": led[0]}, program, university, catalog, prereqs)["valid"] \
                    and len(led[0]) <= len(semesters):
                v = roadmap["variants"][ref]
                return led[0], led[1], led[2] + [f"Laid out on the Bulletin's {v['title']} ({v['source']}): each term "
                                                 "starts from that roadmap semester's courses and GE areas, adjusted for "
                                                 "what's done"], led[3]
        return semesters, first_ok, notes, waited

    semesters, first_ok, notes, waited = plan_at(fixed)
    # D25: the graduation goal sets the load; the roadmap is the normal range. With graduate_by (and no cap of the
    # student's), a roadmap plan that ends after it is rebuilt with every term at the roadmap's heaviest semester, then
    # one unit more at a time up to the fall/spring maximum, until it ends by then. Past that, why_not says why.
    target = profile.get("graduate_by")
    late = lambda sems: not sems or term_key(sems[-1]["term"]) > term_key(str(target))
    fit = None
    tried = fixed is None and road_sems and TERM.fullmatch(str(target or "")) and late(semesters)
    if tried:
        heaviest = min(max(x["units"] for x in road_sems), university["max_units"]["fall_spring"])
        for x in range(int(heaviest), int(university["max_units"]["fall_spring"]) + 1):
            trial = plan_at(x)
            if not late(trial[0]) and check_plan(profile, {"semesters": trial[0]}, program, university, catalog,
                                                 prereqs)["valid"]:
                semesters, first_ok, notes, waited = trial
                fit = {"graduate_by": target, "units_per_term": x,
                       "note": f"to finish by {target}, terms go up to {x:g} units: "
                               + (f"the roadmap's heaviest semester ({heaviest:g})" if x == heaviest else
                                  f"above the roadmap's heaviest semester ({heaviest:g}), an overload above "
                                  f"{load['normal_max']:g} ({load['source']}): see an advisor")}
                break
    most = university["max_units"]["fall_spring"]
    cap_used = fit["units_per_term"] if fit else most if tried else fixed  # a failed fit is judged at the maximum
    # The lighter option (D24): the normal 15 where the roadmap's loads go above it (two 16-unit terms in the
    # first-time roadmaps).
    normal_pace = None
    if fixed is None and not fit and any(s["max_units"] > load["normal_max"] for s in semesters):
        light = plan_at(load["normal_max"])[0]
        if light and check_plan(profile, {"semesters": light}, program, university, catalog, prereqs)["valid"]:
            normal_pace = {"max_units_per_term": load["normal_max"], "terms": len(light),
                           "est_graduation_term": light[-1]["term"],
                           "note": f"the normal load of {load['normal_max']:g} ({load['source']}) instead of the roadmap's "
                                   f"(up to {max(s['max_units'] for s in semesters):g}): {len(light)} terms, done in "
                                   f"{light[-1]['term']}; pass max_units_per_term: {load['normal_max']:g} to plan that way"}
    warnings += notes
    plan = {"semesters": semesters}
    check = check_plan(profile, plan, program, university, catalog, prereqs)
    held = Counter(c if isinstance(c, str) else c["slot"] for c in (semesters[-1]["courses"] if semesters else [])
                   if isinstance(c, str) or c["units"])
    held = ", ".join(f"{n} × {c}" if n > 1 else c for c, n in held.items())
    # A light last term (a 1-unit free elective at 15 per term) can fold into one earlier spring/fall term: the
    # lightest one that passes check_plan with the extra units, latest first. check_plan can't see when a slot's
    # options are ready (senior electives, D19; upper-division standing), so a slot moves no earlier than the first
    # term the plan already gives that slot.
    fold, last, first = None, semesters[-1] if semesters else {"courses": []}, {}
    kind = lambda x: (x["slot"], bool(x.get("upper_division")))
    for i, s in enumerate(semesters):
        for x in (x for x in s["courses"] if isinstance(x, dict)):
            first.setdefault(kind(x), i)
    earliest = max((first[kind(x)] for x in last["courses"] if isinstance(x, dict) and x["units"]), default=0)
    for s in sorted(reversed(semesters[earliest:-1]) if check["valid"] else [], key=lambda s: s["units"]):  # stable: latest first
        units = s["units"] + last["units"]
        if s["term"][5:] not in ("spring", "fall") or units > university["max_units"]["fall_spring"]:
            continue
        moved = [x | {"courses": x["courses"] + last["courses"], "units": units, "max_units": max(x["max_units"], units)}
                 if x is s else x for x in semesters[:-1]]
        if check_plan(profile | ({"max_units_per_term": max(fixed, units)} if fixed is not None else {}),
                      {"semesters": moved}, program, university, catalog, prereqs)["valid"]:
            overload = units > load["normal_max"] and units > s.get("roadmap", {}).get("units", 0)
            fold = {"term": s["term"], "units": units, "terms": len(moved), "est_graduation_term": moved[-1]["term"],
                    "note": f"move {last['term']}'s {held} ({last['units']:g} unit{'s' if last['units'] != 1 else ''}) "
                            f"into {s['term']}: one {units:g}-unit term, done in {moved[-1]['term']}, a term sooner"
                            + (f"; above the normal load of {load['normal_max']:g} ({load['source']}), so see an advisor "
                               "first" if overload else "")
                            + (f". check_plan the moved plan with max_units_per_term: {max(fixed, units):g}"
                               if fixed is not None else f". In the moved plan {s['term']} has max_units: {units:g}")}
            break

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
            if c in waited:
                parts.append(f"GatorPath can't check its prereq, so it stays with the Bulletin roadmap, which has it in "
                             f"semester {printed_in[c] + 1} (at most a term earlier)")
            if not (dependents[c] or coreqs[c] or opens[c]):
                parts.append("no later course in this plan needs it, so it can move if needed")
            if len(path) >= 3:
                parts.append(f"starts a {len(path)}-term chain: {' → '.join(path)}")
            if len(path) >= 2 and all(term_of.get(path[k + 1]) == term_of[path[k]] + 1 for k in range(len(path) - 1)):
                parts.append(f"no slack: delaying it pushes back {path[-1]}")
            if first_ok.get(c, s["term"]) != s["term"]:
                parts.append(f"could have started in {first_ok[c]}; waited for room under {s['max_units']:g} units that term")
            notes[c] = parts[0][0].upper() + "; ".join(parts)[1:]
        s["why"] = notes

    plan_units = sum(s["units"] for s in semesters)
    critical = min(todo, key=rank_of) if todo else None
    kind_of_load = ("max_units_per_term" if fixed is not None else "graduate_by" if fit else "roadmap" if road_sems
                    else "normal")
    by_units, got, t = 0, 0.0, start if start[5:] in ("spring", "fall") else next_term(start, False)
    while got < plan_units and by_units < 40:  # spring/fall terms at their caps
        got, by_units, t = got + cap_for(t, cap_used, units0 + got), by_units + 1, next_term(t, False)
    pace = {"terms": len(semesters), "load": kind_of_load,
            **({"units_per_term": cap_used if cap_used is not None else load["normal_max"]}
               if kind_of_load != "roadmap" else {}), **({"fit": fit} if fit else {}),
            "include_summer": summer, "include_winter": winter, "planned_units": plan_units,
            **({"normal_load": normal_pace} if normal_pace else {}), **({"fold_last_term": fold} if fold else {}),
            "min_terms_by_prereqs": depth[critical] if critical else 0,
            "longest_chain": longest(critical) if critical else [],
            "min_terms_by_units": by_units}
    if target and TERM.fullmatch(str(target)) and semesters:
        available = terms_through(start, target, summer, winter)
        pace |= {"graduate_by": target, "terms_available": available,
                 "on_time": check["valid"] and term_key(semesters[-1]["term"]) <= term_key(target)}
        if not pace["on_time"]:
            why_not = []
            if pace["min_terms_by_prereqs"] > available:
                why_not.append(f"the prereq chain alone needs {pace['min_terms_by_prereqs']} terms "
                               f"({' → '.join(pace['longest_chain'])}); only {available} until {target}")
            if pace["min_terms_by_units"] > available:
                if tried and not fit:
                    why_not.append(f"{plan_units:g} units need {pace['min_terms_by_units']} terms even at {most:g} a "
                                   f"term, the fall/spring maximum ({university['max_units']['source']}); only "
                                   f"{available}: add summers or Winter Session")
                else:
                    at = "the roadmap's loads" if kind_of_load == "roadmap" else f"{pace['units_per_term']:g} per term"
                    why_not.append(f"{plan_units:g} units at {at} needs {pace['min_terms_by_units']} terms; only "
                                   f"{available}: add summers or raise max_units_per_term (above {load['normal_max']:g} "
                                   f"is an overload, {load['source']})")
            if not why_not:
                why_not.append(f"the plan needs {len(semesters)} terms; the last ({semesters[-1]['term']}) holds {held}. "
                               "Senior electives wait for upper-division standing and an option that's ready (its "
                               f"prereqs), and upper-division GE for {levels['upper']} units" + ("" if summer and winter else "; try include_summer or include_winter"))
            pace["why_not"] = why_not
    return {"catalog_year": program["catalog_year"], "variant": variant, **plan,
            "est_graduation_term": semesters[-1]["term"] if semesters and check["valid"] else None, "pace": pace,
            "warnings": warnings + check["warnings"],
            "see_advisor": see_advisor([("substitutions", f"{c}: passed with {best[c]}, which this requirement doesn't "
                                         "accept, and it can't be repeated; ask about a substitution or petition")
                                        for c in stuck]
                                       + [("substitutions", f"{groups[g['id']]['title']}: \"{groups[g['id']]['approval']}\" "
                                                            f"({g['source']}); get the courses approved before taking them")
                                          for g in status["groups"] if approval_only(groups[g["id"]])
                                          and g["status"] not in ("satisfied", "waived")],
                                       program, university, check["see_advisor"]),
            "check": {"valid": check["valid"], "errors": check["errors"]}}


def compare_programs(profile: dict, current: tuple[dict, dict], target: tuple[dict, dict], university: dict,
                     catalog: dict, prereqs: dict) -> dict:
    """What-if for a change of major (ARCHITECTURE §7.3): which of the student's courses count toward each major, what
    the target still needs, and build_plan's length for each at the same load. `current` and `target` are (program
    rules, roadmap); `university` is the student's own catalog year (GE doesn't change with the major)."""
    sides, counts, warnings = {}, {}, []
    for key, (program, roadmap) in (("current", current), ("target", target)):
        p = profile | {"program": program["program"]}
        if key == "target":  # the DPR's substitutions were approved for the current major, not this one
            p = p | {"dpr_met": []}
            if profile.get("dpr_met"):
                warnings.append(f"Substitutions on your DPR ({', '.join(profile['dpr_met'])}) are your current major's; "
                                f"they aren't counted toward {program['title']}: ask its department whether they carry over")
        plan = build_plan(p, program, university, roadmap, catalog, prereqs)
        if "needs_input" in plan or "error" in plan:
            return plan | {"for": key}
        status = audit(p, program, university, catalog)
        major = [g for g in status["groups"] if g["kind"] == "major"]
        done = {c for g in major for c in g["counted"]}
        going = {c for g in major for c in g["in_progress"]}
        units = lambda cs: sum(catalog[c]["units_min"] for c in cs if c in catalog)
        counts[key] = done | going
        sides[key] = {"program": program["program"], "title": program["title"], "catalog_year": program["catalog_year"],
                      "major_units": {"done": units(done), "in_progress": units(going), "needed": program["total_units"]},
                      "terms": len(plan["semesters"]), "est_graduation_term": plan["est_graduation_term"],
                      "plan_valid": plan["check"]["valid"]}
        if key == "target":
            sides[key]["groups"] = [{k: v for k, v in g.items() if k not in ("kind", "eligible")} for g in major]
            warnings += [w for w in status["warnings"] if "doesn't count toward" in w]
            advise = see_advisor([("major_advisor", f"Changing your major to {program['title']}: confirm what counts and "
                                   "the requirements in effect when you change")], program, university, plan["see_advisor"])
    only_current = sorted(counts["current"] - counts["target"])
    return {"catalog_year": sides["target"]["catalog_year"], **sides,
            "courses": {"count_in_both": sorted(counts["current"] & counts["target"]), "only_current": only_current,
                        "only_target": sorted(counts["target"] - counts["current"])},
            "extra_terms": sides["target"]["terms"] - sides["current"]["terms"]
                           if sides["target"]["est_graduation_term"] and sides["current"]["est_graduation_term"] else None,
            "warnings": warnings + ([f"{', '.join(only_current)} still count toward the 120 units (and GE where they carry "
                                     "an area), just not toward the new major"] if only_current else []),
            "see_advisor": advise}


def minimal_covers(need: frozenset, covers: list[frozenset], ways: int = 10, budget: int = 20000) -> list[list]:
    """Sets of covers whose union is `need`, none redundant, fewest first. A greedy cover sets the size; an exact-cover
    search (branch on the requirement with the fewest covers, only over covers that contain it) finds others up to that
    size (with 5 or fewer open, up to one course each). `budget` caps the steps, so 17 open requirements still answer
    at once. Not a proof of the minimum."""
    if not need or not all(any(r in c for c in covers) for r in need):
        return []
    lean = lambda chosen: [x for i, x in enumerate(chosen)  # drop parts the others already cover
                           if frozenset().union(*(c for j, c in enumerate(chosen) if j != i)) != need] or chosen
    chosen, covered = [], frozenset()
    while covered != need:
        c = max(covers, key=lambda c: (len(c - covered), -len(c), sorted(c)))
        chosen.append(c)
        covered |= c
    greedy = lean(chosen)
    while len(lean(greedy)) < len(greedy):
        greedy = lean(greedy)
    count = {r: sum(r in c for c in covers) for r in need}
    size = len(need) if len(need) <= 5 else len(greedy)  # few open: every shape up to one course each
    found, seen, steps = [greedy], {frozenset(greedy)}, 0

    def search(chosen: list, covered: frozenset) -> None:
        nonlocal steps
        steps += 1
        if steps > budget or len(found) >= ways:
            return
        if covered == need:
            key = frozenset(chosen)
            if key not in seen and not any(frozenset().union(*(c for c in chosen if c is not x)) == need for x in chosen):
                seen.add(key)
                found.append(list(chosen))
            return
        if len(chosen) == size:
            return
        r = min(need - covered, key=lambda x: count[x])
        for c in sorted((c for c in covers if r in c), key=lambda c: (-len(c - covered), sorted(c))):
            search(chosen + [c], covered | c)

    search([], frozenset())
    return sorted(found, key=len)


def cover_combinations(profile: dict, program: dict, university: dict, catalog: dict, prereqs: dict,
                       plan: dict | None = None, by_term: str | None = None, examples: int = 4, ways: int = 8) -> dict:
    """Ways to finish the open university requirements that one course can fill (a GE area, an SF State Studies area,
    an American Institutions part): one course covering several, or separate courses, fewest courses first. Each way's
    parts say which requirements one course covers, with example courses (ready first, then recently offered).
    `overlaps` lists the course kinds that cover two or more open requirements (the double-dips to look for)."""
    from gatorpath.engine.rules import matches

    required = [c for g in program["groups"] for c in g.get("all_of", []) if c in catalog]
    in_major = {str(m["area"]) for m in program.get("ge_met", [])}  # "met in the major" (§6.2 ge_met)
    results = {}
    for g in university["groups"]:
        filters = g.get("from", [])
        filters = filters if isinstance(filters, list) else [filters]
        if not filters or any(matches(f, c, catalog[c]) for f in filters for c in required) or in_major & set(ge_areas(g)):
            continue  # the major's own courses cover it (GWAR via CSC 300GW; Civil's GE 1B, p.1939): not the student's pick
        r = eligible_options(profile, g["id"], program, university, catalog, prereqs, plan, by_term, limit=10**6)
        if r.get("error"):
            return r
        left = r.get("units_needed", 0) - r.get("units_done", 0) if "units_needed" in r else r.get("courses_needed", 0)
        # ponytail: a requirement one course can finish (3-4 units, or one course); bigger ones (GE 4's 6 units) stay
        # as plan slots. Upgrade: one token per course needed.
        if r["status"] not in ("satisfied", "waived") and 0 < left <= (4 if "units_needed" in r else 1):
            results[g["id"]] = r
    open_ids = frozenset(results)
    by_cover: dict[frozenset, dict[str, dict]] = {}
    for gid, r in results.items():
        for o in r["options"]:
            cover = frozenset({gid} | (set(o["also_covers"]) & open_ids))
            by_cover.setdefault(cover, {}).setdefault(o["code"], o)
    rank = {"ready": 0, "check": 1, "blocked": 2}
    recent = lambda c: term_key(catalog[c]["offered"]["last"]) if (catalog[c].get("offered") or {}).get("last") else (0, 0)

    def part(cover: frozenset) -> dict:
        best = sorted(by_cover[cover].values(), key=lambda o: (rank[o["readiness"]], tuple(-x for x in recent(o["code"])),
                                                               o["code"]))
        return {"covers": sorted(results[i]["title"] for i in cover), "options": len(by_cover[cover]),
                "examples": [{k: o[k] for k in ("code", "title", "units", "readiness")} for o in best[:examples]]}

    many = len(open_ids) > 5
    examples = 3 if many else examples
    found = minimal_covers(open_ids, list(by_cover), 3 if many else ways)
    overlaps = sorted((c for c in by_cover if len(c) > 1), key=lambda c: (-len(c), -len(by_cover[c]), sorted(c)))
    missing = [results[i]["title"] for i in open_ids if not any(i in c for c in by_cover)]
    warnings = []
    if found:
        warnings.append(f"{len(found[0])} courses can cover these {len(open_ids)} requirements (the fewest found). Any "
                        "way works, and the parts can go in different terms: pick one, put its courses in the plan, "
                        "and check_plan it. `overlaps` lists the courses that count for two or more")
    if missing:
        warnings.append(f"No eligible course found for: {', '.join(missing)}")
    return {"catalog_year": program["catalog_year"], "open": [results[i]["title"] for i in sorted(open_ids)],
            "fewest_courses": len(found[0]) if found else None,
            "ways": [{"courses": len(w), "parts": [part(c) for c in w]} for w in found],
            "overlaps": [part(c) for c in overlaps[:10]], "warnings": warnings}


def eligible_options(profile: dict, group_id: str, program: dict, university: dict, catalog: dict, prereqs: dict,
                     plan: dict | None = None, by_term: str | None = None, limit: int = 25) -> dict:
    """Courses that can fill a choose-group, with readiness at `by_term` and the other open requirements each covers.

    Ranked: ready first, then courses that also cover the most other open requirements (ENVS 401 = 4UD + ESCA + GP),
    then the preferred subject while a `min_units_from` minimum is short (12 CSC units of senior electives).
    """
    from gatorpath.engine.rules import filters_for, matches, subject

    groups = {g["id"]: g for g in program["groups"] + university["groups"]}
    kind = {g["id"]: k for k, rules in (("major", program), ("university", university)) for g in rules["groups"]}
    g = groups.get(group_id)
    if g is None:
        return {"error": "unknown_group", "groups": list(groups)}
    if "distinct_subjects" in g:  # "GE Area 4 in at least two disciplines": the options are its groups', picked across subjects
        parts = [eligible_options(profile, a, program, university, catalog, prereqs, plan, by_term, limit) for a in g["across"]]
        parts = [r for r in parts if "options" in r]
        if not parts:
            return {"error": "not_a_choice", "warnings": [f"{group_id}: none of {', '.join(g['across'])} is open"]}
        return parts[0] | {"group": group_id, "title": g.get("title", group_id), "source": g["source"],
                           "options": [o for r in parts for o in r["options"]][:max(1, limit)],
                           "warnings": [f"{g.get('title', group_id)}: choose the {', '.join(g['across'])} courses from at "
                                        f"least {g['distinct_subjects']} different subjects ({g['source']})"]}
    if "all_of" in g or "from" not in g:
        return {"error": "not_a_choice", "warnings": [f"{group_id} isn't a choose-group; see get_program_requirements"]}
    if approval_only(g):  # no list to pick from (§6.2): the student's advisor approves the courses
        why = f"{g.get('title', group_id)}: \"{g['approval']}\" ({g['source']})"
        return {"catalog_year": program["catalog_year"], "group": group_id, "title": g.get("title", group_id),
                "source": g["source"], "approval": g["approval"], "options": [], "total_options": 0,
                "warnings": [why + ". GatorPath can't list or check these courses: ask the advisor, then pass the approved "
                             f"ones as profile.approved['{group_id}'] so they count"],
                "see_advisor": see_advisor([("substitutions", why)], program, university)}
    filters = filters_for(g, profile)

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
    grades = known_grades(profile.get("completed", []), profile.get("in_progress", []))

    def ctx_at(term: str) -> dict:
        before = [s for s in semesters if term_key(s["term"]) < term_key(term)]
        done = taken - {c for t, c in planned if term_key(t) >= term_key(term)}
        units = base_units + sum(sum(catalog[c]["units_min"] if isinstance(c, str) and c in catalog
                                     else c.get("units", 0) if isinstance(c, dict) else 0 for c in s["courses"])
                                 for s in before)
        return {"done": done, "same_term": {c for t, c in planned if t == term}, "grades": grades, "units": units,
                "profile": profile, "gpa": gpa, "ge_done": ge_done_areas(profile, university),
                "catalog": catalog, "program": program, "class_level": university["class_level"],
                "slot_areas": {a for s in semesters if term_key(s["term"]) < term_key(term)
                               for x in s["courses"] if isinstance(x, dict) for a in slot_ge_areas(x, groups)}}

    ctxs = {t: ctx_at(t) for t in terms}
    target = status[group_id]
    pref = g.get("min_units_from", {})
    pref_short = bool(pref) and target.get("min_units_from", {}).get("done", 0) < pref.get("units", 0)
    used = {i: sum(1 for c in target["counted"] + target["in_progress"] if matches(f, c, catalog[c]))
            for i, f in enumerate(filters)}
    used_units = {i: sum(catalog[c]["units_min"] for c in target["counted"] + target["in_progress"] if matches(f, c, catalog[c]))
                  for i, f in enumerate(filters)}
    options = []
    for code, course in catalog.items():
        if code in taken:
            continue
        hit = [i for i, f in enumerate(filters) if matches(f, code, course) and used[i] < f.get("max_courses", math.inf)
               and used_units[i] + course["units_min"] <= f.get("max_units", math.inf)]
        if not hit:
            continue
        expr = prereqs.get(code, {}).get("expr")
        state, why = evaluate(expr, ctxs[first])
        option = {"code": code, "title": course["title"], "units": course["units_min"], "source_page": course["source_page"],
                  "readiness": {OK: "ready", UNVERIFIED: "check", NO: "blocked"}[state],
                  "also_covers": [i for i in open_groups if not (kind[i] == kind[group_id] == "major")
                                  and any(matches(f, code, course) for f in filters_for(groups[i], profile))],
                  "offered": "unknown"}
        if state != OK:
            option["blocked_by" if state == NO else "cannot_check"] = why
        if not (runs := season_ok(code, first, catalog))[0]:  # not on that term's schedule, or never runs that season
            option["not_offered"] = runs[1]
        if state == NO:
            later = next((t for t in terms[1:] if evaluate(expr, ctxs[t])[0] != NO), None)
            if later:
                option["ready_by"] = later
        if any("max_courses" in filters[i] for i in hit):
            option["note"] = f"at most {min(filters[i]['max_courses'] for i in hit)} course(s) from this part of the list"
        elif any("max_units" in filters[i] for i in hit):
            option["note"] = f"at most {min(filters[i]['max_units'] for i in hit):g} units from this part of the list"
        options.append(option)
    order = {"ready": 0, "check": 1, "blocked": 2}
    options.sort(key=lambda o: ("not_offered" in o, order[o["readiness"]], -len(o["also_covers"]),
                                not (pref_short and matches(pref, o["code"], catalog[o["code"]])), o["code"]))
    need = {k: target[k] for k in ("units_needed", "units_done", "courses_needed", "min_units_from") if k in target}
    return {"catalog_year": program["catalog_year"], "group": group_id, "title": g.get("title", group_id),
            "source": g["source"], "by_term": first, "status": target["status"], **need,
            "options": options[:max(1, limit)], "total_options": len(options),
            "warnings": [f"also_covers lists other open requirements a course would count for (GE, SF State Studies and "
                         f"American Institutions may overlap with each other and the major, p.2352)"]
                        + ([f"{g.get('title', group_id)}: also \"{g['approval']}\" ({g['source']}): pass courses an advisor "
                            f"approves as profile.approved['{group_id}'] so they count"] if g.get("approval") else [])}

