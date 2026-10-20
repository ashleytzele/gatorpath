# GatorPath — Tasks

Phased checklist. Each phase has a **Done when**. Work phases in order, with two exceptions (ARCHITECTURE D22):
trial feedback can pull work forward from a later phase (trial 1 needed `build_plan`), and an item waiting on a
person or a real document (Phase 2's second reviewer, Phase 6's CR/W sample) stays open while later phases go on.
Such an item says what it waits for. Design details: `docs/ARCHITECTURE.md`.

Legend: `[ ]` todo · `[x]` done · `(?)` needs a decision first

---

## Done 2026-10-18 — Design-consistency audit (Codex, read-only)

Next: Phase 7 (eval questions). Still open in earlier phases, each waiting on a person or a document: Phase 2's
second reviewer, Phase 6's CR/W/repeat sample and the DPR Notes legend.

The pivots since 2026-10-16 came from real trial feedback, but they've outrun the design docs. Codex only sees the
repo, so a change whose reason lives only in a chat would rightly be flagged as a conflict. Write the reasons down
first, then audit.

- [x] 1. Record the pivots in `docs/ARCHITECTURE.md` (decisions log + the sections they change). Done 2026-10-18:
  D17-D22, §8 rewritten roadmap-first, §5 "What may come from where" (+ AGENTS.md golden rules 1-2), the duplicate
  D15 renumbered D16, §16.8 (keep `import_transcript`?)
  - Planning is roadmap-led (§8 still describes critical-path greedy). The default cap stays 15 even though the
    first-time roadmaps have 16-17-unit terms (`pace.roadmap_load` reports them)
  - Senior electives wait for real readiness (an option ready that term), not the roadmap's course order
  - The DPR is the main import (`import_dpr`); the transcript could become optional
  - Some rules come from websites, not the Bulletin: the F-1 Reduced Course Load page (`f1_final_term`) and the
    advising offices. Golden rule 1 still says course data comes from the Bulletin PDF: say what's allowed from where
  - Phases ran out of order: 5 and 6 were done while Phase 2 verification and Phase 3 trials are still open, though
    this file says to finish phases in order
- [x] 2. Run Codex read-only (as in the rules reviews), on design consistency, not Bulletin accuracy. Inputs:
  `AGENTS.md`, `docs/ARCHITECTURE.md` (with the decisions log), `TASKS.md`, the `plan_my_degree` prompt and the tool
  docstrings in `src/gatorpath/server.py`, and `src/gatorpath/engine/planner.py`. Output: a table with columns
  conflict | where (file:line) | which decision or rule it breaks | suggested fix
  - 2026-10-18: 6 findings, all confirmed in the code: (1) the prompt's "re-check until valid" had no way out when no
    plan change fixes an error (p05's CR in a major course; F-1 at a 12-unit cap is invalid, 13 is valid); (2)
    ge_combinations said "every" / "fewest" though its search is bounded (8 ways, 3 past 5 open; "not a proof of
    the minimum"); (3) the server instructions said to cite Bulletin pages only (D21 allows office pages); (4) §7.3's
    readiness shape lacked `check`; (5) the build_plan docstring and this file's Phase 4 item said critical-path
    first (D17); (6) §7.4 asked for the QR pathway unconditionally. Codex missed 3 the step-1 read found: the planner's
    build_plan docstring (D17), the prompt telling F-1 students the final-term RCL is outside GatorPath (D21), and
    why_not saying senior electives wait for the roadmap's order (D19)
- [x] 3. Check each finding in the code before fixing it; commit the fixes, then review the commit

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
- [x] Asterisk (`CSC 510*`): the legend is on p.2436 ("enforced at the time of registration"), found in trial 6;
  parsed as the plain course, no warning (ARCHITECTURE §16.1 closed)
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
  - 2026-10-17: Codex (read-only, independent) reviewed the three files against the PDF in 6 rounds; error rate
    (MISMATCH + MISSING + WRONG-PAGE / items) 19.6% → 16.9% → 10.9% → 15.4% → 12.7% → 6.0%. Each finding was
    re-checked in the PDF before fixing (round 1's two WRONG-PAGE claims were wrong). Round 6's four findings fixed (ADT
    admission note, totals + academic_load pages, CR cap leaves out CR/NC-only major courses); the adt / prior_bachelors
    flags now state the Bulletin's conditions (p.2313).
  - Round 7: 0 MISMATCH, 0 WRONG-PAGE, 9 MISSING / 67 (13.4%), all confirmed in the PDF and fixed: "no specific degree"
    note (p.1906), catalog rights "regular sessions … same curriculum" (p.2390), no UD credit for community college
    work (p.2304, transfer rows numbered 300+ now ⚠️), Winter/Special Sessions outside the 24-unit extension cap
    (p.2391), graduate class level and F-1 continuous enrollment (p.2390), which grade forgiveness drops and what
    happens past 16 units (p.2392), transfer repeats follow the other school's policy (p.2399), Cal-GETC 34 units
    (p.2304).
  - Round 8: 1 MISMATCH, 3 MISSING, 3 WRONG-PAGE / 66 (10.6%). Fixed after checking the PDF: `exam` cap is
    "examination or evaluation" (p.2313); GE 1C / 3UD / 4UD also cite their headings (pp.2315, 2321, 2324; the
    p.2320 summary stays); 2 hours of preparation per class hour (p.2393); the 13-unit academic-notice cap holds while
    the GPA is below 2.0, with a UAC/EOPP exception (p.2397, Codex said 2398); Academic Renewal for pre-fall-2017
    repeats (only to reach the 2.0, prior C-/D/F/WU, shares the 16 units, pp.2398-2399). UNCLEAR legacy GE counts:
    `--legacy-ge` reproduces every count in the comment. Own round-7 slip fixed: transfer repeats are p.2399.
    UNCLEAR (for an advisor): "five 3-unit senior electives" vs 1-unit CSC 685/686. A person still flips `verified`
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
  - [x] Model estimated "finish Spring/Fall 2027" with no planner → phase 4 `build_plan` (used from trial 2 on)
  - [x] Transcript was attached to the chat directly (PII to the provider) → phase 6 `import_transcript` / `import_dpr`
    (built; trial 7 imported a real DPR and transcript locally)
  - Trial 2 (same student, DPR + build/check_plan): two-semester plan matched the student's own;
    claims checked against the Bulletin (ENVS 401 = ESCA + 4UD + GP, CSC 656 with CSC 415 concurrently).
    Gaps: validated against 2026-27 while the student is on Spring 2025; no offering data; GEOG 575's
    "GE Area E" prereq vs the 3/12/25 Area E waiver went unflagged
  - Trial 3 (plan_my_degree prompt): asked one question at a time, wouldn't take the DPR, and the Spring 2025
    catalog hit `unsupported_catalog_year`, so it sent the student elsewhere. Fixed: ask once; the DPR is the
    fast path (with a one-time PII note); other catalog years are planned with a warning; old GE codes
    translated (`legacy_ge_areas`, from co-tagged courses); `dpr_met` for substitutions; QR pathway asked only
    while lower-division math is left
  - Trial 4 (same student, prompt + DPR): valid plan to Spring 2028, but it added GE 6 Ethnic Studies (2026-27
    rule) that the student's Spring 2025 transfer-GE DPR doesn't have. The 2026-27 Bulletin lists Area 6 in the
    GE table (p.2311) and says transfer students have different GE requirements (p.2313); the DPR wins. Fixed:
    `not_on_dpr` leaves such a requirement out with a UAC see_advisor to confirm. Without GE 6 the same courses
    finish in Fall 2027 (12 + 15 units, CSC 656 alongside CSC 415), checked with check_plan
  - Trial 5 (prompt with load_profile / save_profile, cybersecurity, F-1): load_profile found none, the DPR was asked
    once, and the cybersecurity re-pick (CSC 645/651/652/653/656) passed check_plan; save_profile was offered at the end.
    Gaps: F-1 status wasn't asked, so two plans had part-time spring terms (9 and 6 units, only a generic "F-1 students
    need 12" note) until the student said so; the planner left Spring 2027 at 9 units because senior-elective slots wait
    for the roadmap's order; the model gave visa advice the tools don't have (STEM OPT). Fixed: the prompt asks about
    F-1 in its one question; `f1: true` makes a spring/fall term under 12 a `below_f1_minimum` error and a skipped one
    `f1_gap` (pp.2390, 2393); a last term under 12 is a warning + the new `international` advising entry (Division of
    International Education); build_plan fills an F-1 student's light terms with waiting elective slots (the trial's
    9/12/6 → 12/12/3, `tests/test_planner.py`); other visa questions go to the international office
- [x] Also try another client (proves "works with any client"): Codex CLI, since Gemini CLI isn't installed. Trial 6 below
  - Trial 6 (Codex CLI, synthetic p03 sophomore shifted a year to today, the Phase 4 "Done when" questions): with the
    server attached but not named, Codex answered from web search, with no check_plan (README now says to start with
    the prompt). With the plan_my_degree text, it ran load_profile → audit_progress → build_plan →
    list_eligible_electives → check_plan: valid plan to Spring 2029, electives CSC 652/653/651/645/656, triple-duty
    GE (ERTH 335, HIST 405, PLSI 451). "A year early" got the pace table: only 18 units + summers reaches Fall 2028.
    Found: (1) the '*' warning fired on 17 courses, but the legend is on p.2436 ("enforced at the time of
    registration"): warning removed, Phase 1 item closed; (2) with include_summer, build_plan started in the term
    the in-progress courses were in (Fall 2026), so a direct build_plan wrongly said 18 + summers reaches Spring 2028:
    in-progress courses now hold the next spring/fall; (3) Codex read "a year early" against the 3-year horizon:
    the prompt now says it's a year before est_graduation_term
  - Trial 7 (Desktop, a real F-1 transfer student's DPR + transcript via import_dpr / import_transcript; nothing kept):
    valid plan at 12 units a term; the model noticed the two PDFs disagreed on a current course and went with the
    newer DPR. Found: (1) build_plan added MATH 197/198 for a student whose math was done (the pathway walk followed
    "one of" branches below finished courses); fixed, it stops at done or DPR-met courses; (2) electives needing
    MATH 225 showed blocked though the DPR met it by substitution: now "check" (ask the instructor); (3) the last
    term was padded with three courses only to reach 12 units: SF State allows a one-time final-semester Reduced
    Course Load (international.sfsu.edu/rcl), now in the rules and in check_plan's warning, plus F-1's online-class
    limit (3 units); (4) the model called courses optional while also saying upper-division units were short: the
    prompt now says to re-check before calling a course optional; (5) GE slots got one pick: the prompt now lists 3-5
    options that cover the same requirements (9 triple-duty 4UD courses exist for 4UD + ESCA + GP)
  - Trial 8 (Desktop, "I'm an incoming freshman, nothing done, plan everything"): ge_combinations hung (17 open
    requirements, brute-force combinations). Fixed: greedy cover + bounded exact-cover search (0.3 s), `overlaps`.
    Asked next: use the Bulletin roadmap as the foundation (GE Area 1A in term 2, …). build_plan is now roadmap-led:
    a new QR 1/2 freshman gets 8 terms at 15 units (was 9), following the roadmap's GE layout. Scenario matrix
    (`tests/test_server.py`, 11 kinds of students: new freshmen, AP credit, sophomore, ADT and Cal-GETC transfers,
    prior bachelor's, summers, part-time, a retake, an older-catalog DPR) found: Cal-GETC certification didn't count
    for prereqs ("GE Area 1A" for CSC 300GW, UD GE), so transfer plans stalled; the Area 4 two-subjects rule booked an
    extra 3-unit course and wasn't fillable through list_eligible_electives. All fixed; every scenario gets a valid
    plan on the real catalog
  - Scenario review (2026-10-18, `evals/plan_review.py`): 15 kinds of students × 12 / 15 / 18 / 18+summer units on the
    real catalog. Now: every plan valid except QR 3/4 + F-1 at a 12-unit cap (4-unit courses leave 10-11-unit terms the
    F-1 minimum can't accept: an honest error), at or within a term of the lower bound, laid out on the roadmap almost
    everywhere; more units or summers graduate sooner. A freshman at 15 has 18 of 20 roadmap courses in their roadmap
    semester (the rest one term later, from its 16-unit terms); at 18 courses move earlier, never later
    (`test_a_freshman_plan_is_the_roadmap_adjusted`). Fixed on the way: a 0-unit tag made a term of its own; tags
    dumped into term 1; senior electives waited for the roadmap's order instead of their real prereqs (they now go in
    once an option is ready that term); F-1 fill splits free units
  - Trial 9 (2026-10-18, Claude Code headless, `claude -p` with only the gatorpath tools and no prompt; synthetic p03
    shifted a year): the two Done-when questions as written. "What do I need before CSC 653?" → get_prereq_chain:
    upper-division standing, CSC 415 with C or better, GPA 3.0, or instructor permission (p.1899), plus the chain to
    CSC 101 with pages; every prereq matched the Bulletin text. "What's left for my degree?" (typed courses) →
    audit_progress: every group, GE area and total matched p03's hand-checked audit. Found: GE claims from memory
    (PHYS 220 meets 5A: right; "AA S 210 might count for GE 6": wrong, it carries AERM, 4, USH). Fixed: an open GE /
    SF State Studies / American Institutions group names the required major courses still ahead that carry it
    (`major_courses`, p.2352), and the server instructions say a course meets an area only where a tool shows it.
    Re-run: 5A, 5C and GWAR came from major_courses, and GE 6 was checked with get_course instead of guessed

**Done when:** you can ask Claude "what do I need before CSC 653?" and "what's left for my
degree?" and get correct, sourced answers. **Met 2026-10-18** (trial 9).

---

## Phase 4 — Planner

- [x] `engine/planner.py::check_plan` + `check_plan` tool: prereqs by term (tri-state: ok / not met /
  can't verify; "or permission" never rescues a plan), corequisites, class level (p.2390), restrictions,
  repeats/duplicates, unit cap + normal load (p.2393), requirement coverage with slots, 120/UD totals.
  Offering-season checks wait for phase 5
- [x] `build_plan`: critical-path priority + term-by-term greedy (ARCHITECTURE §8; roadmap-led since 2026-10-18,
  D17); corequisites together;
  roadmap pathway courses (QR 3/4: MATH 197 → 198 → 226); slots for GE / senior electives / free units;
  CR or C-or-better major courses that can't count or be repeated → ⚠️ see an advisor
- [x] Return `needs_input: qr_pathway` (and `start_term`) when it's missing
- [x] `list_eligible_electives` with readiness (`ready` / `check` / `blocked` + `blocked_by`, `ready_by` from
  a plan) and the Bulletin description of each option
  - [x] Rank options by how many **open** requirements one course covers ("triple duty": ENVS 401 /
    LS 401 = 4UD + ESCA + GP), so GE/SF State Studies slots collapse into fewer courses
  - [x] `ge_combinations` (asked after trial 7): every minimal combination for the open GE / SF State Studies /
    American Institutions requirements, e.g. one triple-duty course, 4UD + ESCA now and GP next term, or one each;
    the prompt shows them as a table so the student picks (a web UI could draw them later)
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
- [x] Who is the CS Senior Advisor? Decided 2026-10-17: don't name one (ARCHITECTURE D15). Substitutions go to the
  CS department (cs-dept@sfsu.edu, or Navigator), which routes them; other majors fall back to the UAC
- [x] Present a passing plan as a term-by-term list in Degree Planner entry order (prompt step 8), so the student can
  record it in the official planner (ARCHITECTURE §3: complement, don't replace)
- [x] `save_profile` / `load_profile` (ARCHITECTURE §7.3, D13): student-chosen path, default
  `~/.gatorpath/profile.yaml`, refuses repo paths, stale-DPR warning. Test: no tool writes a file
  unless `save_profile` is called (every tool the server lists is run against an empty HOME and cwd).
  `plan_my_degree` starts with `load_profile` and offers `save_profile` at the end

**Done when:** "I'm a CS sophomore, I want cybersecurity, plan my next 3 years" produces a plan
that passes `check_plan`, with sensible electives, and "what if I graduate a year early?" gets a
comparison that says what has to give. **Met 2026-10-17 (trial 6, Codex CLI; see Phase 3).**

---

## Phase 5 — Offering history

- [x] Check SFSU class-search terms of use (2026-10-17): no terms on the page, robots.txt allows all, CSU Responsible
  Use Policy satisfied by the etiquette in AGENTS.md; decision: scrape politely (ARCHITECTURE §16.2)
- [x] `ingest/offerings.py`: one search per subject per term, cached (`data/cache/offerings/`), ≥ 2 s between requests,
  honest User-Agent. No CSRF token needed: the search form redirects to a GET `results?term=2257&classCategory=REG&
  subject=CSC`, and `searchresultsjson` returns that session's sections. Regular session (REG) only, not CPaGE
- [x] Scrape CSC, MATH and PHYS for the last 4 years: 2023-spring to 2026-fall, 36 searches (2026-10-17)
- [x] `offered` (offered_terms) on catalog rows: [terms it ran, terms checked] per season + `last`; build_plan waits
  for a season the course runs in (only seasons the plan has), check_plan warns (wrong season, not run in the last
  year, never run); get_course / search_courses / list_eligible_electives show it
- [x] Spot-check 5 courses against the live site (fresh fetch vs stored): CSC 653 2024-summer, CSC 648 2026-fall,
  MATH 324 2025-spring, PHYS 222 2025-fall (labs), CSC 300GW 2026-spring: all match; the CSC 653 detail page agrees.
  Found: CSC 652 last ran 2023-summer and CSC 653 2024-summer (summers only), so trial 6's security picks now warn

**Done when:** the planner never places a fall-only course in spring without a warning. **Met 2026-10-17** (`tests/test_planner.py`).

---

## Phase 6 — Transcript import

- [x] Get the unofficial transcript layout (`SSR_TSRPT`); synthetic fixture at
  `tests/fixtures/transcript_synthetic.txt` (ARCHITECTURE §7.3)
- [ ] Get a sample with CR / W / I / repeat / summer rows (redacted or rebuilt synthetic). None available
  (2026-10-17): the parser reads any p.2403 grade symbol in the same columns, assumes `SU` for summer (ponytail), and
  flags unknown term codes and unreadable rows by position. Check against the first real transcript that has them
- [x] `transcript.py`: `pdftotext -layout` → extract (term, code, units, grade) rows; drop
  everything else; transfer blocks → `transfer_units` + ⚠️
- [x] In-progress courses (no grade yet) → `in_progress`
- [x] Test: the fake name/ID strings in the fixture never appear in the output
- [x] `import_transcript` tool (a local path, so the PDF isn't attached to the chat); `plan_my_degree` offers it.
  Test: importing the synthetic transcript gives the same audit as typing the courses
- [x] Get the DPR (Degree Progress Report) layout from a real sample (not kept); synthetic fixture
  `tests/fixtures/dpr_synthetic.txt`, layout in ARCHITECTURE §7.3. The DPR, not the transcript,
  shows which requirement each transfer course meets, so it's the import for transfer students
- [x] Catalog year (decided in trial 3): a DPR on another catalog year is planned with 2026-27 rules plus a warning,
  the DPR wins where they disagree, and `not_on_dpr` leaves out what the DPR doesn't have. 2024-25 rules wait for
  phase 9. Original question: the sample DPR holds the student to **Spring 2025 (2024-25 Bulletin)**, with
  the old GE scheme (A1-E, UD-B/C/D, 48 → 42 units after the 3/12/25 waivers). Our rules are 2026-27
  only. Decide: add 2024-25 rules (needs that Bulletin PDF), or have `import_dpr` refuse to audit
  across years. Mapping old GE areas to new ones must come from a Bulletin table, never from memory
- [ ] (?) DPR `Notes` codes (`02`, `03`, `04` on transfer rows) have no legend in the print; ask
  the Registrar or an advisor. `import_dpr` flags any it finds
- [x] `dpr.py` + `import_dpr` tool: local PDF → `completed` (SF State + `transfer: true` rows),
  `in_progress`, `ge_done`, `transfer_units`; PII dropped, raw text never returned/logged/stored.
  No live login to the Student Center: the student downloads the PDF and re-imports each term. Also `dpr_met`
  (substitutions), `gpa`, `catalog_year`, and `remaining` (the DPR's own "needed"); transfer rows get the
  requirement's minimum grade, said in a warning; a "needed" line beats waiver wording; `plan_my_degree` asks for the
  DPR's path first
- [x] DPR-first (ARCHITECTURE §7.3, D14): `import_dpr` returns `remaining` from the DPR, and
  `build_plan` plans from it when present. As built: build_plan plans from the profile import_dpr builds (transfer
  rows, dpr_met, ge_done), and the cross-check flags wherever that differs from the DPR. ponytail: no separate "plan
  from remaining" path; add one if a trial finds a DPR requirement the profile can't express
- [x] DPR cross-check: compare `audit_progress` against the DPR's own per-requirement status;
  every disagreement → ⚠️ naming the group (catches rule bugs while rules are `verified: false`). Course
  requirements by code, GE areas via legacy_ge_areas, GWAR, units toward 120, and GE areas missing from the DPR
  (→ not_on_dpr); `see_advisor` the DPR when anything disagrees
- [x] Test: the fake name/ID strings in the DPR fixture never appear in the output

**Done when:** importing the synthetic transcript gives the same audit as typing the courses, and
importing the synthetic DPR gives an audit with no unexplained disagreements with the DPR. **Met 2026-10-17**: the transcript test in `tests/test_server.py`; for the DPR every course and GE area agrees, and the two left (unlisted transfer units, GE areas the partial fixture doesn't show) come with their reason (`tests/test_dpr.py`).

---

## Phase 7 — Evals, demo, first users

- [x] 30–50 eval questions (`evals/`), each with a profile + goal + expected properties: `evals/questions.yaml`, 39
  questions (10 catalog, 10 "what's left", 13 plans with a goal, 6 honesty) + 5 follow-ups. Facts are computed from the
  tools at scoring time; the goal keywords are the only hand-written rubric
- [x] `run_evals.py`: run through a real AI client + server; score validity, goal-fit (rubric),
  hallucinated codes. Claude Code and Codex CLI, each with only the gatorpath server (no user plugins, web search or
  shell); the presented plan is re-checked for the question's student; `evals/REPORT.md` + an alignment table
  - Run 2026-10-18 (`data/evals/20261018-175748`): Claude 38/39, Codex 37/39 questions fully passed; plans passing
    check_plan 13/13 both; 0 unknown course codes; the profile each client passed matched the student every time; same
    graduation term on 12 of 13 plans (part-time: Codex's lighter terms end a term later). Goal fit 11/12 and 10/12:
    Claude's game-development picks (CSC 630/631 ran once in 4 years), Codex's data-science and web picks (keyword rubric;
    CSC 671 Deep Learning doesn't say "machine learning"). Codex is thorough but slow: median 68 tool calls and 11 min
    per plan vs Claude's 14 and 2.5 min
  - Fixed from the runs (server/prompt): "QR 3/4" now reads as 3/4; the prompt uses courses already given and takes
    what isn't mentioned as none (Codex asked to confirm "no prior coursework"); `first_time` is left out unless said
    (Codex invented false); plans never start on top of the term underway (`current_term` from today's date,
    check_plan `term_in_progress` / `term_in_past`: Codex had put CSC 215 beside an in-progress CSC 101 and it passed)
  - Found about the clients: without "SF State" in the question Codex may skip the gatorpath tools; Codex's web search
    comes through its `apps` feature (not `web_search`); usage limits return as an answer (Claude) or an error event
    (Codex), so `--retry` reruns them. Scorer bugs fixed with tests: shorthand code lists, the plan the answer presents
    (not the last check_plan), course levels ("700-level") read as codes
- [ ] README: problem, demo GIF/video (2 min), setup in 3 commands, eval table, limitations
  - 2026-10-19: problem, setup in 3 commands (from the zip), eval table and limitations written. Waits on the
    demo GIF/video, recorded by a person
- [x] Shareable zip for classmates (2026-10-19): `dist/gatorpath.zip` = the committed code + `data/catalog.db`
  (command in AGENTS.md), so they don't need the Bulletin PDF or a scrape. Not the raw PDF, cache or eval runs.
  The PDF importers now say to install poppler when pdftotext is missing
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
