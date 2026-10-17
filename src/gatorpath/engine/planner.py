"""Plans: check_plan (ARCHITECTURE §7.3, the single source of truth for validity). Pure functions, no DB.

A plan is {"semesters": [{"term": "2027-spring", "courses": ["CSC 413", {"slot": "senior_electives", "units": 3}]}]}.
A slot is an unfilled pick for a choose-group, named by its group id; the AI fills it from list_eligible_electives.
`{"slot": "elective", "units": 3, "upper_division": true?}` is free units toward the 120 (the roadmaps' "elective").

Assumptions, reported as a warning on every check:
- in-progress and planned courses are passed with whatever grade their requirements and prereqs ask for;
- in-progress courses finish before the first planned term.
"""

import re

from gatorpath.engine.prereq import leaves, prereq_warnings
from gatorpath.engine.rules import GRADE_POINTS, audit, number, rank

SEASONS = {"spring": 0, "summer": 1, "fall": 2}
TERM = re.compile(r"(\d{4})-(spring|summer|fall)")
ASSUMED = "A"  # stand-in grade for planned courses when simulating the audit; statuses only, never a GPA
OK, NO, UNVERIFIED = "ok", "no", "unverified"
UNVERIFIABLE = {"permission", "equivalent", "requirement", "high_school", "unknown"}


def term_key(term: str) -> tuple[int, int]:
    y, s = TERM.fullmatch(term).groups()
    return int(y), SEASONS[s]


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
            return all(number(c) >= 300 for c in f["list"])
        return int(str(f.get("level", "0")).rstrip("+")) >= 300

    return bool(filters) and all(map(up, filters))


def slot_ge_areas(slot: dict, groups: dict) -> set[str]:
    """GE areas a filled slot will carry (assumed for later "GE Area X" prereqs)."""
    f = groups.get(slot.get("slot"), {}).get("from", {})
    areas = f.get("ge_area", []) if isinstance(f, dict) else []
    return {str(a) for a in (areas if isinstance(areas, list) else [areas])}


def check_plan(profile: dict, plan: dict, program: dict, university: dict, catalog: dict, prereqs: dict) -> dict:
    """{valid, errors, warnings, terms, remaining}. Errors make a plan invalid; warnings don't."""
    errors: list[dict] = []
    warnings: list[str] = ["Assumes in-progress and planned courses are passed with the grades their requirements need"]
    err = lambda kind, msg, **kw: errors.append({"error": kind, "message": msg, **kw})
    load, levels = university["academic_load"], university["class_level"]
    cap = profile.get("max_units_per_term", load["normal_max"])

    completed = [r for r in profile.get("completed", []) if r["code"] in catalog]
    grades: dict[str, str] = {}
    for r in completed:  # best attempt
        if r["code"] not in grades or (rank(r["grade"]) or -1) > (rank(grades[r["code"]]) or -1):
            grades[r["code"]] = r["grade"]
    done = {c for c, g in grades.items() if passed(g)} | {c for c in profile.get("in_progress", []) if c in catalog}
    now = audit(profile, program, university, catalog)["totals"]  # repeats, transfer duplicates handled there
    units = now["units"]["value"] + now["units_in_progress"]
    gpa = profile.get("gpa", now["gpa_sf_state"]["value"])

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
                elif c in grades and (rank(grades[c]) or 0) >= GRADE_POINTS["C"] or grades.get(c) == "CR":
                    err("already_passed", f"{c} was passed with {grades[c]}; it may not be repeated (p.2392)", term=term, course=c)
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
            warnings.extend(w for w in prereq_warnings(c, row) if "partial" in w or "unparsed" in w)
        if ctx.get("gpa_used") and "gpa" not in profile:
            warnings.append(f"GPA-gated prereqs were checked with your SF State GPA ({gpa}); pass `gpa` if your overall GPA differs")

        summer = term.endswith("summer")
        if term_units > cap:
            err("over_cap", f"{term}: {term_units:g} units is over max_units_per_term ({cap:g})", term=term)
        normal = load["summer_normal_max" if summer else "normal_max"]
        if term_units > normal:
            warnings.append(f"{term}: {term_units:g} units is above the normal load of {normal:g} ({load['source']}); "
                            "see an advisor before planning an overload")
        if summer and not profile.get("include_summer", False):
            warnings.append(f"{term}: summer term planned but include_summer is false")
        terms_out.append({"term": term, "units": term_units, "units_before": units})
        planned += [{"code": c, "grade": ASSUMED, "term": term} for c in codes if c in catalog]
        done = done | {c for c in codes if c in catalog}
        for c in codes:  # a planned retake replaces the old grade for later prereqs
            grades.pop(c, None)
        slot_areas |= {a for x in term_slots for a in slot_ge_areas(x, groups)}
        units += term_units

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
    warnings.extend(w for w in result["warnings"] if "not verified" in w)
    return {"catalog_year": program["catalog_year"], "valid": not errors, "errors": errors,
            "warnings": list(dict.fromkeys(warnings)), "terms": terms_out, "remaining": remaining}


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
    t = next_term(max(terms, key=term_key), profile.get("include_summer", False))
    return next_term(t, profile.get("include_summer", False)) if profile.get("in_progress") else t


def chunks(units: float, size: float = 3) -> list[float]:
    out = [size] * int(units // size)
    return out + [units - size * len(out)] if units % size else out


def build_plan(profile: dict, program: dict, university: dict, roadmap: dict, catalog: dict, prereqs: dict) -> dict:
    """Deterministic baseline plan (ARCHITECTURE §8): required courses by critical path, then slots. Passes check_plan."""
    from gatorpath.engine.prereq import prereq_chain

    summer = profile.get("include_summer", False)
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
    if variant is None and any(number(c) < 300 for c in required):
        return {"catalog_year": program["catalog_year"], "needs_input": "qr_pathway",
                "warnings": ["The roadmap (and the math courses before MATH 226) depends on the QR pathway / math "
                             "placement: give qr_pathway ('1/2' or '3/4'), or adt: true for a verified AA-T/AS-T"]}

    # Roadmap courses for this pathway that lead to a required course (QR 3/4: MATH 197, MATH 198 before MATH 226).
    items = [i for sem in roadmap["variants"][variant]["semesters"] for i in sem["items"]] if variant else []
    order = {c: n for n, c in enumerate(i for i in items if isinstance(i, str))}
    have = {r["code"] for r in profile.get("completed", []) if passed(r["grade"])} | set(in_prog)
    best = {}
    for r in profile.get("completed", []):
        if r["code"] not in best or (rank(r["grade"]) or -1) > (rank(best[r["code"]]) or -1):
            best[r["code"]] = r["grade"]
    stuck = [c for c in required if not catalog[c]["repeatable"]
             and (best.get(c) == "CR" or (rank(best.get(c)) or 0) >= GRADE_POINTS["C"])]
    warnings = [f"{c}: passed with {best[c]}, which doesn't count toward this requirement, and a course passed with CR "
                "or C or better can't be repeated (p.2392); see an advisor about a substitution or petition" for c in stuck]
    required = [c for c in required if c not in stuck]
    closure = {e["code"] for c in required if c in prereqs for e in prereq_chain(c, prereqs)["chain"]}
    todo = required + [c for c in order if c in closure and c not in have and c not in required and c in catalog]

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
    first_elective = next((n for n, sem in enumerate(roadmap["variants"][variant]["semesters"])
                           if any(isinstance(i, dict) and i.get("slot") == "senior_elective" for i in sem["items"])), None) if variant else None
    before_electives = {i for sem in roadmap["variants"][variant]["semesters"][:first_elective] for i in sem["items"]
                        if isinstance(i, str)} if first_elective is not None else set()

    done = set(have)
    grades = {r["code"]: r["grade"] for r in profile.get("completed", [])}
    units = status["totals"]["units"]["value"]
    gpa = profile.get("gpa", status["totals"]["gpa_sf_state"]["value"])
    left = sorted(todo, key=rank_of)
    semesters, term = [], start
    slot_areas: set[str] = set()
    for _ in range(20):
        if not left and not slots:
            break
        if term.endswith("summer") and not summer:
            term = next_term(term, summer)
            continue
        limit = min(cap, load["summer_normal_max"]) if term.endswith("summer") else cap
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
            return state == OK or (state == UNVERIFIED and not waiting)

        changed = True
        while changed:
            changed = False
            for c in [c for c in left if c not in placed]:
                bundle = [c] + [d for d in needs[c] if d in left and d not in placed and c in needs.get(d, ()) and d not in hard[c]]
                u = sum(catalog[b]["units_min"] for b in bundle)
                same = set(placed) | set(bundle)
                if used + u <= limit and all(ok(b, same) for b in bundle):
                    placed += bundle
                    used += u
                    changed = True
                    break
        left = [c for c in left if c not in placed]
        ready_electives = units >= levels["upper"] and before_electives & set(todo) <= done
        term_slots = []
        for kind in ("tag", "ge", "ud_ge", "major", "elective"):
            for s in [s for s in slots if s["_kind"] == kind]:
                if kind in ("ud_ge", "major") and units < levels["upper"]:
                    continue
                if kind == "major" and not ready_electives:
                    continue
                if kind == "elective" and s.get("upper_division") and units < levels["upper"]:
                    continue
                if used + s["units"] <= limit:
                    term_slots.append(s)
                    slots.remove(s)
                    used += s["units"]
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
    return {"catalog_year": program["catalog_year"], "variant": variant, **plan,
            "est_graduation_term": semesters[-1]["term"] if semesters and check["valid"] else None,
            "warnings": warnings + check["warnings"], "check": {"valid": check["valid"], "errors": check["errors"]}}
