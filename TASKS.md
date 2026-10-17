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

- [x] `rules/programs/2026-27/bs-cs.yaml` from Bulletin p.1905 (all 4 groups, global grade
  rules, page sources)
- [x] `rules/university/2026-27.yaml`: GE areas (43 units, p.2311 table), SF State Studies,
  American Institutions, GWAR (C-), unit/residence/CR/GPA totals (p.2313)
- [x] `rules/roadmaps/2026-27/bs-cs.yaml`: variants `qr-1-2`, `qr-3-4`, `adt` (the Bulletin's
  "Transfer Student Roadmap (2 Year)" is the ADT roadmap, p.1906 → p.1912)
- [ ] Second person double-checks all three files against the PDF → set `verified: true`
- [x] `engine/rules.py`: load YAML, evaluate `all_of`, `choose_units`, `from` filters, `except`,
  `max_courses`, `min_units_from`, `min_grade`, `no_cr_nc` (+ `waived_if`, `distinct_subjects`)
- [x] Double-counting per ARCHITECTURE §6.2 (once within the major; GE/SFSS/AI may overlap;
  major↔GE allowed, p.2352, so §16.7 is closed)
- [x] Repeats: best attempt counts, units once, ⚠️ on 2nd/3rd attempt (§16.5)
- [x] University totals: 120 units, upper-division units, residence, CR cap, GPA
- [x] 10 synthetic student profiles in `evals/profiles/` with hand-computed audits (major + GE) →
  tests (`tests/test_rules.py`, catalog rows in `evals/catalog-2026-27.json`)
- [x] Fix from phase 1: paired notes with "[formerly …]" (CSC 852/652) weren't linked

**Done when:** all 10 audits (major and GE) match the hand-computed answers.

---

## Phase 3 — MCP server v0 (read-only)

- [x] `server.py` (mcp 2.x renamed FastMCP to `MCPServer`): `search_courses`, `get_course`, `get_prereq_chain`,
  `list_programs`, `get_program_requirements`, `get_roadmap`, `audit_progress`. Tested over a fixture
  catalog.db of real Bulletin rows (`tests/fixtures/catalog_rows.json`) and end to end over stdio
- [x] FTS5 index for `search_courses` (`course_fts`, built by `ingest.bulletin`; rebuild catalog.db once)
- [x] Add to Claude Desktop config (done 2026-10-16)
- [ ] Try 10 real questions; write down what felt wrong. Found so far (1, a transfer student's transcript):
  - [x] Audit silently used 2026-27 for a Spring 2025 student → ⚠️ when `catalog_year` is missing
  - [x] Model guessed what 46 transfer units covered → audit ⚠️ + server instructions: never guess
    transfer coverage or graduation terms
  - [ ] Model estimated "finish Spring/Fall 2027" with no planner → phase 4 `build_plan`
  - [ ] Transcript was attached to the chat directly (PII to the provider) → phase 6 `import_transcript` / `import_dpr`
  - Trial 2 (same student, DPR + build/check_plan): two-semester plan matched the student's own;
    claims checked against the Bulletin (ENVS 401 = ESCA + 4UD + GP, CSC 656 with CSC 415 concurrently).
    Gaps: validated against 2026-27 while the student is on Spring 2025; no offering data; GEOG 575's
    "GE Area E" prereq vs the 3/12/25 Area E waiver went unflagged
- [ ] Also try Gemini CLI (proves "works with any client")

**Done when:** you can ask Claude "what do I need before CSC 653?" and "what's left for my
degree?" and get correct, sourced answers.

---

## Phase 4 — Planner

- [x] `engine/planner.py::check_plan` + `check_plan` tool: prereqs by term (tri-state: ok / not met /
  can't verify; "or permission" never rescues a plan), corequisites, class level (p.2390), restrictions,
  repeats/duplicates, unit cap + normal load (p.2393), requirement coverage with slots, 120/UD totals.
  Offering-season checks wait for phase 5
- [x] `build_plan`: critical-path priority + term-by-term greedy (ARCHITECTURE §8); corequisites together;
  roadmap pathway courses (QR 3/4: MATH 197 → 198 → 226); slots for GE / senior electives / free units;
  CR or C-or-better major courses that can't count or be repeated → ⚠️ see an advisor
- [x] Return `needs_input: qr_pathway` (and `start_term`) when it's missing
- [x] `list_eligible_electives` with readiness (`ready` / `check` / `blocked` + `blocked_by`, `ready_by` from
  a plan) and the Bulletin description of each option
  - [x] Rank options by how many **open** requirements one course covers ("triple duty": ENVS 401 /
    LS 401 = 4UD + ESCA + GP), so GE/SF State Studies slots collapse into fewer courses
- [x] MCP prompt `plan_my_degree` (ARCHITECTURE §7.4), args `goal`, `graduate_by`. Test: it names only real tools
- [x] Test: every `build_plan` output passes `check_plan` for all eval profiles (p05 is invalid by
  design: CR in MATH 226/CSC 101, which the major rejects and which can't be repeated; it says why)
- [x] Test: the cybersecurity case schedules CSC 415 before CSC 652/653 (p03 plan, slots filled, re-checked)
- [x] `unlocks` in `get_course` (reverse prereq index) and `why` on every course `build_plan` places
  ("CSC 413 in term 3: CSC 665, CSC 620, CSC 648 need it")
- [x] Pace options in `plan_my_degree`: `build_plan` at ≈18 + summer / 15 / 12 units, compare
  `est_graduation_term`.
  - [x] `build_plan` `pace` (prereq-chain floor vs units floor) + `graduate_by` → `on_time` / `why_not`.
    Test: an impossible 3-year plan says what blocks it (chain or units)
- [x] What-if workflows in the prompt (ARCHITECTURE §7.4): earlier graduation, new direction
- [x] Advisor handoff (ARCHITECTURE §7.5): `see_advisor` items for substitutions (CR in a major course),
  GPA-gated permission, overloads, unverified rules, in check_plan / build_plan / audit_progress.
  DPR disagreements join when the cross-check exists (phase 6)
- [x] Collect the official advising links + how to book, with sources → `advising:` in
  `rules/university/2026-27.yaml` (UAC, Advising Hub, DPR) and `rules/programs/2026-27/bs-cs.yaml`
  (CS department, Senior Advisor, CoSE team). Booking is Navigator (sfsu.campus.eab.com)
- [ ] (?) Who is the CS Senior Advisor? The department page requires one for substitutions but doesn't
  name them. Ask cs-dept@sfsu.edu
- [x] Present a passing plan as a term-by-term list in Degree Planner entry order (prompt step 8), so the student can
  record it in the official planner (ARCHITECTURE §3: complement, don't replace)
- [ ] `save_profile` / `load_profile` (ARCHITECTURE §7.3, D13): student-chosen path, default
  `~/.gatorpath/profile.yaml`, refuses repo paths, stale-DPR warning. Test: no tool writes a file
  unless `save_profile` is called

**Done when:** "I'm a CS sophomore, I want cybersecurity, plan my next 3 years" produces a plan
that passes `check_plan`, with sensible electives, and "what if I graduate a year early?" gets a
comparison that says what has to give.

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
- [x] Get the DPR (Degree Progress Report) layout from a real sample (not kept); synthetic fixture
  `tests/fixtures/dpr_synthetic.txt`, layout in ARCHITECTURE §7.3. The DPR, not the transcript,
  shows which requirement each transfer course meets, so it's the import for transfer students
- [ ] (?) Catalog year: the sample DPR holds the student to **Spring 2025 (2024-25 Bulletin)**, with
  the old GE scheme (A1-E, UD-B/C/D, 48 → 42 units after the 3/12/25 waivers). Our rules are 2026-27
  only. Decide: add 2024-25 rules (needs that Bulletin PDF), or have `import_dpr` refuse to audit
  across years. Mapping old GE areas to new ones must come from a Bulletin table, never from memory
- [ ] (?) DPR `Notes` codes (`02`, `03`, `04` on transfer rows) have no legend in the print; ask
  the Registrar or an advisor
- [ ] `dpr.py` + `import_dpr` tool: local PDF → `completed` (SF State + `transfer: true` rows),
  `in_progress`, `ge_done`, `transfer_units`; PII dropped, raw text never returned/logged/stored.
  No live login to the Student Center: the student downloads the PDF and re-imports each term
- [ ] DPR-first (ARCHITECTURE §7.3, D14): `import_dpr` returns `remaining` from the DPR, and
  `build_plan` plans from it when present
- [ ] DPR cross-check: compare `audit_progress` against the DPR's own per-requirement status;
  every disagreement → ⚠️ naming the group (catches rule bugs while rules are `verified: false`)
- [ ] Test: the fake name/ID strings in the DPR fixture never appear in the output

**Done when:** importing the synthetic transcript gives the same audit as typing the courses, and
importing the synthetic DPR gives an audit with no unexplained disagreements with the DPR.

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

## Phase 9 — Keeping it current (ARCHITECTURE §5 "Keeping it current", D11, D12)

Robots detect and rebuild; a human approves rule changes; students re-import their DPR each term.

- [ ] Catalog year per student: the server takes the year from `profile.catalog_year` / the DPR's
  requirement term and loads `rules/<kind>/<year>/` (removes the `YEAR` ponytail in `server.py`).
  First real case: 2024-25 rules (needs the 2024-25 Bulletin PDF), see the Phase 6 `(?)`
- [ ] Source snapshots: `rules/programs/<year>/<program>.source.txt` holds the Bulletin text each
  group was written from
- [ ] Bulletin diff: new Bulletin vs snapshots → unchanged groups copied to the new year (new page
  numbers, `verified` kept); changed groups listed with old/new text, program set `verified: false`
- [ ] (?) Find the Bulletin PDF's download URL pattern so a job can fetch it
- [ ] Yearly GitHub Action (cron + manual trigger): fetch Bulletin if new → ingest → diff → open a
  PR. Never merges itself, never edits rule logic
- [ ] Per-term GitHub Action: offerings scrape (phase 5), once per term, cached
- [ ] Attach the rebuilt `catalog.db` to a GitHub release; README says how to download it
- [ ] `amendments` rule type in `engine/rules.py` + tests; first use: the 3/12/25 Area C/E waivers
  in the 2024-25 rules (needs the memo or its DPR wording as the source)
- [ ] DPR cross-check ⚠️ links a GitHub issue template: program, catalog year, requirement, what
  the DPR says. No grades, names or IDs

**Done when:** a dry run with a second Bulletin year opens a PR whose diff a reviewer can approve
in under an hour, and an unchanged program needs no edits.

---

## Later (not planned yet)

- Transfer credit: ASSIST (CA community colleges); out-of-state similarity + Course Equivalency
  Request drafting
- Week-level schedule builder from live class-search sections
- Web roadmap UI on top of the same MCP server
- Pitch to SFSU Advising / Registrar for a pilot
