# GatorPath — Tasks

Phased checklist. Each phase has a **Done when**. Finish phases in order; don't start a phase
until the previous one's "Done when" is true. Design details: `docs/ARCHITECTURE.md`.

Legend: `[ ]` todo · `[x]` done · `(?)` needs a decision first

---

## Phase 0 — Foundation

- [x] Create repo `~/Projects/gatorpath`
- [x] Write `docs/ARCHITECTURE.md`, `AGENTS.md`, `TASKS.md`, `README.md`
- [x] Review + approve the architecture doc
- [x] Install tools: `brew install uv poppler`
- [x] `uv init` → `pyproject.toml` with deps: `mcp`, `pyyaml`, `httpx`, `beautifulsoup4`; dev: `pytest`
- [x] Put the Bulletin PDF at `data/raw/bulletin-2026-27.pdf` (git-ignored)
- [x] Create a GitHub repo (private until phase 7) and push: github.com/ashleytzele/gatorpath
- [x] GitHub Actions: run `pytest` on push (`.github/workflows/test.yml`)

**Done when:** `uv run pytest` passes (even with zero tests) locally and in CI.

---

## Phase 1 — Catalog: Bulletin → courses + prereqs

- [x] `ingest/bulletin.py`: extract with `pdftotext -raw` (default mode interleaves columns)
- [x] Parse course headers: `CODE Title (Units: N)` / `(Units: 1-3)` → `course`
- [x] Capture description, grading notes ("Plus-minus letter grade only", "CR/NC grading only")
- [x] Record `source_page` (the **printed** page number, from the footer) for every course
- [x] Dedupe: each course is printed in its department section and again in the A–Z catalog.
  Keep one row per `code`; warn if the texts differ
- [x] Parse `Course Attributes:` bullets → `course.ge_areas` (GE areas, AERM/ESCA/GP/SJ, USH/USG,
  GWAR)
- [x] Prereq parser → expression tree (ARCHITECTURE §6.3), with status `ok`/`partial`/`unparsed`
  - [x] course codes, `and`/`or`/`;`, "with a grade of C or better"
  - [x] standing (upper-division, senior, graduate)
  - [x] GPA conditions
  - [x] "may be taken concurrently"
  - [x] "permission of the instructor/department" → `permission` leaf
  - [x] "Restricted to … majors" → `restricted_to` leaf
  - [x] Paired-course entries ("Prerequisites for CSC 671: …" inside CSC 871)
- [x] `course_link` for paired (671/871) and cross-listed (HUM 690/CWL 680) courses
- [ ] Asterisk (`CSC 510*`): no legend in the PDF. Parse as the plain course + ⚠️ with raw text;
  ask the CS department (ARCHITECTURE §16.1)
- [x] Golden test file: 64 real prereq strings from CSC/MATH/PHYS → expected trees (`tests/test_prereq.py`)
- [x] Coverage report: printed by `python -m gatorpath.ingest.bulletin <pdf>`; lists every non-ok string
  and every referenced code missing from the catalog (e.g. renumbered CSC 210)
- [x] Coverage 95.5% (234/245; CSC 99.0%, MATH 92.4%, PHYS 94.5%). The 11 non-ok are listed by the
  report (ambiguous MATH 742/760/761; LA, thesis and degree-status text)

**Done when:** CSC, MATH and PHYS prereqs are ≥ 95% `ok`, and every non-ok one is listed in the
report.

---

## Phase 2 — Rules: BS CS + GE + university requirements, roadmaps, audit

- [ ] `rules/programs/2026-27/bs-cs.yaml` from Bulletin p.1905 (all 4 groups, global grade
  rules, page sources)
- [ ] `rules/university/2026-27.yaml`: GE areas (43 units, p.2311 table), SF State Studies,
  American Institutions, GWAR (C-), unit/residence/CR/GPA totals (p.2313)
- [ ] `rules/roadmaps/2026-27/bs-cs.yaml`: variants `qr-1-2`, `qr-3-4`, `transfer-2yr`, `adt`
- [ ] Second person double-checks both files against the PDF → set `verified: true`
- [ ] `engine/rules.py`: load YAML, evaluate `all_of`, `choose_units`, `from` filters, `except`,
  `max_courses`, `min_units_from`, `min_grade`, `no_cr_nc`
- [ ] Double-counting per ARCHITECTURE §6.2 (once within the major; GE/SFSS/AI may overlap;
  major↔UD GE allowed with ⚠️ until §16.7 is answered)
- [ ] Repeats: best attempt counts, units once, ⚠️ on 2nd/3rd attempt (§16.5)
- [ ] University totals: 120 units, upper-division units, residence, CR cap, GPA
- [ ] 10 synthetic student profiles in `evals/profiles/` with hand-computed audits (major + GE) →
  tests

**Done when:** all 10 audits (major and GE) match the hand-computed answers.

---

## Phase 3 — MCP server v0 (read-only)

- [ ] `server.py` with FastMCP: `search_courses`, `get_course`, `get_prereq_chain`,
  `list_programs`, `get_program_requirements`, `get_roadmap`, `audit_progress`
- [ ] FTS5 index for `search_courses`
- [ ] Add to Claude Desktop config; try 10 real questions; write down what felt wrong
- [ ] Also try Gemini CLI (proves "works with any client")

**Done when:** you can ask Claude "what do I need before CSC 653?" and "what's left for my
degree?" and get correct, sourced answers.

---

## Phase 4 — Planner

- [ ] `engine/planner.py::check_plan`: all errors/warnings from ARCHITECTURE §7.3
- [ ] `build_plan`: critical-path priority + term-by-term greedy (ARCHITECTURE §8)
- [ ] Return `needs_input: qr_pathway` when it's missing
- [ ] `list_eligible_electives` with readiness (`ready` / `ready_by` / `blocked_by`)
- [ ] MCP prompt `plan_my_degree` (ARCHITECTURE §7.4)
- [ ] Test: every `build_plan` output passes `check_plan` for all eval profiles
- [ ] Test: the cybersecurity case schedules CSC 415 before CSC 652/653

**Done when:** "I'm a CS sophomore, I want cybersecurity, plan my next 3 years" produces a plan
that passes `check_plan`, with sensible electives.

---

## Phase 5 — Offering history

- [ ] (?) Check SFSU class-search terms of use
- [ ] `ingest/offerings.py`: session + CSRF token, one search per subject per term, cache HTML,
  ≥ 2 s between requests
- [ ] Scrape CSC, MATH and PHYS for the last 4 years (fall/spring/summer)
- [ ] `offered_terms` view; planner uses it; `get_course` shows it
- [ ] Spot-check 5 courses by hand against the website

**Done when:** the planner never places a fall-only course in spring without a warning.

---

## Phase 6 — Transcript import

- [x] Get the unofficial transcript layout (`SSR_TSRPT`); synthetic fixture at
  `tests/fixtures/transcript_synthetic.txt` (ARCHITECTURE §7.3)
- [ ] Get a sample with CR / W / I / repeat / summer rows (redacted or rebuilt synthetic)
- [ ] `transcript.py`: `pdftotext -layout` → extract (term, code, units, grade) rows; drop
  everything else; transfer blocks → `transfer_units` + ⚠️
- [ ] In-progress courses (no grade yet) → `in_progress`
- [ ] Test: the fake name/ID strings in the fixture never appear in the output
- [ ] `import_transcript` tool

**Done when:** importing the synthetic transcript gives the same audit as typing the courses.

---

## Phase 7 — Evals, demo, first users

- [ ] 30–50 eval questions (`evals/`), each with a profile + goal + expected properties
- [ ] `run_evals.py`: run through a real AI client + server; score validity, goal-fit (rubric),
  hallucinated codes
- [ ] README: problem, demo GIF/video (2 min), setup in 3 commands, eval table, limitations
- [ ] Make the repo public (MIT); credit GatorWay/Plan-Ed as prior art
- [ ] 5–10 SFSU classmates try it; collect feedback; fix the top 3 issues
- [ ] Write the resume bullet with real numbers

**Done when:** the public repo has a demo, an eval table, and real user feedback.

---

## Phase 8 — Expand

- [ ] BS Mathematics rules + roadmaps (verified)
- [ ] `compare_programs(profile, target)`: what counts, what's left, extra semesters
- [ ] Offline AI-draft pipeline: Bulletin program page → draft YAML → human review →
  `verified: true`
- [ ] Load all programs as `verified: false`

---

## Later (not planned yet)

- Transfer credit: ASSIST (CA community colleges); out-of-state similarity + Course Equivalency
  Request drafting
- Week-level schedule builder from live class-search sections
- Web roadmap UI on top of the same MCP server
- Other catalog years (2025-26, 2027-28)
- Pitch to SFSU Advising / Registrar for a pilot
