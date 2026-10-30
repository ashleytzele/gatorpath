"""Bulletin prereq text -> expression tree (ARCHITECTURE §6.3). Pure functions, no DB.

How SFSU writes prereqs (checked against every CSC/MATH/PHYS string, 2026-27):
- ';' separates AND clauses; a clause starting with 'or' starts an alternative ("A; B; or permission").
- A grade phrase covers the courses before it in its clause. "all with grades …" at the end of a
  clause, or a clause that is only a grade phrase, covers every earlier clause in the group too.
- 'either A or B' binds tighter than 'and'; ', and' / ', or' split a comma list.
- Clauses saying "recommended" are not requirements.
- "<X> majors with …" clauses are alternatives, one per major (ENGR 696: "Civil Engineering majors with … ENGR 300 …;
  Mechanical Engineering majors with … ENGR 302 …").
Anything not understood becomes an {"unknown": text} leaf: kept, never dropped (status 'partial').
"""

import re

I = re.I
COURSE = re.compile(r"([A-Z]{1,5}(?: [A-Z]{1,3})? \d{3}[A-Z]{0,3})\*?(?!\w)")
GRADE = re.compile(  # "C-or better" too, with no space (ENGR 304); it was read as "C"
    r"(all\s+)?(?:completed\s+)?with\s+(?:a\s+)?(?:grades?\s+of\s+)?((?-i:[A-D]))(\+|-\s*minus|-|\s+minus)?"
    r"(?:(?![A-Za-z])|(?<=[+-])(?=or\b))(?:\s*or\s+(better|higher|lower))?",
    I,
)
# a course's subject: KIN, AA S; not a degree or GE ("24 units of MA coursework", ISED 895)
SUBJECT = r"(?-i:(?!(?:MA|MS|MFA|MBA|BA|BS|GE)\b)[A-Z]{1,5}(?: [A-Z]{1,3})?)"
NUMBERS = {"six": 6, "nine": 9, "twelve": 12}
OLD_GE = r"(?-i:[A-F][1-5]?)\*?(?![\w/])"  # an older GE code: A2, B4, E (this Bulletin's start with a digit)
SOPH, UP, SENIOR, GRAD = {"standing": "sophomore"}, {"standing": "upper"}, {"standing": "senior"}, {"standing": "graduate"}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
# QR/Math placement as the Bulletin words it: "Category I or II placement for QR/Math", "Category III or IV for QR/Math
# placement", "CAT I or II placement for QR/MATH*", "Category I or II QR/Math placement", "Placement Category III or IV"
QR = (r"(?:\bcat(?:egory)?|(?:quantitative reasoning )?placement category) (iv|i{1,3})\*?(?: (?:or|and) (iv|i{1,3})\*?)?"
      r"(?:(?: placement)?(?: for)? qr/math\*?(?: placement)?)?")
# a sentence for one placement: "Category III or IV for QR/Math placement must have completed MATH 197 …"
PLACED = re.compile(rf"((?>{QR})) (?:must )?(?!or\b)(.+)$", re.I)  # atomic: "placement for QR/Math" isn't the rest
# one sentence, one way in per placement: "CAT I or II placement for QR/MATH* or CAT III or IV placement for QR/MATH with a
# grade of C or better in MATH 124* or MATH 197* or MATH 199*" (CHEM 115)
TWO_PLACEMENTS = re.compile(rf"^((?>{QR})[^.;]*?)\s+or\s+((?>{QR})[^;]*)$", re.I)


def placement(text: str) -> dict | None:
    """A placement and what it needs: "CAT III or IV placement … with a grade of C or better in MATH 124* or …"."""
    if not (m := PLACED.match(text)):
        return parse_prereq(text, False)["expr"]
    rest = re.sub(r"^(?:with )?a grade of (\S+ or better) in (.+)$", r"\2 with a grade of \1", re.sub(r"^have completed ", "", m[4]))
    return combine("all", [{"qr_category": [ROMAN[g.lower()] for g in m.groups()[1:3] if g]}, parse_prereq(rest, False)["expr"]])
ADVISORY = re.compile(r"\b(recommended|should)\b", I)
MAY_ENROLL = re.compile(r"(.+?) may enroll with (?:the )?permission of the instructor\.?$", I)
MAJORS_WITH = re.compile(r"(?:Restricted to )?([A-Za-z][A-Za-z&,\- ]*? majors(?: and minors)?) with (.+)$", I)
ATC = "Advancement to Candidacy and Culminating Experience forms approved by Graduate Studies"


def perm(who: str) -> dict:
    who = who.lower()
    kind = ("instructor" if who == "instructor" else "department" if "department" in who
            else "committee_chair" if "committee chair" in who else "advisor")
    return {"permission": kind}


def permissions(m: re.Match) -> dict:
    first, op, second = m.groups()
    if not second:
        return perm(first)
    return {"any" if op.lower() == "or" else "all": [perm(first), perm(second)]}


LEAF, AND, OR, COMMA, EITHER, BOTH, GRADE_T, CONC_MARK, CONC_PREFIX, WORD = range(10)
RULES = [
    (re.compile(r"\(may be taken concurrently\)", I), lambda m: (CONC_MARK, None)),
    # "must/may be taken concurrently with X" too, but not "May not be taken concurrently with" (an exclusion) nor CINE's
    # "may be taken concurrently without a formal exception"
    (re.compile(r"concurrent(?:ly)? enroll(?:ment)? in|be enrolled in an?\b|(?:must |may )?(?<!not )be taken concurrently with\b",
                I), lambda m: (CONC_PREFIX, None)),
    (GRADE, lambda m: (GRADE_T, (m.group(2) + ("+" if m.group(3) == "+" else "-" if m.group(3) else ""), bool(m.group(1)),
                                 "max_grade" if (m.group(4) or "").lower() == "lower" else "min_grade"))),
    # Placement "Category 1/2" is the roadmap QR pathway 1/2 (Bulletin p.1906 -> p.1908).
    (re.compile(QR, I), lambda m: (LEAF, {"qr_category": [ROMAN[g.lower()] for g in m.groups() if g]})),
    # an exclusion, not a requirement: "Not open to students who have completed ERTH 110 or ERTH 111" (ERTH 112)
    (re.compile(rf"(?i:not open to students who have completed )((?:{COURSE.pattern}(?:,? (?:or|and) |, )?)+)"),
     lambda m: (LEAF, combine("all", [{"not_after": c} for c in COURSE.findall(m.group(1))]))),
    # and not in the same term: "May not be taken concurrently with M S 684" (M S 683); "with JOUR 605* and JOUR 609*"
    (re.compile(rf"(?i:may not be taken concurrently with )((?:{COURSE.pattern}(?:,? (?:or|and) |, )?)+)"),
     lambda m: (LEAF, combine("all", [{"not_with": c} for c in COURSE.findall(m.group(1))]))),
    # units done: "24 upper-division units in AA S courses" (AA S 696), "6 units of upper-division KIN courses", "15*
    # upper-division ENGR units" (ENGR 696), "Nine units of SXS coursework", "30 units of coursework" (A U 220)
    (re.compile(rf"(?:a minimum of |at least )?(\d+|{'|'.join(NUMBERS)})\*? (upper-division )?(?:units (?:of|in) "
                rf"(upper-division )?(?:({SUBJECT}) )?(?:coursework|courses)\b|({SUBJECT}) units\b)", I),
     lambda m: (LEAF, {"units": int(NUMBERS.get(m[1].lower(), m[1]))} | ({"subject": m[4] or m[5]} if m[4] or m[5] else {})
                | ({"level": "upper"} if m[2] or m[3] else {}))),
    (re.compile(r"first-year math advising module", I), lambda m: (LEAF, {"requirement": "First-Year Math Advising Module"})),
    (re.compile(r"(?:by |an )?audition\b", I), lambda m: (LEAF, {"requirement": "Audition"})),  # MUS ensembles: "Audition."
    # Named non-course requirements: understood, but unverifiable (⚠️ like permission).
    (re.compile(r"(?:approval of )?(?:advancement to candidacy|atc\b|proposal for culminating experience)(?:(?!permission)[^;])*?"
                r"\bforms\b(?: (?:must be )?approved)?(?: by (?:the )?(?:division of graduate studies|graduate division|"
                r"graduate studies))?(?: before registration)?", I), lambda m: (LEAF, {"requirement": ATC})),
    (re.compile(r"an approved study proposal must be on file by the time of registration", I),
     lambda m: (LEAF, {"requirement": "Approved study proposal on file by registration"})),
    (re.compile(r"an? college-level [a-z]+ course", I), lambda m: (LEAF, {"requirement": m.group(0)})),
    (re.compile(r"high school ([a-z-]+(?: and [a-z-]+)?)", I), lambda m: (LEAF, {"high_school": m.group(1)})),
    (re.compile(r"in an? ([\w ]+? program)\b", I), lambda m: (LEAF, {"restricted_to": m.group(1)})),
    (re.compile(r"upper[- ]division or graduate standing", I), lambda m: (LEAF, {"any": [dict(UP), dict(GRAD)]})),
    (re.compile(r"(?:restricted to )?upper[- ]division (?:standing|students)", I), lambda m: (LEAF, dict(UP))),
    (re.compile(r"senior standing", I), lambda m: (LEAF, dict(SENIOR))),
    (re.compile(r"sophomore standing(?: (?:or|and) (?:above|higher))?", I), lambda m: (LEAF, dict(SOPH))),
    # Junior is 60-89 units, upper division (p.2390)
    (re.compile(r"junior standing(?: or above)?", I), lambda m: (LEAF, dict(UP))),
    (re.compile(r"graduate(?:[- ]level)? standing\*?", I), lambda m: (LEAF, dict(GRAD))),
    (re.compile(r"(?:a |overall )?gpa of (?:at least )?(\d\.\d+)(?: or (?:higher|better))?", I),
     lambda m: (LEAF, {"gpa": float(m.group(1))})),
    (re.compile(r"(\d\.\d+) gpa or (?:higher|better)", I), lambda m: (LEAF, {"gpa": float(m.group(1))})),
    (re.compile(r"(?:permission|approval) of (?:the )?(instructor|department|computer science department|faculty adviser|"
                r"graduate (?:major )?advis[eo]r)(?: (and|or) (instructor|graduate advis[eo]r|committee chair))?", I),
     lambda m: (LEAF, permissions(m))),
    (re.compile(r"(?:the candidate's )?committee chair", I), lambda m: (LEAF, {"permission": "committee_chair"})),
    # a standing, not a program: "Restricted to senior standing and LS 300GW" (LS 690)
    (re.compile(r"restricted to (?=(?:sophomore|junior|senior) standing\b)", I), lambda m: None),
    (re.compile(r"restricted to (.+?),?(?= or (?:permission|approval)\b|$)", I),
     lambda m: (LEAF, {"restricted_to": m.group(1).strip()})),
    (re.compile(r"(\d[a-c]?)/[a-d]\d\*?(?: course\b| requirement\b)?", I), lambda m: (LEAF, {"ge_area": m.group(1).upper()})),
    # older GE codes, "GE Area A2" (ENGR 697GW), "GE Areas A1*, A2*, A3*, and B4*" (HIST 342): as printed, then
    # parse_prereq reads them as this Bulletin's areas (current_ge)
    (re.compile(rf"ge areas? ({OLD_GE}(?:(?:,? (?:and|or) |, ){OLD_GE})*)", I),
     lambda m: (LEAF, combine("any" if " or " in m[1] and " and " not in m[1] else "all",
                              [{"ge_area": c} for c in re.findall(r"(?-i:[A-F][1-5]?)(?=\*|\b)", m[1])]))),
    (COURSE, lambda m: (LEAF, {"course": m.group(1)})),
    (re.compile(r"equivalents?\b", I), lambda m: (LEAF, {"equivalent": True})),  # "… or equivalents with grades of …"
    (re.compile(r"and/or\b|or\b|/", I), lambda m: (OR, None)),
    (re.compile(r"and\b|&", I), lambda m: (AND, None)),
    (re.compile(r","), lambda m: (COMMA, None)),
    (re.compile(r"either\b", I), lambda m: (EITHER, None)),
    (re.compile(r"both\b", I), lambda m: (BOTH, None)),
    (re.compile(r"ge areas?\b|one of the following:|required\b|all\b|successful completion of|in a previous semester|"
                r"have satisfied the\b", I),
     lambda m: None),
    (re.compile(r"[^\s,;/&()]+|\S"), lambda m: (WORD, None)),
]


def leaves(expr):
    if expr is None:
        return
    if "all" in expr or "any" in expr:
        for e in expr.get("all", expr.get("any")):
            yield from leaves(e)
    else:
        yield expr


def granted(expr):
    """The tree with each permission leaf ({"permission": "instructor"}) as {"granted": "instructor"}: the student says
    they have it (profile.permissions), so it counts as met instead of only being reported."""
    if expr is None:
        return None
    if "all" in expr or "any" in expr:
        op = "all" if "all" in expr else "any"
        return expr | {op: [granted(e) for e in expr[op]]}
    return {"granted": expr["permission"]} if "permission" in expr else expr


def combine(op: str, parts: list) -> dict | None:
    flat = []
    for p in parts:
        if p is None:
            continue
        flat += [x for x in (p[op] if op in p else [p]) if x not in flat]
    return None if not flat else flat[0] if len(flat) == 1 else {op: flat}


def apply_grade(expr, grade: str, key: str = "min_grade") -> None:
    """key is 'max_grade' for "… with a grade of C- or lower" (a retake condition)."""
    for leaf in leaves(expr):
        if "course" in leaf or "ge_area" in leaf or "high_school" in leaf:
            leaf.setdefault(key, grade)


def tokenize(s: str) -> list[tuple]:
    toks, pending, pos = [], None, 0

    def flush():
        nonlocal pending
        if pending:
            text = s[pending[0]:pending[1]]
            # "Graduate Mathematics students", "BA Math … majors": a program restriction without "Restricted to"
            key = "restricted_to" if re.search(r"\b(students|majors|minors|status)$", text) else "unknown"
            toks.append((LEAF, {key: text}))
            pending = None

    while pos < len(s):
        if s[pos].isspace():
            pos += 1
            continue
        for rx, make in RULES:
            if m := rx.match(s, pos):
                break
        tok = make(m)
        if tok and tok[0] == WORD:
            pending = (pending[0] if pending else m.start(), m.end())
        else:
            flush()
            if tok:
                toks.append(tok)
        pos = m.end()
    flush()
    return mark_concurrent(toks)


def mark_concurrent(toks: list[tuple]) -> list[tuple]:
    """'concurrent enrollment in X' marks the courses after it; '(may be taken concurrently)' the ones before it."""
    out, prefix = [], False
    for kind, val in toks:
        if kind == CONC_PREFIX:
            prefix = True
            continue
        if kind == CONC_MARK:
            scope = out[-1:] if out and out[-1][0] == LEAF else []
            if out and out[-1][0] == GRADE_T:
                scope = []
                for t in reversed(out[:-1]):
                    if t[0] == GRADE_T:
                        break
                    scope.append(t)
            for t in scope:
                if t[0] == LEAF:
                    for leaf in leaves(t[1]):
                        if "course" in leaf:
                            leaf["concurrent_ok"] = True
            continue
        if prefix and kind == LEAF:
            for leaf in leaves(val):
                if "course" in leaf:
                    leaf["concurrent_ok"] = True
        out.append((kind, val))
    return out


def parse_bool(toks: list[tuple]) -> dict | None:
    """or_expr := and_expr ('or' and_expr)* ; and_expr := unit ('and'? unit)* ; unit := leaf | either… | both…"""
    pos = 0

    def peek():
        return toks[pos][0] if pos < len(toks) else None

    def unit():
        nonlocal pos
        kind, val = toks[pos]
        pos += 1
        if kind == EITHER:
            parts = [unit()] if pos < len(toks) else []
            while peek() == OR:
                pos += 1
                parts.append(unit())
            return combine("any", parts)
        if kind == BOTH:
            parts = [unit()] if pos < len(toks) else []
            if peek() == AND:
                pos += 1
                parts.append(unit())
            return combine("all", parts)
        return val if kind == LEAF else None

    def and_expr():
        nonlocal pos
        parts = [unit()]
        while pos < len(toks) and peek() != OR:
            if peek() == AND:
                pos += 1
                if pos >= len(toks):
                    break
            parts.append(unit())
        return combine("all", parts)

    parts = [and_expr()] if toks else []
    while peek() == OR:
        pos += 1
        if pos < len(toks):
            parts.append(and_expr())
    return combine("any", parts)


def parse_list(toks: list[tuple]) -> dict | None:
    if not any(k == COMMA for k, _ in toks):
        return parse_bool(toks)
    segments, ops = [[]], set()
    for t in toks:
        if t[0] == COMMA:
            segments.append([])
        else:
            segments[-1].append(t)
    parts = []
    for seg in segments:
        if seg and seg[0][0] in (AND, OR):
            ops.add(seg[0][0])
            seg = seg[1:]
        if seg:
            parts.append(parse_bool(seg))
    return combine("any" if ops == {OR} else "all", parts)


def parse_seq(toks: list[tuple]) -> dict | None:
    """A grade phrase ends a group: 'A and B with grades of C or better or X' = (A and B) or X."""
    g = next((i for i, t in enumerate(toks) if t[0] == GRADE_T), None)
    if g is None:
        return parse_list(toks)
    left, right = toks[:g], toks[g + 1:]
    lhs = parse_list(left)
    grade, _, key = toks[g][1]
    apply_grade(lhs, grade, key)
    while right and right[0][0] == COMMA:
        right = right[1:]
    if not right:
        return lhs
    if right[0][0] in (OR, AND):
        return combine("any" if right[0][0] == OR else "all", [lhs, parse_seq(right[1:])])
    return combine("all", [lhs, parse_seq(right)])


def parse_clause(clause: str) -> tuple[dict | None, tuple[str, str] | None]:
    """Returns (expr, grade to apply to the whole group, if this clause's grade phrase reaches back)."""
    toks = tokenize(clause)
    group_grade = None
    trimmed = [t for t in toks if t[0] != COMMA]
    if trimmed and trimmed[-1][0] == GRADE_T:
        grade, says_all, key = trimmed[-1][1]
        if says_all or len(trimmed) == 1:
            group_grade = (grade, key)
    return parse_seq(toks), group_grade


def current_ge(expr: dict | None, legacy: dict) -> dict | None:
    """An older GE code ("GE Area A2", ENGR 697GW) -> the area the university rules' legacy_ge_areas give it ("Area 1A:
    English Composition ... [Formerly A2]", p.2314); one with two (2024-25's D2) needs both. One with no equivalent (E)
    stays unknown, as without a map."""
    if not expr:
        return expr
    if "all" in expr or "any" in expr:
        op = "all" if "all" in expr else "any"
        return combine(op, [current_ge(e, legacy) for e in expr[op]])
    code = str(expr.get("ge_area", "1"))
    if not code[0].isalpha():  # this Bulletin's codes start with a digit: 1A, 2, 3UD
        return expr
    if (new := legacy.get(code.upper())) is None:
        return {"unknown": f"GE Area {code}"}
    return combine("all", [expr | {"ge_area": str(a)} for a in (new if isinstance(new, list) else [new])])


def parse_prereq(text: str, legacy: dict | None | bool = None) -> dict:
    """`legacy`: the catalog year's legacy_ge_areas map (older GE code -> this Bulletin's areas). False leaves older codes
    as printed, for a caller that translates the whole tree."""
    text = text.strip()
    if not text:
        return {"expr": None, "status": "none", "needs_permission": False}
    sentences, dropped = [], False
    for sentence in re.split(r"(?<=\.)\s+(?=[A-Z])", text):
        if sentence.lower().startswith("for students who"):  # audience note, not a requirement
            dropped = True
            continue
        if (m := TWO_PLACEMENTS.match(sentence.rstrip("."))):
            sentences.append(combine("any", [placement(m[1]), placement(m[4])]))
            continue
        if PLACED.match(sentence) and any("qr_category" in leaf for e in sentences for leaf in leaves(e)):
            # placements are exclusive, so another placement's sentence is its own way in (CHEM 180), not one more need
            sentences[-1:] = [combine("any", [*sentences[-1:], placement(sentence.rstrip("."))])]
            continue
        if m := MAY_ENROLL.match(sentence):  # "Senior … majors may enroll with the permission of the instructor."
            alt = {"all": [{"restricted_to": m.group(1)}, {"permission": "instructor"}]}
            sentences[-1:] = [combine("any", [*sentences[-1:], alt])]
            continue
        replaced = sentence.lower().startswith("may be replaced by ")  # "… May be replaced by permission"
        if replaced:
            sentence = sentence[len("may be replaced by "):]
        groups, majors = [[]], []  # majors: the "<X> majors with …" branches of the current group
        flush = lambda: groups[-1].append(combine("any", [combine("all", b) for b in majors])) if majors else None
        for clause in sentence.rstrip(".").split(";"):
            clause = clause.strip()
            if ADVISORY.search(clause):
                dropped = True
                continue
            if not clause:
                continue
            if clause.lower().startswith("or "):
                flush()
                groups.append([])
                majors = []
                clause = clause[3:]
            elif clause.lower().startswith("and "):
                clause = clause[4:]
            # not "… majors with junior standing", and not "A or B and C or D" (ambiguous: kept whole, flagged)
            if (m := MAJORS_WITH.match(clause)) and COURSE.search(m[2]) and "standing" not in m[2] and not (
                    " or " in m[2] and " and " in m[2] and "either" not in m[2]):
                majors.append([{"restricted_to": m.group(1)}])
                clause = m.group(2)
            into = majors[-1] if majors else groups[-1]  # a clause after a branch is that major's
            expr, group_grade = parse_clause(clause)
            if group_grade:
                for e in into:
                    apply_grade(e, *group_grade)
            if expr:
                into.append(expr)
        flush()
        expr = combine("any", [combine("all", g) for g in groups])
        if replaced and sentences:
            sentences[-1] = combine("any", [sentences[-1], expr])
        else:
            sentences.append(expr)
    expr = combine("all", sentences)
    if legacy is not False:
        expr = current_ge(expr, legacy or {})
    found = list(leaves(expr))
    unknown = sum("unknown" in leaf for leaf in found)
    if expr is None:
        status = "ok" if dropped else "unparsed"
    else:
        status = "ok" if not unknown else "unparsed" if unknown == len(found) else "partial"
    return {"expr": expr, "status": status, "needs_permission": any("permission" in leaf for leaf in found)}


UNVERIFIABLE = {"permission", "restricted_to", "equivalent", "requirement", "high_school", "unknown"}
# "An \"*\" denotes that a course prerequisite is enforced at the time of registration. Prerequisites without a \"*\"
# may be enforced by the instructor up to the end of add/drop." (p.2436) So `X*` is the plain prereq X, no warning.


def prereq_warnings(code: str, row: dict) -> list[str]:
    """⚠️ for prereq text the tree can't fully vouch for. Raw Bulletin text is quoted so the reader can check."""
    out = []
    if row["status"] in ("partial", "unparsed"):
        out.append(f"{code}: prereq is {row['status']}, only partly machine-readable; Bulletin text: {row['raw_text']!r}")
    return out


def prereq_chain(code: str, prereqs: dict[str, dict]) -> dict:
    """Everything that must come before `code`, from {code: {raw_text, expr, status, …}} for one catalog year.

    `chain` lists every course the prereqs mention, alternatives included, each before the courses that need it
    and `code` last; each entry's `requires` says which are and/or. `conditions` are the non-course leaves.
    Corequisites ("concurrent enrollment in PHYS 222" both ways) point at each other, so a back edge through a
    `concurrent_ok` leaf is expected; any other back edge is a ⚠️.
    """
    chain, conditions, warnings, state = [], [], [], {}
    missing: dict[str, list[str]] = {}

    def visit(c: str, needed_by: str | None, concurrent: bool) -> None:
        if state.get(c) == "open" and not concurrent:
            warnings.append(f"{c}: prerequisite cycle through {needed_by}; stopped there")
        if c in state:
            return
        row = prereqs.get(c)
        state[c] = "open"
        if row is None:
            missing.setdefault(c, []).append(needed_by)
            return
        for leaf in leaves(row["expr"]):
            if "course" not in leaf:
                conditions.append({"for": c, **leaf, "verifiable": not UNVERIFIABLE & leaf.keys()})
            elif leaf["course"] in missing:
                missing[leaf["course"]].append(c)
            elif leaf["course"] != c:  # MATH 226 lists itself "with a grade of C- or lower": a retake rule, not a cycle
                visit(leaf["course"], c, leaf.get("concurrent_ok", False))
        if row["status"] in ("partial", "unparsed"):
            warnings.append(prereq_warnings(c, row)[0])
        state[c] = "done"
        chain.append({"code": c, "requires": row["expr"], **{k: v for k, v in row.items() if k != "expr"}})

    visit(code, None, False)
    warnings += [f"{c} (needed by {', '.join(by)}) is not in this catalog; it may have been renumbered" for c, by in missing.items()]
    return {"code": code, "requires": chain[-1]["requires"] if chain else None, "chain": chain,
            "conditions": conditions, "warnings": warnings}


def reverse_index(prereqs: dict[str, dict]) -> dict[str, list[str]]:
    """{code: courses whose prereqs name it (as a requirement or one of the alternatives)}: what a course unlocks."""
    out: dict[str, set[str]] = {}
    for c, row in prereqs.items():
        for leaf in leaves(row["expr"]):
            if "course" in leaf and leaf["course"] != c:
                out.setdefault(leaf["course"], set()).add(c)
    return {k: sorted(v) for k, v in out.items()}
