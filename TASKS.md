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
    first-time roadmaps have 16-17-unit terms (`pace.roadmap_load` reports them). Replaced by D24 (2026-10-22): the
    roadmap's loads are the default
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
  - Run 2026-10-21 (`data/evals/20261021-192336`), 44 questions: the three catalog years (a Fall 2025 sophomore, a Fall
    2024 junior on the old GE pattern, both `scenario:` students in tests/test_server.py) and Winter Session (a plan's
    what-if, "Can I take one of my GE classes in Winter Session?"). Claude 43/44, Codex 43/44; plans passing check_plan
    15/15 and 14/15; 0 unknown course codes; the profile each client passed matched the student every time, catalog
    year included (the scorer now checks it, and scores goal fit on the student's own year's elective list). All six
    new questions pass on both. Left: Claude's web-development retake plan skips CSC 667 / 675, which need a 3.0 GPA
    (the student has 2.545), and names them as backups (keyword rubric; kept as a fail); Codex stopped to ask a Cal-GETC
    transfer student for a DPR though they gave units, certification and "no major courses" (the prompt's "gives their
    courses" now covers what transfer credit meets, e.g. a GE certification and no major courses, but not a unit total
    alone; rerun `data/evals/20261022-001516` passes on both).
    Scorer fixes: honesty wording ("isn't listed", "couldn't find"), "senior elective" for the Electives group, and a
    summer what-if answered from the first turn's build_plan run
  - Graduation terms differ on 2 of 15 plans. Fall 2025 sophomore: at 15 units build_plan ends with a 1-unit term;
    Claude offered one 16-unit term instead (a term sooner, with an advisor's OK), Codex kept the extra term. p03:
    Codex's own plan runs a term past build_plan's. Since 2026-10-22 `pace.fold_last_term` says it: a light last term
    goes into the lightest earlier spring/fall term that passes check_plan (up to 19 units), with the advisor note when
    it's over 15; a slot moves no earlier than the plan's first term with that slot (check_plan can't see senior-elective
    readiness: without it a transfer's last two went into their first term). In plan_review (flag F) 14 cells get it, e.g. the sophomore's 1 unit -> one 16-unit term
- [ ] README: problem, demo GIF/video (2 min), setup in 3 commands, eval table, limitations
  - 2026-10-19: problem, setup in 3 commands (from the zip), eval table and limitations written. Waits on the
    demo GIF/video, recorded by a person
- [x] Shareable zip for classmates (2026-10-19): `dist/gatorpath.zip` = the committed code + `data/catalog.db`
  (command in AGENTS.md), so they don't need the Bulletin PDF or a scrape. Not the raw PDF, cache or eval runs.
  The PDF importers now say to install poppler when pdftotext is missing
- [ ] Make the repo public (MIT); credit GatorWay/Plan-Ed as prior art
- [ ] 5–10 SFSU classmates try it; collect feedback; fix the top 3 issues
  - Test user 1 (2026-10-20: DPR import, plan, "can I take a GE class in winter"). Fixed: US History options for a
    first-time student (ge_combinations, list_eligible_electives) follow `first_time_from` like the audit (an
    upper-division USH course was offered, then failed check_plan); GE Area 4 in ge_done alone no longer meets US
    History; a course retaken now drops its old grade for prereqs (build_plan blocked everything after it); a DPR page
    break's print header and "One course is required." are no longer requirement titles.
  - Winter Session terms (2026-10-21): `YYYY-winter` (January, between fall and spring; "The maximum number of units a
    student may earn in Winter Session is 4 units", each year's Bulletin), checked by check_plan with no F-1 minimum or
    normal-load rule; `include_winter` lets build_plan use them for GE, American Institutions and free-elective slots
    only (no winter offering history). With it, 6 of 17 scenarios finish a term sooner; a student 19 units short of
    a spring graduation gets one GE course into Winter. Summer stays opt-in (`include_summer`), as before
- [x] Write the resume bullet with real numbers (2026-10-22; numbers from `data/catalog.db`, `evals/REPORT.md` run
  20261021-192336, `pytest`). Add "N SF State students tried it" once the classmates have:
  - Built GatorPath, a Python MCP server that gives AI assistants deterministic SF State degree-planning tools: parsed
    4,967 courses from the 2,932-page Bulletin PDF (prerequisites fully parsed for 74%, the 111 it can't parse flagged,
    never guessed), encoded BS CS requirements for 3 catalog years with a source page cited on every rule, and wrote
    the plan checker every generated plan must pass; on 44 eval questions Claude Code and Codex CLI each passed 43,
    with 0 hallucinated course codes
  - Short: Built an MCP server that grounds AI degree planning in SF State's 2,932-page Bulletin: 4,967 courses, page-
    cited requirements for 3 catalog years, a deterministic plan checker; 43/44 eval questions passed on both Claude
    Code and Codex CLI, 0 hallucinated course codes

**Done when:** the public repo has a demo, an eval table, and real user feedback.

---

## Phase 8 — Expand

- [ ] BS Mathematics rules + roadmaps (verified)
  - 2026-10-22: the Bulletin has no BS in Mathematics: a BA (Advanced Study, Liberal Arts, Teaching), a BS in
    Applied Mathematics and a BS in Statistics (p.2089). Chosen: **BS Applied Mathematics**, 2026-27,
    `rules/programs/2026-27/bs-applied-math.yaml` + roadmaps QR 1/2, QR 3/4, ADT (pp.2129-2137), `verified: false`.
    New vocabulary (ARCHITECTURE §6.2): `one_of` ("Select One: MATH 209, CSC 101 & CSC 215, or CSC 309"),
    `approval` + `from: {approved: true}` + `profile.approved` (three application electives "chosen with the consent
    of the applied mathematics advisor": no list, so only approved courses count and build_plan sends the student to
    that advisor), roadmap `{one_of}` and `{slot: major, group}` items. check_plan's "12 units must be CSC" note and
    the "rules only for <years>" warning are now per program. Synthetic p11 (sophomore) and p12 (senior: C- in MATH
    325, CR in an elective, the CSC option in progress, approved electives); 4 Applied Math scenarios in plan_review.
    Found: QR 3/4 takes 10 terms, not the roadmap's 8 (MATH 376 ran fall-only and MATH 460 spring-only in Class
    Search 2023-2026; the roadmap puts MATH 696 before its prereq MATH 460); the ADT footnote says MATH 460 is
    fall-only, the history says spring; MATH 400's prereq names "MATH 309" (not in the Bulletin), not CSC 309.
    Not done: the Scholars BS + MA roadmap (graduate rules), older catalog years, `dpr_plan` (waits on a real Applied
    Math DPR), and a second person's check against the PDF
- [x] `compare_programs(profile, target)`: what counts, what's left, extra semesters. Done 2026-10-22: both majors'
  audits and build_plan at the same load; `courses` count_in_both / only_current / only_target, `extra_terms`. The new
  major is the Bulletin in effect at the change ("must fulfill the major requirements in effect at the time they
  declare or change their major", pp.2352, 2390: `change_of_major` in the university rules), GE stays the catalog
  year; the DPR's substitutions aren't carried over. A CS junior on track keeps 4 major courses toward Applied Math
  and needs 2 more terms. Eval questions left-p11, left-p12 and switch-math added (not run yet)
- [x] Offline AI-draft pipeline: Bulletin program page → draft YAML → human review →
  `verified: true`. Done 2026-10-22: `gatorpath.ingest.programs` lists the 110 bachelor's programs the 2026-27
  department pages list, with requirement and roadmap pages from the running heads (wrapped heads, a shortened listed
  title, a listed page that's another program's, "&"/"and" handled); `--source` writes `<id>.source.txt`; `--draft`
  runs `claude -p` (no tools) with ARCHITECTURE §6.2, the other programs as examples and the page text, into
  `rules/drafts/<year>/`; `check_program` (engine) checks vocabulary, codes, pages, word-for-word `quote`s and units.
  Acceptance: BS Applied Mathematics drafted without itself as an example audits p11 and p12 exactly like the
  hand-written file (counted, remaining, totals; only group titles differ). The first draft used choose_n, which
  plans a 0-unit slot: check_program flags it and the prompt asks for choose_units. No roadmap drafting yet
- [x] The roadmap is the default unit load (D24, replaces D18). Done 2026-10-22: without max_units_per_term, a
  spring/fall term's cap is the printed load of the roadmap semester the student's units have reached (nearest
  semester end: a new BS CS QR 1/2 freshman gets 16, 15, 16, 15, 15, 15, 15, 13; a 62-unit transfer starts on
  semester 5's load; the ADT roadmap counts SF State units), the last semester's load past the end, at most 19, at
  least 12 for F-1. Each semester carries max_units and roadmap {units, source}; check_plan takes them, and a load
  over 15 its roadmap semester prints is "as on the Bulletin roadmap (p.X)", no advisor. pace.normal_load is the
  lighter plan at 15. Scenario matrix (plan_review, new roadmap column): same or fewer terms than at 15 for
  freshmen (QR 3/4: 8 vs 9); a term more for transfers past a first-time roadmap's end (its last semester's 13,
  Cal-GETC transfer 7 vs 6) and for the Applied Math ADT roadmap, which prints 13, 13, 9, 12, 7, 4, 2.
- [x] The graduation goal sets the load (D25). Done 2026-10-22: with graduate_by, a roadmap plan that ends later is
  rebuilt at the roadmap's heaviest semester, then a unit more at a time up to 19, until it ends by then (a 62-unit
  transfer by 2029-fall: 16 a term; a BS CS freshman a term early: 18, an overload, advisor); plan_my_degree asks
  for the goal. Without one, a term past the roadmap's end keeps its last semester's load.
- [x] Load all programs as `verified: false`. Done 2026-10-23: 97 of the Bulletin's 110 bachelor's programs are served
  (BS CS and BS Applied Mathematics hand-written; 95 AI-drafted, `drafted: true` in list_programs). The five pilot
  programs had a first-pass review against their Bulletin text (fixes in the e26fb86 commit); the other 90 passed the
  `--load` gate unreviewed: only `unparsed` groups left, codes/pages/quotes/units clean, a new student's plan passes
  check_plan on every variant (194 variant plans through the server tools, 8-11 terms). Drafting: Sonnet, rules then
  roadmaps, resumed three times across usage-limit resets (a failed call is reported per program now; only
  hand-written files are prompt examples). Engine fixes the drafts found: CHEM 115's one-sentence placement
  alternatives (unlocked 7 science programs); a prereq outside the requirements and roadmap is added to the plan
  (one per "one of"; PHYS 330 needs MATH 376: Physics, Earth Sciences, Cell and Molecular Biology); all_of/one_of
  claim before electives (Art History's ART 671); "graduate standing or KIN ITEP …" isn't graduate-only; "majors and
  minors with …" clauses; variable-unit courses in the units check; an approval beside a list keeps the list.
  Still drafts, for a person (rules/drafts/2026-27/): BA American Indian Studies, BA Dance, BS Physics: Astrophysics,
  BM Instrumental and Vocal Performance (roadmap semesters short of their printed units: lessons and other unparsed
  items left off), BM Music Production (MUS 281 not on its roadmap), BS Environmental Science: NRM&C (ENV 690 not on
  its roadmap; plan invalid), both Nutrition concentrations (FCS 426 isn't in the catalog), BA Philosophy and
  Religion (no total printed), BA Early Childhood Studies: Special Education ITEP (graduate credential chain), BA
  Women and Gender Studies (3 upper-division units short in the plan). BA Family and Community Sciences has no roadmap.
  Reviewed 2026-10-23 (first pass, Claude): all 90 gate-loaded programs read against their Bulletin text, group by
  group with units added up; 37 fixed, 53 correct as drafted; log in docs/review-2026-27-drafts.md. The usual
  fixes: electives the drafter left unparsed or advisor-only though the Bulletin names their courses or a numbered
  range (now planned); "as needed to reach a total of N units" electives (new `fill_to_total`, ARCHITECTURE §6.2);
  a required course merged into a Select One (BA Chemistry's CHEM 390GW); an approval text paraphrased (check_program
  now checks approval text word for word, like quotes). For a person: BA American Studies, BA Liberal Studies and LS
  ITEP are "Suspended - Not Accepting New Students"; BECA's Bulletin says both 6 and 3 units of BECA 576/685/695/699;
  Classics names a CLAS 400GW the catalog doesn't have; Ecology's upper-division heading (23-25) is a unit more than
  its printed courses. Repeatable courses add up their units in the audit (ensembles), but the planner can't
  schedule one course four times, so "MUS 260 (1 unit course taken 4 times)" stays flagged.
  Pilot 2026-10-22: one program per college, drafted with `--client "claude -p --model sonnet …"` to save usage
  (about 35 s each), kept in `rules/drafts/2026-27/`. BS Civil Engineering had 0 to fix. BM Composition, BS Business
  Administration: Finance, BA Asian American Studies and BS Public Health had 2-6 unparsed groups each. Those are all
  things the vocabulary can't say: CR/NC unit caps, "a maximum of 3 units from", a 1-unit course taken 4 times, courses
  taken concurrently or in sequence, a concentration GPA. In every draft the parsed groups plus the unparsed groups'
  printed units equal total_units (27+9 of 36, 47+18 of 65, 66+3 of 69, 58 of 58, 93). Errors: Public Health wrote
  cross-listings as "PH/ETHS 221" (the prompt now says to list each code), and check_program rejected pages under 1000
  (fixed). The checker can't see omissions: the Civil draft's electives left out "subject to the minimum number of
  units specified for each group" and the advisor-approved study plan, so a draft with 0 to fix still needs a person.
  Before loading: (1) done 2026-10-22: an `unparsed` group (4 of the 5 drafts) audits as status `unparsed` with its
  quote and a warning, and check_plan warns instead of failing (it raised KeyError before); (2) done 2026-10-22, the
  roadmap is the planner's foundation, so every program gets one: `--roadmap <id>` drafts it (below); (3) decide
  whether unreviewed drafts are served.
  Roadmap pilot 2026-10-22 (same 5 programs, Sonnet): `check_roadmap` found Finance and Public Health clean. The
  rest: Asian American Studies and Composition name a major group that their rules draft left unparsed; Civil QR
  3/4's total_units was the "123 Total Units Required" header, not its own "Total Units 129-130" (the prompt now
  says which); Civil's 5-year roadmap was left out, as asked. Plans for a new student on each draft (`try_plans`)
  found four engine and parser bugs, fixed: a "Select One" written as `choose_units` is only a slot, so a course
  needing it never fit (Public Health's PH 425 needs a statistics course; the prompt now says `one_of`);
  "<X> majors with …" prereq clauses were ANDed (ENGR 696 needed every major's courses; now one alternative per
  major, 20 of 4,967 prereqs changed, ambiguous "A or B and C or D" kept whole); "upper-division and graduate …
  majors" read as graduate-only (MUS 434); build_plan counted every major slot as upper division and check_plan
  didn't (Asian American Studies came up 3 units short). With the Select Ones as `one_of`, 9 of 10 test plans pass
  check_plan at 8-10 terms. Civil QR 3/4 stopped on CHEM 180, fixed 2026-10-22: its second sentence ("Category III or
  IV for QR/Math placement must have completed MATH 197 …") was ANDed; another placement's sentence is now its own way
  in, and the QR placement pattern reads every wording the Bulletin uses ("CAT I or II", "… QR/Math placement",
  "Placement Category III or IV"): 7-8 prereqs per year change, CHEM 100/101/115/180 and ESE/ESM 101-102. 10 of 10
  pilot plans pass. "Not open to students who have completed ERTH 112" parsed as requiring ERTH 112; fixed
  2026-10-22, a `not_after` exclusion leaf (ERTH 110-172; 2024-25 also ARTH 404, CLAR 550, ERTH 162, MSCI 313).
  A one_of option was chosen by units only; fixed 2026-10-22: build_plan keeps the audit's option only while every
  planned course stays reachable with it, else the first by units that does (Applied Math: with MATH 209 out of reach,
  CSC 101 & CSC 215, not CSC 309, since MATH 400 needs CSC 215 or MATH 209).
  Pilot redrafted 2026-10-22 with the new prompts (Sonnet, 12 calls: 5 rules, 5 roadmaps, Composition's 2 again). Every "Select One" is now `one_of` (13 groups, 0 left as choose_units) and all 9 test plans
  pass check_plan (8 terms; Civil 10). Public Health: 0 to fix in rules and roadmap. Finance roadmap 0 to fix. What's
  left is a person's: unparsed groups (CR/NC caps, lessons taken 4 times, ensembles, a GPA floor, ENGR 696's
  15-unit rule) and the roadmap slots that name them, plus Civil's 5-year roadmap (left out). Fixed on the way: a
  title's unquoted colon lost two answers (now quoted before parsing; both recovered from the kept answer, no new
  call); the roadmap step read a not-yet-YAML rules draft after spending its call (now checked first); drafted
  roadmaps write a Select One as {slot: major, group: <one_of group>} (the planner now places that group's course);
  my cross-listing prompt line made Composition require MUS 130 and TH A 131 both (now: a required cross-listed
  course is a one_of of its codes, and check_program flags both codes in an all_of from the catalog's 509 pairs).
  Not redrafted with the new prompt yet (usage): the pilot's 5 come first in the load-all run.
- [x] 90/10: GatorPath checks 90% of the rules itself, a person the other 10%. Done 2026-10-24 (`--coverage`):
  91.6% of the 892 requirement groups in the 100 served programs (was 76.5% of 918 in 97); 75 left for a person (67
  unparsed, 8 an advisor approves); 53 programs have nothing left for a person (was 14). Unparsed groups were mostly
  rules over other groups' courses, now check groups (ARCHITECTURE §6.2): letter grades only, CR/NC caps, a GPA
  floor, at most N courses below a grade, at least/at most N units or courses matching a filter (upper division, at
  SF State, in transfer), N subjects, one course in N of the printed categories, all from one category. Filters
  gained max_units, level lower/upper (and lists) on any filter. Caps inside one list are filters; alternatives the
  DPR records (test-outs, AP credit, substitutions with consent, a double major) are `exceptions` text, checked word
  for word. A rule the university rules already state (2.0 GPA in all coursework, GWAR C-, 12 major units in
  residence) or the structure already enforces was removed, with the reason in the file's header. check_roadmap
  takes a variable-unit course's range (AIS 694, 1-3, printed 3), which loaded BA American Indian Studies, BA Dance
  and BS Physics: Astrophysics (first-pass reviewed, rules converted). Interpretations to confirm are in
  docs/review-2026-27-drafts.md ("2026-10-24"). What's left for a person:
  - [ ] (?) Complementary Studies (23 BA groups): one question for an advisor first. Can GE courses count toward the
    12 units "outside of the primary prefix" (p.2353)? If yes, it's a check over every course; if no, 12 units of
    electives outside the prefix (the roadmaps' "Complementary Studies or SF State Studies or University Elective"
    slots suggest no). Either answer converts them all.
  - [ ] Ordering rules in the planner (15): "Before advancing to the 300-level or higher courses ... completed the
    lower-division courses for the major" (4 art and design programs), a capstone "in the senior year" / "the spring
    semester of the student's final (senior) year" (Economics, 3 English), a GPA before credential coursework (2
    ITEPs), Social Work's GE 1A first and 24 junior units before practicum, ENGR 696 after 15 UD ENGR units, Speech's
    semester sequence. A planner order constraint, then a check.
  - [ ] Repeated courses in a plan (4, and the BM Instrumental/Vocal Performance drafts): "MUS 260 Applied Music
    Lessons (1 unit course taken 4 times)". The audit adds up a repeatable course's units; the planner places a
    course once. MUS 443 "taken 4 times" isn't repeatable in its catalog entry: a question for the department.
  - Advisor approvals (genuinely a person's, 16): 8 approval-only elective groups, 4 engineering study plans,
    Classics' culminating demonstration, Kinesiology ITEP's 12 activity areas and certifications, Art History's
    change-of-major consultation.
  - Bulletin text to clarify (5): BECA says 3 and 6 units of BECA 576/685/695/699; LTNS's "no more than 4 units" per
    course or combined; Kinesiology ITEP's "theory" vs "movement-based" courses and "content areas" aren't listed.
  - Data GatorPath doesn't have (12): online units (Cinema), study abroad units (French), units per term in
    production courses, the college of a GWAR course (French), COMM 150 with GE A1, partial units (COMM's "only 2
    units"), per-course unit caps, History's A-with-B/C/D overlap, SPAN 215's heritage test-out (0-3 units).
  - [ ] BA Women and Gender Studies draft: its plan ends 3 upper-division units short; the free electives' UD flag
    doesn't survive the roadmap's own elective slots (planner)
- [ ] Cross-check every served program with a second drafter (`--cross`, Codex CLI; ARCHITECTURE §6.2). Pilot
  2026-10-24, 5 programs, about 77 s each: the hand-written Applied Math agreed on every made-up student; the other 4
  had 19 disagreements: 2 Codex errors (a dropped Select One, a required pair read as a Select One), 1 question for a
  person (Chemistry's "prerequisite courses", review log), the rest Codex leaving a rule unparsed that ours expresses.
  It also led to an engine bug: a major group sharing the university's id "gwar" (17 programs) took its result (fixed).
  All 100: about 2 hours of Codex time, across usage-limit resets (a failed call is reported per program; a kept
  second draft is reused). Agreement never sets `verified`; an advisor still confirms

---

## Phase 9 — Keeping it current (ARCHITECTURE §5 "Keeping it current", D11, D12)

Robots detect and rebuild; a human approves rule changes; students re-import their DPR each term.

- [ ] Catalog year per student: the server takes the year from `profile.catalog_year` / the DPR's
  requirement term and loads `rules/<kind>/<year>/` (removes the `YEAR` ponytail in `server.py`).
  First real case: 2024-25 rules (needs the 2024-25 Bulletin PDF), see the Phase 6 `(?)`
  - 2026-10-20, for test user 1 (Fall 2025): 2025-26 rules, roadmaps and catalog rows, `verified: false`. Written by
    a rule diff from 2026-27: every quote re-found on its new page (pages 12-14 earlier), section-by-section text
    diffs read. What differs: C or better only for CSC 510 and CSC 648 (`min_grade` map, §6.2); the printed elective
    list; no course approved for 2UD; the QR 3/4 roadmap leaves out PHYS 222; F -> 6 rests on tags only. Server:
    `rules_year` ("Fall 2025" -> 2025-26, else the newest with a warning), course facts from the newest Bulletin and a
    completed course dropped since keeps its old row (D23; that closed a real DPR's 3-unit gap).
    `get_program_requirements` / `get_roadmap` take `catalog_year`. Next: 2024-25 (PDF in `data/raw/`; old GE A-E)
  - 2025-26 rules verified by ashleytzele (2026-10-20); its Winter Session line (p.1722) checked 2026-10-21
  - 2026-10-21, 2024-25 (Spring 2025 / Fall 2024 DPRs), `verified: false`. BS CS and policies by rule diff from
    2025-26 (same rules; the elective list adds CSC 649, 658; pages 39 and 46 earlier). GE rewritten from this
    Bulletin: 48 units in A1-A3, B1-B4, C1, C2 + "C1 or C2", D (D2 = US History), E, F, UD-B/C/D, matched by the
    newest Bulletin's codes (D23 exception, ARCHITECTURE §5). `amendments` built: the 3/12/25 Dean's memo waives
    Area E and the third Area C course ("Min Units Changed from 48 to 42", DPR wording). One first-time roadmap (no
    QR split). No `transfer` block (the Bulletin doesn't say what a certification meets), no 90-unit transfer cap,
    no GWAR grade minimum (not stated); a CSLG exam exists only this year. Confirm the memo on a second DPR
  - Next up (2026-10-22): (1) a second Spring 2025 DPR shows the 3/12/25 Area E/C waiver -> verify the 2024-25 files;
    (2) the 2026-27 rules still need their sign-off (verified: false); (3) done 2026-10-22: `pace.fold_last_term`
    (Phase 7); (4) more classmates (Phase 7: 5-10,
    top 3 issues). Evals on the three catalog years and Winter Session: done 2026-10-21 (Phase 7)
- [ ] Source snapshots: `rules/programs/<year>/<program>.source.txt` holds the Bulletin text each
  group was written from
  - 2026-10-22: written for 2026-27 (bs-cs, bs-applied-math) by `ingest.programs --source`; 2024-25 and 2025-26 not
    yet (their PDFs' program lists may differ: check the index first)
- [ ] Bulletin diff: new Bulletin vs snapshots → unchanged groups copied to the new year (new page
  numbers, `verified` kept); changed groups listed with old/new text, program set `verified: false`
- [x] Find the Bulletin PDF's download URL so a job can fetch it (2026-10-20): every year is on
  https://bulletin.sfsu.edu/past-bulletin-archive/ (the current one on https://bulletin.sfsu.edu/). Each year's page has
  "Download entire Bulletin as a PDF": `/past-bulletin-archive/<yyyy-yyyy>/pdf/<yyyy-yyyy>_SF_State_Bulletin.pdf`
  for 2018-19 to 2020-21, a Box link with no pattern from 2021-22 on (scrape the link), none for 2016-17 and 2017-18
  (web pages only). 2024-25 and 2025-26 are in `data/raw/`. The 2025-26 PDF's running headers wrongly say 2026-2027
  (cover and content are 2025-26), so the year comes from the file name, as the ingest already does
- [ ] Yearly GitHub Action (cron + manual trigger): fetch Bulletin if new → ingest → diff → open a
  PR. Never merges itself, never edits rule logic
- [ ] Per-term GitHub Action: offerings scrape (phase 5), once per term, cached
- [ ] Attach the rebuilt `catalog.db` to a GitHub release; README says how to download it
- [x] `amendments` rule type in `engine/rules.py` + tests; first use: the 3/12/25 Area C/E waivers
  in the 2024-25 rules (needs the memo or its DPR wording as the source). Done 2026-10-21 with the 2024-25 rules
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
