"""Bulletin prereq text -> expression tree (ARCHITECTURE §6.3). Pure functions, no DB.

How SFSU writes prereqs (checked against every CSC/MATH/PHYS string, 2026-27):
- ';' separates AND clauses; a clause starting with 'or' starts an alternative ("A; B; or permission").
- A grade phrase covers the courses before it in its clause. "all with grades …" at the end of a
  clause, or a clause that is only a grade phrase, covers every earlier clause in the group too.
- 'either A or B' binds tighter than 'and'; ', and' / ', or' split a comma list.
- Clauses saying "recommended" are not requirements.
Anything not understood becomes an {"unknown": text} leaf: kept, never dropped (status 'partial').
"""

import re

I = re.I
COURSE = re.compile(r"([A-Z]{1,5}(?: [A-Z]{1,3})? \d{3}[A-Z]{0,3})\*?(?!\w)")
GRADE = re.compile(
    r"(all\s+)?(?:completed\s+)?with\s+(?:a\s+)?(?:grades?\s+of\s+)?((?-i:[A-D]))(\+|-\s*minus|-|\s+minus)?(?![A-Za-z])"
    r"(?:\s+or\s+(better|higher|lower))?",
    I,
)
UP, SENIOR, GRAD = {"standing": "upper"}, {"standing": "senior"}, {"standing": "graduate"}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
ADVISORY = re.compile(r"\b(recommended|should)\b", I)
MAY_ENROLL = re.compile(r"(.+?) may enroll with (?:the )?permission of the instructor\.?$", I)
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
    (re.compile(r"concurrent(?:ly)? enroll(?:ment)? in", I), lambda m: (CONC_PREFIX, None)),
    (GRADE, lambda m: (GRADE_T, (m.group(2) + ("+" if m.group(3) == "+" else "-" if m.group(3) else ""), bool(m.group(1)),
                                 "max_grade" if (m.group(4) or "").lower() == "lower" else "min_grade"))),
    # Placement "Category 1/2" is the roadmap QR pathway 1/2 (Bulletin p.1906 -> p.1908).
    (re.compile(r"category (iv|i{1,3})\*?(?: (?:or|and) (iv|i{1,3})\*?)? placement for qr/math", I),
     lambda m: (LEAF, {"qr_category": [ROMAN[g.lower()] for g in m.groups() if g]})),
    (re.compile(r"first-year math advising module", I), lambda m: (LEAF, {"requirement": "First-Year Math Advising Module"})),
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
    (re.compile(r"graduate(?:[- ]level)? standing\*?", I), lambda m: (LEAF, dict(GRAD))),
    (re.compile(r"(?:a |overall )?gpa of (?:at least )?(\d\.\d+)(?: or (?:higher|better))?", I),
     lambda m: (LEAF, {"gpa": float(m.group(1))})),
    (re.compile(r"(\d\.\d+) gpa or (?:higher|better)", I), lambda m: (LEAF, {"gpa": float(m.group(1))})),
    (re.compile(r"(?:permission|approval) of (?:the )?(instructor|department|computer science department|faculty adviser|"
                r"graduate (?:major )?advis[eo]r)(?: (and|or) (instructor|graduate advis[eo]r|committee chair))?", I),
     lambda m: (LEAF, permissions(m))),
    (re.compile(r"(?:the candidate's )?committee chair", I), lambda m: (LEAF, {"permission": "committee_chair"})),
    (re.compile(r"restricted to (.+?),?(?= or (?:permission|approval)\b|$)", I),
     lambda m: (LEAF, {"restricted_to": m.group(1).strip()})),
    (re.compile(r"(\d[a-c]?)/[a-d]\d\*?", I), lambda m: (LEAF, {"ge_area": m.group(1).upper()})),
    (COURSE, lambda m: (LEAF, {"course": m.group(1)})),
    (re.compile(r"equivalent\b", I), lambda m: (LEAF, {"equivalent": True})),
    (re.compile(r"and/or\b|or\b|/", I), lambda m: (OR, None)),
    (re.compile(r"and\b|&", I), lambda m: (AND, None)),
    (re.compile(r","), lambda m: (COMMA, None)),
    (re.compile(r"either\b", I), lambda m: (EITHER, None)),
    (re.compile(r"both\b", I), lambda m: (BOTH, None)),
    (re.compile(r"ge areas?\b|one of the following:|required\b|all\b|successful completion of|in a previous semester", I),
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


def parse_prereq(text: str) -> dict:
    text = text.strip()
    if not text:
        return {"expr": None, "status": "none", "needs_permission": False}
    sentences, dropped = [], False
    for sentence in re.split(r"(?<=\.)\s+(?=[A-Z])", text):
        if sentence.lower().startswith("for students who"):  # audience note, not a requirement
            dropped = True
            continue
        if m := MAY_ENROLL.match(sentence):  # "Senior … majors may enroll with the permission of the instructor."
            alt = {"all": [{"restricted_to": m.group(1)}, {"permission": "instructor"}]}
            sentences[-1:] = [combine("any", [*sentences[-1:], alt])]
            continue
        replaced = sentence.lower().startswith("may be replaced by ")  # "… May be replaced by permission"
        if replaced:
            sentence = sentence[len("may be replaced by "):]
        groups = [[]]
        for clause in sentence.rstrip(".").split(";"):
            clause = clause.strip()
            if ADVISORY.search(clause):
                dropped = True
                continue
            if not clause:
                continue
            if clause.lower().startswith("or "):
                groups.append([])
                clause = clause[3:]
            elif clause.lower().startswith("and "):
                clause = clause[4:]
            expr, group_grade = parse_clause(clause)
            if group_grade:
                for e in groups[-1]:
                    apply_grade(e, *group_grade)
            if expr:
                groups[-1].append(expr)
        expr = combine("any", [combine("all", g) for g in groups])
        if replaced and sentences:
            sentences[-1] = combine("any", [sentences[-1], expr])
        else:
            sentences.append(expr)
    expr = combine("all", sentences)
    found = list(leaves(expr))
    unknown = sum("unknown" in leaf for leaf in found)
    if expr is None:
        status = "ok" if dropped else "unparsed"
    else:
        status = "ok" if not unknown else "unparsed" if unknown == len(found) else "partial"
    return {"expr": expr, "status": status, "needs_permission": any("permission" in leaf for leaf in found)}
