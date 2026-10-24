"""Bulletin program pages -> source text -> AI-drafted rules YAML -> check_program (ARCHITECTURE §6.2, D5). Offline: the
server never calls a model (D6), and a draft stays in rules/drafts/ until a person reviews it."""

import argparse
import json
import re
import shlex
import subprocess
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from gatorpath import db
from gatorpath.engine.planner import VARIANTS, approval_only, build_plan, check_roadmap, ge_areas
from gatorpath.engine.rules import RULES_DIR, audit, check_program, filters_for, matches
from gatorpath.ingest.bulletin import extract_pages

LISTED = re.compile(r"• (Bachelor of (?:Arts|Science|Music|Fine Arts)\b[^•()]*?) \(p\. (\d{1,4})\)")
HEAD = re.compile(r"\s*San Francisco State University Bulletin \d{4}-\d{4}\s*")
DEGREES = {"Bachelor of Arts": "ba", "Bachelor of Science": "bs", "Bachelor of Music": "bm", "Bachelor of Fine Arts": "bfa"}
MARK = re.compile(r"^=== p\.(\d{1,4}) ===$", re.M)
ARCHITECTURE = Path(__file__).parents[3] / "docs/ARCHITECTURE.md"
CLIENT = "claude -p --tools '' --strict-mcp-config --setting-sources project"  # no tools: it only writes YAML


def clean(page: str) -> list[str]:
    return [line.strip() for line in unicodedata.normalize("NFKC", page).split("\n") if line.strip()]  # ﬁ -> fi


def head(page: str) -> str:
    """The running head without the Bulletin's name ('' if none). A long head wraps: a right-hand page prints the name
    after it (whole title), a left-hand one before it, so there it may be only the first part."""
    lines = clean(page)[:5]  # a long head wraps over up to 4 lines (BUS ADT roadmaps, p.159)
    k = next((i for i, line in enumerate(lines) if HEAD.search(line)), None)
    return "" if k is None else " ".join(" ".join(lines[:k] + [HEAD.sub(" ", lines[k])]).split())


def printed(page: str) -> int | None:
    lines = clean(page)
    return int(lines[-1]) if lines and lines[-1].isdigit() else None


def index(pages: list[str]) -> list[dict]:
    """Bachelor's programs the department pages list ("• Bachelor of … (p. 2129)"), each with its requirement pages (from
    its first page while the running head is its title, or the start of it) and roadmap pages (heads that go on past
    it). The list isn't always the heading: when the listed page isn't one of the title's requirement pages, the page
    whose head is the title; else the listed page's head is the title (the list shortened it)."""
    norm = lambda t: " ".join(t.replace("&", "and").split())
    flat = " ".join(" ".join(clean(p)) for p in pages)
    listed: dict[str, int] = {}
    for title, page in LISTED.findall(flat):
        listed.setdefault(" ".join(title.split()), int(page))
    by_page = {n: p for p in pages if (n := printed(p))}
    heads = {n: norm(head(p)) for n, p in by_page.items()}
    found = {}
    for title, page in listed.items():
        t, h = norm(title), heads.get(page, "")
        if h and t.startswith(h):
            found[title] = page
        elif exact := next((n for n, x in sorted(heads.items()) if x == t), None):
            found[title] = exact
        elif h:
            found[" ".join(head(by_page[page]).split())] = page
    order = sorted(set(found.values()))
    out = []
    for title, start in sorted(found.items(), key=lambda x: x[1]):
        stop = next((n for n in order if n > start), max(heads) + 1)
        t, req, road, n = norm(title), [], [], start

        def at(n: int) -> str:
            h = heads.get(n, "") if n < stop else ""
            if h and h != t and t.startswith(h) and len(lines := clean(by_page[n])) > 1:
                more = norm(f"{h} {lines[1]}")  # a left-hand page cut the head short: its next line finishes it
                if more.startswith(t) or t.startswith(more):
                    return more
            return h

        while (h := at(n)) and t.startswith(h):
            req.append(n)
            n += 1
        # roadmap pages: the heads that go on past the title, up to the next program (not only right after: another
        # roadmap can sit between, e.g. Anthropology's BA + MA Scholars roadmap, p.892)
        road = [k for k in range(n, stop) if (h := at(k)) and h.startswith(t)]
        out.append({"title": title, "pages": req, "roadmap_pages": road})
    return out


def program_id(title: str, existing: dict[str, str]) -> str:
    """'Bachelor of Arts in English: Concentration in Literature' -> 'ba-english-literature', 'Bachelor of Music:
    Concentration in Composition' -> 'bm-composition'; a program that already has
    rules keeps its id ('bs-cs')."""
    if title in existing:
        return existing[title]
    degree = next((d for d in DEGREES if title.startswith(d)), None)
    rest = re.sub(r"^(?: in |: )", "", title[len(degree):]) if degree else title
    rest = rest.replace("Concentration in ", "").replace("&", "and")
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", rest).encode("ascii", "ignore").decode().lower()).strip("-")
    return f"{DEGREES[degree]}-{slug}" if degree else slug


def source_text(pages: list[str], numbers: list[int]) -> str:
    """The pages' text, one '=== p.NNNN ===' line before each (printed numbers), running head and page number dropped."""
    by_page = {printed(p): p for p in pages}
    parts = []
    for n in numbers:
        lines = clean(by_page[n])
        k = next((i for i, line in enumerate(lines[:5]) if HEAD.search(line)), None)
        if k is not None:  # the running head, wrapped or not (a left page's second head line stays: it's short)
            lines = lines[k + 1:]
        if lines and lines[-1].isdigit():
            lines = lines[:-1]
        parts.append(f"=== p.{n} ===\n" + "\n".join(lines))
    return "\n".join(parts) + "\n"


def source_pages(source: str) -> set[int]:
    return {int(n) for n in MARK.findall(source)}


def vocabulary() -> str:
    """ARCHITECTURE §6.2 (the rules vocabulary), the drafter's instructions."""
    text = ARCHITECTURE.read_text()
    return text[text.index("### 6.2"):text.index("### 6.3")]


def prompt(title: str, program: str, year: str, source: str, examples: list[str]) -> str:
    shown = "\n\n".join(f"```yaml\n{e}```" for e in examples)
    return f"""Draft the requirements of "{title}" from the {year} SF State Bulletin as a GatorPath rules YAML file.

Rules (they're checked by a program, then by a person):
- Use only the vocabulary below (ARCHITECTURE §6.2). Copy the shape of the hand-written examples.
- program: {program}; title: {title}; catalog_year: {year}; verified: false; verified_by: null.
- Every group gets `source: "p.NNNN"`, a page from the "=== p.NNNN ===" lines, and `quote`: the Bulletin's own words
  that group was written from, copied exactly (no paraphrase, no "...").
- Only course codes printed in the text, written as printed ("MATH 301GW"). Never add a course, a grade minimum or a
  unit count the text doesn't state. total_units is the printed major total (its minimum).
- A "Select One" between printed courses or bundles is `one_of`, one option each: [[MATH 209], [CSC 101, CSC 215]].
  The plan then schedules a real course, which a later course's prereq may need. "Select N units" / "N courses" from a
  list, and electives, are `choose_units`: the units the Bulletin prints for it (the Units column). Don't use choose_n
  in a program file: the planner reads it as a 0-unit designation. Electives "as needed to reach a total of N units"
  are `choose_units` (the printed minimum, 0 if none) with `fill_to_total: true`. A cross-listed course ("PH/ETHS 221") is one
  course under two codes: in a list to choose from, write each code (PH 221, ETHS 221); a required one is its own
  one_of group, one option per code ([[MUS 130], [TH A 131]]), never both codes in an all_of.
- Major requirements only: GE, SF State Studies and the university's graduation requirements are in other files.
  Include transfer_notes only when the text gives transfer advice; leave out `advising` and `dpr_plan`.
- Grading rules and unit limits over a program's courses (letter grades only, a CR/NC cap, a GPA floor, "no more than
  one course below C-", "30 units must be upper-division", "12 units at SF State") are check groups; a cap inside one
  list ("up to 9 units of lower-division") is a filter's max_units. A rule the university rules already state (a 2.0
  GPA in all coursework) needs no group.
- A requirement the vocabulary can't express exactly: a group with `unparsed: true`, its `quote` and `source`, and
  nothing else. Never approximate one.
- Answer with the YAML only, in one ```yaml block. Double-quote every string with a colon in it.

{vocabulary()}

Hand-written examples:

{shown}

The Bulletin text ({year}), page by page:

{source}"""


def roadmap_prompt(title: str, program: str, year: str, source: str, rules: str, labels: list[str],
                   examples: list[str]) -> str:
    shown = "\n\n".join(f"```yaml\n{e}```" for e in examples)
    return f"""Draft the roadmaps of "{title}" from the {year} SF State Bulletin as a GatorPath roadmap YAML file.

Rules (they're checked by a program, then by a person):
- Use only the roadmap vocabulary below (ARCHITECTURE §6.2, "Roadmap items"). Copy the shape of the hand-written examples.
- program: {program}; catalog_year: {year}; verified: false; verified_by: null.
- Variants, keyed {", ".join(VARIANTS)} only: a first-time roadmap per Quantitative Reasoning category (qr-1-2 with
  qr_pathway: "1/2", qr-3-4 with "3/4"), or first-time (no qr_pathway) when the program has one first-time roadmap;
  adt for the Associate Degree for Transfer roadmap (the first, when there are several). Leave out every other roadmap (5-year, 2-year transfer without
  an ADT, Scholars). Each variant: title (the printed heading), total_units (its last "Total Units" line, the minimum), source
  ("p.NNNN-NNNN", its pages), notes (the printed notes and footnotes, word for word), semesters.
- Each semester: units (the printed "Units" line; the minimum of a range), source ("p.NNNN"), items. The items' units
  must add up to it exactly: a course code counts its catalog units; a slot counts its `units`.
- Items: a course code as printed ("PH 400GW"); a GE requirement is {{slot: GE, area: <label>, units}} with the
  printed area (one of {", ".join(labels)}, or a label made of them like "1", "5UD/2UD"); American Institutions
  (USH, USG, CSLG) is {{slot: ai, area, units}}; "SF State Studies or University Elective" is
  {{slot: sfss_or_elective, units}}; "University Elective" or "Minor or Elective" is {{slot: elective, units}};
  a major choice ("Major Elective", "Concentration Elective", a "Select One" between courses that's a choose group of
  the program rules below) is {{slot: major, group: <that group's id>, units}}; a "Select One" of course codes or
  slots the rules don't make a group is {{one_of: [...], units}}. "Take Two" etc. go in the item's units (and a note).
- A cross-listed course ("MUS 130/TH A 131", "MUS/TH A 221") is its first code: MUS 130, MUS 221.
- Numbers printed between a title and its units are footnote marks, not units.
- Answer with the YAML only, in one ```yaml block. Double-quote every title, note and string with a colon in it.

{vocabulary()}

The program's rules (group ids for major slots):

```yaml
{rules}```

Hand-written examples:

{shown}

The Bulletin's roadmap pages ({year}), page by page:

{source}"""


def parse_draft(answer: str, key: str = "groups") -> dict:
    """The YAML in a ```yaml block (or the whole answer), as a mapping that has `key`. A title, quote, note or text whose
    colon a model left unquoted ("Bachelor of Music: Concentration in Composition Roadmap", "Select One: 3") is quoted
    first: each is one line of plain text."""
    m = re.search(r"```(?:yaml)?\n(.*?)```", answer, re.S)
    text = re.sub(r"^(\s*(?:- )?(?:title|quote|note|text): )(?![\"'|>\[{])(.*:.*)$",
                  lambda t: t[1] + json.dumps(t[2], ensure_ascii=False),
                  m.group(1) if m else answer, flags=re.M)
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or key not in data:
        raise ValueError(f"the answer isn't a rules file with {key}")
    return data


def read_draft(path: Path, key: str, stamp: dict) -> dict:
    """A draft file as a mapping. One kept as the client's raw answer (it wasn't YAML) is parsed with parse_draft's
    repairs, stamped like a draft, and rewritten as YAML; ValueError / YAMLError when it still can't be read."""
    text = path.read_text()
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict) and key in data:
            return data
    except yaml.YAMLError:
        pass
    data = parse_draft(text, key) | stamp | {"verified": False, "verified_by": None,
                                            "drafted_by": f"{CLIENT.split()[0]}, {date.fromtimestamp(path.stat().st_mtime)}"}
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
    return data


def ask(client: str, text: str, key: str, keep: Path | None = None) -> dict:
    """One headless AI-client run: the prompt on stdin, the YAML out, stamped never verified. The answer is written to
    `keep` first, so one that isn't YAML is there for a person to fix instead of lost."""
    run = subprocess.run(shlex.split(client), input=text, capture_output=True, text=True)
    if run.returncode:  # a usage limit, a network error: reported for this program, the batch goes on
        raise RuntimeError(f"the client exited {run.returncode}: {(run.stderr or run.stdout).strip()[:200]}")
    answer = run.stdout
    if keep:
        keep.write_text(answer)
    name = next(w for w in shlex.split(client) if w != "env" and "=" not in w)  # "env CODEX_HOME=… codex exec" -> codex
    return parse_draft(answer, key) | {"verified": False, "verified_by": None, "drafted_by": f"{name}, {date.today().isoformat()}"}


def hand_written(kind: str, year: str, program: str) -> list[str]:
    """The examples a draft is shown: the hand-written files only (never another draft: they'd multiply the prompt as
    programs load, and teach the drafter its own mistakes), and never the program being drafted."""
    return [t for p in sorted((RULES_DIR / kind / year).glob("*.yaml"))
            if p.stem != program and "drafted_by:" not in (t := p.read_text())]


def draft(title: str, program: str, year: str, source: str, client: str = CLIENT, keep: Path | None = None) -> dict:
    """A program's rules. Fields a model mustn't set are overwritten."""
    examples = hand_written("programs", year, program)
    data = ask(client, prompt(title, program, year, source, examples), "groups", keep)
    return data | {"program": program, "title": title, "catalog_year": year}


def draft_roadmap(title: str, program: str, year: str, source: str, rules: str, university: dict,
                  client: str = CLIENT, keep: Path | None = None) -> dict:
    """A program's roadmaps, written against its rules (`rules`: the YAML text, for the major groups' ids)."""
    examples = hand_written("roadmaps", year, program)
    labels = sorted({a for g in university["groups"] for a in ge_areas(g)})
    data = ask(client, roadmap_prompt(title, program, year, source, rules, labels, examples), "variants", keep)
    return {"program": program, "catalog_year": year} | data | {"program": program, "catalog_year": year}


def codex_client(work: Path) -> str:
    """Codex CLI as a second, independent drafter: the prompt only. A clean CODEX_HOME (the user's login and model, no MCP
    server, which would hand it our rules; no web search, no shell) and an empty working directory."""
    home, cwd = work / "codex_home", work / "codex_cwd"
    for d in (home, cwd):
        d.mkdir(parents=True, exist_ok=True)
    if not (home / "auth.json").exists():
        (home / "auth.json").symlink_to(Path.home() / ".codex/auth.json")  # the user's own login, never copied
    user = Path.home() / ".codex/config.toml"
    model = "".join(l + "\n" for l in (user.read_text().splitlines() if user.exists() else [])
                    if re.match(r"(model|model_reasoning_effort)\s*=", l))
    off = "".join(f"{f} = false\n" for f in ("apps", "browser_use", "browser_use_external", "in_app_browser", "shell_tool",
                                             "skill_search"))
    (home / "config.toml").write_text(f'{model}web_search = "disabled"\n[features]\n{off}')
    return f"env CODEX_HOME={home} codex exec --skip-git-repo-check -s read-only -C {cwd} --ephemeral -"


def comparable(g: dict) -> bool:
    """A course group two drafts can be compared on: not unparsed, not one only an advisor's approval fills."""
    return not g.get("unparsed") and not approval_only(g) and "across" not in g


def student(program: dict, university: dict, catalog: dict, last: bool = False) -> list[dict]:
    """Completed rows (grade B) meeting every comparable group of `program`: each required course, the first (or last)
    option of each Select One, and each choice filled from its lists, then the catalog, in code order (or reversed)."""
    rows, have = [], set()

    def add(c: str) -> bool:
        if c in catalog and c not in have:
            have.add(c)
            rows.append({"code": c, "grade": "B", "term": "2027-fall"})
            return True
        return False

    groups = [g for g in program["groups"] if comparable(g)]
    for g in groups:
        for c in g.get("all_of", []) + (g["one_of"][-1 if last else 0] if "one_of" in g else []):
            add(c)
    pools = {}
    for g in groups:
        if "from" in g:
            fs = filters_for(g, {})
            pool = list(dict.fromkeys([c for f in fs for c in f.get("list", [])]
                                      + sorted(c for c in catalog if any(matches(f, c, catalog[c]) for f in fs))))
            pools[g["id"]] = pool[::-1] if last else pool
    for _ in range(60):  # one course per open choice at a time, until the audit says each is met
        got = {x["id"]: x for x in audit({"catalog_year": program["catalog_year"], "completed": rows}, program, university,
                                         catalog)["groups"]}
        if not [add(next((c for c in pools[i] if c not in have), "")) for i in pools if got[i]["status"] != "satisfied"]:
            break
    return rows


def unmet(rows: list[dict], program: dict, university: dict, catalog: dict) -> list[str]:
    """What keeps `rows` from completing the program's comparable groups (and its check groups: one broken)."""
    by = {g["id"]: g for g in program["groups"]}
    out = []
    for x in audit({"catalog_year": program["catalog_year"], "completed": rows}, program, university, catalog)["groups"]:
        g = by.get(x["id"])
        if x["kind"] != "major" or g is None or (not comparable(g) and "across" not in g):
            continue
        if x["status"] == "remaining" if "across" in g else x["status"] not in ("satisfied", "waived"):
            out.append(x["title"] + (f" (still {', '.join(x['remaining'])})" if x.get("remaining") else ""))
    return out


def cross_check(ours: dict, theirs: dict, university: dict, catalog: dict, names: tuple = ("ours", "theirs")) -> list[str]:
    """Two drafts of one program, compared on made-up students: one who completes each (first and last options), then
    that student with one course at CR, D or C-. A student the two judge differently is a disagreement for a person,
    with the requirements that say no; for a changed grade, only what the grade adds. [] when they agree on every one.
    Unparsed and approval-only groups aren't compared."""
    out = [f"total_units: {names[0]} {ours.get('total_units')}, {names[1]} {theirs.get('total_units')}"] \
        if ours.get("total_units") != theirs.get("total_units") else []
    versions = dict(zip(names, (ours, theirs)))
    judge = lambda rows: {n: unmet(rows, p, university, catalog) for n, p in versions.items()}
    says = lambda why: "; ".join(f"{n}: " + (f"not done, {', '.join(w)}" if w else "done") for n, w in why.items())
    found: dict[tuple, list[str]] = {}
    for name, program in versions.items():
        for last in (False, True):
            base = student(program, university, catalog, last)
            first = judge(base)
            if bool(first[names[0]]) != bool(first[names[1]]):
                found.setdefault(("", says(first)), []).append(f"a student completing the {name} draft")
            for r in base:
                for grade in ("CR", "D", "C-"):
                    then = judge([x | {"grade": grade} if x is r else x for x in base])
                    added = {n: [re.sub(r" \(still .*\)$", "", w) for w in then[n] if w not in first[n]] for n in names}
                    if bool(added[names[0]]) != bool(added[names[1]]):
                        found.setdefault((grade, says(added)), []).append(r["code"])
    return out + [f"{', '.join(dict.fromkeys(who))}{' at ' + grade if grade else ''}: {why}"
                  for (grade, why), who in found.items()]


def try_plans(program: dict, roadmap: dict, university: dict, catalog: dict, prereqs: dict) -> list[str]:
    """build_plan for a new student on each variant (an ADT transfer on `adt`), as check_plan sees it: the end-to-end
    check that a drafted program and roadmap can be planned at all."""
    out = []
    for key, v in roadmap.get("variants", {}).items():
        profile = {"program": program["program"], "catalog_year": program["catalog_year"], "start_term": "2027-fall",
                   "completed": []} | ({"qr_pathway": v["qr_pathway"]} if v.get("qr_pathway") else {}) | (
                      {"adt": True} if key == "adt" else {})
        plan = build_plan(profile, program, university, roadmap, catalog, prereqs)
        if "check" not in plan:
            out.append(f"plan {key}: none ({plan.get('needs_input') or plan.get('error')})")
            continue
        stopped = [w for w in plan["warnings"] if w.startswith("Stopped")]
        out.append(f"plan {key}: {'valid' if plan['check']['valid'] else 'INVALID'}, {len(plan['semesters'])} terms"
                   + "".join(f"\n    {e['message']}" for e in plan["check"]["errors"]) + "".join(f"\n    {w}" for w in stopped))
    return out


# check_program / check_roadmap lines a loaded draft may still carry: requirements left for a person, flagged
LOADABLE = ("unparsed, a person writes", "units: can't check total_units", "is unparsed in the program rules",
            "aren't in any variant")
HEADER = ("# AI-drafted from the {year} Bulletin text ({source}) by {drafted_by}; checked by check_program, check_roadmap\n"
          "# and a test plan per variant (ingest.programs --load). verified: false until a person checks it against\n"
          "# the PDF (AGENTS.md, \"Adding or changing a program's rules\").\n")


def load(pid: str, year: str, catalog: dict, prereqs: dict, university: dict, pages: dict) -> list[str]:
    """Move a draft and its roadmap into rules/ when nothing but flagged requirements is left and a new student's plan
    passes check_plan on every variant. [] when it moved; else what keeps it in rules/drafts/."""
    d, rules = RULES_DIR / "drafts" / year, RULES_DIR / "programs" / year
    home = d if (d / f"{pid}.yaml").exists() else rules  # a redrafted roadmap for a loaded program uses its rules
    stamp = {"program": pid, "catalog_year": year}
    try:
        program = read_draft(home / f"{pid}.yaml", "groups", stamp | {"title": pages[pid]["title"]})
        roadmap = read_draft(d / f"{pid}.roadmap.yaml", "variants", stamp)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
        return [f"no readable draft and roadmap ({type(e).__name__})"]
    if not program.get("drafted_by"):
        return ["hand-written rules: --load only moves AI drafts"]
    source, road_source = (home / f"{pid}.source.txt").read_text(), (d / f"{pid}.roadmap.source.txt").read_text()
    problems = check_program(program, catalog, set(pages[pid]["pages"]), source) + check_roadmap(
        roadmap, program, university, catalog, set(pages[pid]["roadmap_pages"]), road_source)
    problems = [x for x in problems if not any(k in x for k in LOADABLE)]
    problems += [x.split("\n")[0] for x in try_plans(program, roadmap, university, catalog, prereqs)
                 if ": valid," not in x.split("\n")[0]]
    if problems:
        return problems
    head = HEADER.format(year=year, source=f"{pid}.source.txt", drafted_by=program.get("drafted_by", "an AI client"))
    for kind, data, text in (("programs", program, source), ("roadmaps", roadmap, road_source)):
        out = RULES_DIR / kind / year
        (out / f"{pid}.yaml").write_text(head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
        (out / (f"{pid}.source.txt")).write_text(text)
    for f in (f"{pid}.yaml", f"{pid}.roadmap.yaml", f"{pid}.source.txt", f"{pid}.roadmap.source.txt"):
        (d / f).unlink(missing_ok=True)
    return []


def coverage(rules: list[dict], listed: int) -> list[str]:
    """How much of the served rules GatorPath checks itself (the goal: 90%, a person the other 10%). A person's: an
    unparsed group, and a group only an advisor's approval fills."""
    groups = [(p["program"], g) for p in rules for g in p["groups"]]
    unparsed = [x for x in groups if x[1].get("unparsed")]
    approved = [x for x in groups if approval_only(x[1])]
    left = Counter(pid for pid, _ in unparsed + approved)
    person = left.total()
    pct = lambda n: f"{100 * n / len(groups):.1f}%"
    return [f"programs served: {len(rules)} of {listed} in the Bulletin",
            f"requirement groups: {len(groups)}; GatorPath checks {len(groups) - person} ({pct(len(groups) - person)}); "
            f"a person {person} ({pct(person)}): {len(unparsed)} unparsed, {len(approved)} an advisor approves",
            f"programs with nothing for a person: {sum(1 for p in rules if not left[p['program']])}",
            "most for a person: " + ", ".join(f"{pid} {n}" for pid, n in left.most_common(10))]


def main() -> None:
    ap = argparse.ArgumentParser(description="List the Bulletin's bachelor's programs, write their source text, draft "
                                             "rules YAML with an AI client, and check program files.")
    ap.add_argument("pdf")
    ap.add_argument("--year", help="catalog year, e.g. 2026-27 (default: read from the file name)")
    ap.add_argument("--source", nargs="*", metavar="ID", help="write <id>.source.txt (no ids: every program with rules)")
    ap.add_argument("--draft", nargs="+", metavar="ID", help="draft rules/drafts/<year>/<id>.yaml with --client")
    ap.add_argument("--roadmap", nargs="+", metavar="ID", help="draft rules/drafts/<year>/<id>.roadmap.yaml with --client, "
                                                               "against the program's rules (or its draft)")
    ap.add_argument("--load", nargs="*", metavar="ID", help="move drafts that pass the checks and a test plan into "
                                                             "rules/ (no ids: every draft)")
    ap.add_argument("--coverage", action="store_true", help="how much of the served rules GatorPath checks vs a person")
    ap.add_argument("--cross", nargs="+", metavar="ID", help="a second, independent draft of served programs (default "
                                                              "client: Codex CLI) compared on made-up students")
    ap.add_argument("--client", default=None, help=f"headless AI client, prompt on stdin (default: {CLIENT})")
    ap.add_argument("--db", default="data/catalog.db")
    args = ap.parse_args()
    year = args.year or re.search(r"\d{4}-\d{2}", Path(args.pdf).name).group()
    pages = extract_pages(args.pdf)
    have = {yaml.safe_load(p.read_text())["title"]: p.stem for p in (RULES_DIR / "programs" / year).glob("*.yaml")}
    programs = {program_id(p["title"], have): p for p in index(pages)}
    if args.coverage:
        print("\n".join(coverage([yaml.safe_load(f.read_text()) for f in sorted((RULES_DIR / "programs" / year).glob("*.yaml"))],
                                  len(programs))))
        return
    client = args.client or CLIENT
    if args.source is None and not args.draft and not args.roadmap and args.load is None and not args.cross:
        print(json.dumps([{"id": i, **p, "has_rules": p["title"] in have} for i, p in programs.items()], indent=1))
        return
    if unknown := [i for i in (args.source or []) + (args.draft or []) + (args.roadmap or []) + (args.load or [])
                   + (args.cross or [])
                   if i not in programs]:
        ap.error(f"unknown program id {', '.join(unknown)}; run with only the PDF to list them")
    catalog = db.load_catalog(args.db, year)
    for pid in (args.source or [i for i, p in programs.items() if p["title"] in have]) if args.source is not None else []:
        # next to the rules; a program without rules yet keeps it with its drafts
        path = RULES_DIR / ("programs" if programs[pid]["title"] in have else "drafts") / year / f"{pid}.source.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source_text(pages, programs[pid]["pages"]))
        print(f"{path} ({len(programs[pid]['pages'])} pages)")
    for pid in args.draft or []:
        p = programs[pid]
        source = source_text(pages, p["pages"])
        out = RULES_DIR / "drafts" / year
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{pid}.source.txt").write_text(source)
        try:
            data = draft(p["title"], pid, year, source, client, out / f"{pid}.yaml")
        except RuntimeError as e:
            print(f"{pid}: no draft, {e}")
            continue
        except (ValueError, yaml.YAMLError) as e:
            print(f"{out / f'{pid}.yaml'}: the answer isn't a rules file, fix it by hand ({str(e).splitlines()[0]})")
            continue
        (out / f"{pid}.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
        problems = check_program(data, catalog, set(p["pages"]), source)
        print(f"{out / f'{pid}.yaml'}: {len(problems)} to fix" + "".join(f"\n  {x}" for x in problems))
    university = yaml.safe_load((RULES_DIR / "university" / f"{year}.yaml").read_text())
    for pid in args.roadmap or []:
        p, out = programs[pid], RULES_DIR / "drafts" / year
        rules = next((f for f in (RULES_DIR / "programs" / year / f"{pid}.yaml", out / f"{pid}.yaml") if f.exists()), None)
        if rules is None:
            ap.error(f"{pid} has no rules or draft yet: run --draft {pid} first")
        if not p["roadmap_pages"]:
            print(f"{pid}: no roadmap pages in the Bulletin; nothing to draft")
            continue
        try:  # before spending a call: a draft kept as the raw answer is repaired, or reported
            program = read_draft(rules, "groups", {"program": pid, "title": p["title"], "catalog_year": year})
        except (ValueError, yaml.YAMLError):
            print(f"{rules}: isn't YAML yet, fix it before drafting its roadmap")
            continue
        source = source_text(pages, p["roadmap_pages"])
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{pid}.roadmap.source.txt").write_text(source)
        try:
            data = draft_roadmap(p["title"], pid, year, source, rules.read_text(), university, client,
                                 out / f"{pid}.roadmap.yaml")
        except RuntimeError as e:
            print(f"{pid}: no roadmap draft, {e}")
            continue
        except (ValueError, yaml.YAMLError) as e:
            print(f"{out / f'{pid}.roadmap.yaml'}: the answer isn't a roadmap file, fix it by hand ({str(e).splitlines()[0]})")
            continue
        (out / f"{pid}.roadmap.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
        problems = check_roadmap(data, program, university, catalog, set(p["roadmap_pages"]), source)
        print(f"{out / f'{pid}.roadmap.yaml'}: {len(problems)} to fix" + "".join(f"\n  {x}" for x in problems)
              + "".join(f"\n  {x}" for x in try_plans(program, data, university, catalog, db.load_prereqs(args.db, year))))

    for pid in args.cross or []:  # a second draft from another client, compared with the served rules
        served, out = RULES_DIR / "programs" / year, RULES_DIR / "drafts" / year / "cross"
        if not (served / f"{pid}.yaml").exists():
            print(f"{pid}: not served, nothing to cross-check")
            continue
        out.mkdir(parents=True, exist_ok=True)
        p, source, second = programs[pid], (served / f"{pid}.source.txt").read_text(), out / f"{pid}.yaml"
        who = args.client or codex_client(RULES_DIR.parent / "data")
        try:  # an earlier second draft is reused: delete it to draft again
            data = read_draft(second, "groups", {"program": pid, "title": p["title"], "catalog_year": year}) \
                if second.exists() else draft(p["title"], pid, year, source, who, second)
        except RuntimeError as e:
            print(f"{pid}: no second draft, {e}")
            continue
        except (ValueError, yaml.YAMLError) as e:
            print(f"{second}: the answer isn't a rules file, fix it by hand ({str(e).splitlines()[0]})")
            continue
        second.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
        problems = check_program(data, catalog, set(p["pages"]), source)
        name = data.get("drafted_by", "second").split(",")[0]
        diff = cross_check(yaml.safe_load((served / f"{pid}.yaml").read_text()), data, university, catalog, ("ours", name))
        print(f"{pid}: " + ("agree on every made-up student" if not diff else f"{len(diff)} disagreement(s)")
              + "".join(f"\n  {x}" for x in diff)
              + (f"\n  ({name}'s draft has {len(problems)} check_program problem(s), "
                 f"{sum(1 for g in data['groups'] if g.get('unparsed'))} unparsed group(s))" if problems else ""))

    if args.load is not None:
        prereqs = db.load_prereqs(args.db, year)
        ids = args.load or sorted({p.name.split(".")[0] for p in (RULES_DIR / "drafts" / year).glob("*.yaml")})
        for pid in ids:
            why = load(pid, year, catalog, prereqs, university, programs)
            print(f"{pid}: " + ("loaded into rules/ (verified: false)" if not why else "stays a draft"
                                + "".join(f"\n  {x}" for x in why)))


if __name__ == "__main__":
    main()
