"""Bulletin program pages -> source text -> AI-drafted rules YAML -> check_program (ARCHITECTURE §6.2, D5). Offline: the
server never calls a model (D6), and a draft stays in rules/drafts/ until a person reviews it."""

import argparse
import json
import re
import shlex
import subprocess
import unicodedata
from datetime import date
from pathlib import Path

import yaml

from gatorpath import db
from gatorpath.engine.rules import RULES_DIR, check_program
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
    lines = clean(page)[:3]
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
        while (h := at(n)) and h.startswith(t):
            road.append(n)
            n += 1
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
        k = next((i for i, line in enumerate(lines[:3]) if HEAD.search(line)), None)
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
- A "Select One" / "select N units" / "N courses" choice in the major is `choose_units`: the units the Bulletin prints
  for it (the Units column). Don't use choose_n in a program file: the planner reads it as a 0-unit designation.
  A choice between bundles ("CSC 101 & CSC 215") is `one_of`. A cross-listed course ("PH/ETHS 221") is each of its
  codes: PH 221, ETHS 221.
- Major requirements only: GE, SF State Studies and the university's graduation requirements are in other files.
  Include transfer_notes only when the text gives transfer advice; leave out `advising` and `dpr_plan`.
- A requirement the vocabulary can't express exactly: a group with `unparsed: true`, its `quote` and `source`, and
  nothing else. Never approximate one.
- Answer with the YAML only, in one ```yaml block.

{vocabulary()}

Hand-written examples:

{shown}

The Bulletin text ({year}), page by page:

{source}"""


def parse_draft(answer: str) -> dict:
    """The YAML in a ```yaml block (or the whole answer), as a mapping."""
    m = re.search(r"```(?:yaml)?\n(.*?)```", answer, re.S)
    data = yaml.safe_load(m.group(1) if m else answer)
    if not isinstance(data, dict) or "groups" not in data:
        raise ValueError("the answer isn't a rules file with groups")
    return data


def draft(title: str, program: str, year: str, source: str, client: str = CLIENT) -> dict:
    """One headless AI-client run: the prompt on stdin, the YAML out. Fields a model mustn't set are overwritten."""
    examples = [p.read_text() for p in sorted((RULES_DIR / "programs" / year).glob("*.yaml")) if p.stem != program]
    answer = subprocess.run(shlex.split(client), input=prompt(title, program, year, source, examples), capture_output=True,
                            text=True, check=True).stdout
    data = parse_draft(answer)
    return data | {"program": program, "title": title, "catalog_year": year, "verified": False, "verified_by": None,
                   "drafted_by": f"{shlex.split(client)[0]}, {date.today().isoformat()}"}


def main() -> None:
    ap = argparse.ArgumentParser(description="List the Bulletin's bachelor's programs, write their source text, draft "
                                             "rules YAML with an AI client, and check program files.")
    ap.add_argument("pdf")
    ap.add_argument("--year", help="catalog year, e.g. 2026-27 (default: read from the file name)")
    ap.add_argument("--source", nargs="*", metavar="ID", help="write <id>.source.txt (no ids: every program with rules)")
    ap.add_argument("--draft", nargs="+", metavar="ID", help="draft rules/drafts/<year>/<id>.yaml with --client")
    ap.add_argument("--client", default=CLIENT, help=f"headless AI client, prompt on stdin (default: {CLIENT})")
    ap.add_argument("--db", default="data/catalog.db")
    args = ap.parse_args()
    year = args.year or re.search(r"\d{4}-\d{2}", Path(args.pdf).name).group()
    pages = extract_pages(args.pdf)
    have = {yaml.safe_load(p.read_text())["title"]: p.stem for p in (RULES_DIR / "programs" / year).glob("*.yaml")}
    programs = {program_id(p["title"], have): p for p in index(pages)}
    if args.source is None and not args.draft:
        print(json.dumps([{"id": i, **p, "has_rules": p["title"] in have} for i, p in programs.items()], indent=1))
        return
    if unknown := [i for i in (args.source or []) + (args.draft or []) if i not in programs]:
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
        data = draft(p["title"], pid, year, source, args.client)
        (out / f"{pid}.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
        problems = check_program(data, catalog, set(p["pages"]), source)
        print(f"{out / f'{pid}.yaml'}: {len(problems)} to fix" + "".join(f"\n  {x}" for x in problems))


if __name__ == "__main__":
    main()
