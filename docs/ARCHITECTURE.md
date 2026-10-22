# GatorPath — Architecture & Design

> Status: **Approved 2026-10-15** · Last updated: 2026-10-20 · Catalog years in scope: **2026-27, 2025-26, 2024-25**
>
> GatorPath is an **MCP server** that gives any AI assistant (Claude, Gemini CLI, ChatGPT, …)
> accurate, checkable tools for planning an SF State degree. The AI talks to the student and
> picks options; the server knows the rules and checks every plan. **The AI suggests, the code
> verifies.**

---

## 1. Goal

Help an SF State student answer, correctly:

1. **Where am I?** — what's done, what's left for my major.
2. **What's my 4-year path?** — a semester-by-semester plan that respects prerequisites,
   unit loads, and when courses are actually offered.
3. **Which direction?** — "I want cybersecurity / AI / web" → which electives, and in what order
   so the prerequisite chain works out.

### In scope (v1)

- SF State only, **BS Computer Science** first (verified), then Math: **BS Applied Mathematics** (2026-27, added
  2026-10-22; the Bulletin has no BS in Mathematics, only a BA with three concentrations, p.2089).
- 4-year roadmap / pathway planning, career-direction elective picks.
- Course history: the student's DPR (local PDF import, the main one), a typed list, or the local transcript PDF
  (D14, D20).
- Course offering patterns from the public class search.

### Not in scope yet (see §14 Roadmap)

- Transfer credit from other schools (ASSIST, out-of-state equivalency).
- Week-level schedule building (sections, times, conflicts).
- A web UI.
- Majors other than CS/Math being *verified* (they may load, but are labeled unverified).

### Non-goals

- Replacing advisors or the official Degree Progress Report (DPR). We always point back to them.
- Registering for classes or touching any SFSU account/system.

---

## 2. Users & example questions

| User | Example question |
|---|---|
| CS freshman | "I'm in MATH 226 this fall. Give me a 4-year plan." |
| CS junior | "I've done CSC 215, 220, 230, 256. I want cybersecurity — what should I take and when?" |
| Undecided / switching | "I'm a Math major with these courses. What if I switch to CS?" *(phase 8)* |
| Advisor | "Is this student's plan valid? Anything that will block them later?" |

These become the seed of the evaluation set (§12).

---

## 3. Prior art & how we're different

| Project | What it does | Gap we fill |
|---|---|---|
| SFSU Degree Planner / DPR / What-If (Student Center) | Official audit + planner: preferences (units per term), arrange plan, What-If report, refresh suggestions (seen 2026-10-16) | Shows only required/suggested classes, with no reasoning visible: no "why this term", no career direction, no switch-cost comparison. **Complement, don't replace:** it's official, so GatorPath explores and explains, the student records the plan there, and an advisor confirms |
| **Plan-Ed** (2nd place, SF Hacks × GDG 2026) | Gemini 4-yr plan + rules engine, web app | Web app only; no offering data; not reusable by other tools |
| **GatorWay** (`dixisouls/gatorway`, MIT) | Transcript → interest-based electives, FastMCP + pgvector | Local hackathon build; no transfer, no switch compare, no offering patterns |
| Stellic, Transfermatic, TransferAI | Commercial requirement / transfer planners | Not SFSU-specific career pathways |

**Our angle:**

1. **MCP-first.** The product *is* the tool server — usable from any AI client, not locked
   in one web app.
2. **Verified data.** Every rule cites a Bulletin page. There's a public eval score.
3. **Offering-aware.** Real historical schedule data ("CSC 653 is fall-only").
4. **Privacy by design.** The server stores no student data. Transcripts are parsed locally.
5. **Explains itself.** Every placed course says why it's in that term and what it unlocks, and advisor
   handoffs say who to see and how to book (§7.4, §7.5).

---

## 4. System overview

```
┌──────────── OFFLINE BUILD (once per catalog year / term) ─────────────┐
│                                                                        │
│  Bulletin PDF ──▶ ingest/bulletin.py ──▶ course, prereq, course_link   │
│  (2,932 pages)        │                                                │
│                       └─ unparsed prereq text → status=unparsed (flag) │
│                                                                        │
│  Class Search ──▶ ingest/offerings.py ──▶ offering ──▶ offered_terms   │
│  (public, HTML)                                                        │
│                                                       ▼                │
│  rules/programs/*.yaml   ─┐                    data/catalog.db         │
│  rules/roadmaps/*.yaml   ─┼─ hand-written, reviewed in git, cite pages │
│  rules/university/*.yaml ─┘  (+ office pages: URL + date checked, §5)  │
└────────────────────────────────────────────────────────────────────────┘
                                     │ read-only
┌──────────── MCP SERVER  (gatorpath, runs locally over stdio) ──────────┐
│                                                                        │
│  catalog tools      program tools        student tools                 │
│  search_courses     list_programs        audit_progress                │
│  get_course         get_program_req.     build_plan · check_plan       │
│  get_prereq_chain   get_roadmap          list_eligible_electives       │
│                                          ge_combinations               │
│                                          import_dpr (local, preferred) │
│                                          import_transcript (local)     │
│                                          save_profile · load_profile   │
│                                                                        │
│  engine/: rules.py (requirement eval) · prereq.py · planner.py         │
│  NO LLM calls · NO student data stored · deterministic                 │
└────────────────────────────────────────────────────────────────────────┘
                                     ▲ MCP (tools + one prompt)
┌──────────── AI CLIENT (Claude Desktop, Gemini CLI, …) ─────────────────┐
│  conversation · interprets career goal · picks electives · explains    │
│  MUST call check_plan before presenting a plan                         │
└────────────────────────────────────────────────────────────────────────┘
```

**Why the server has no LLM:** the client already brings one. Keeping the server deterministic
makes it free to run, easy to test, and impossible for it to "hallucinate a rule". If a future
tool truly needs a model (e.g. AI-drafted rules for new majors), that runs **offline** with
human review, never at question time.

---

## 5. Data sources

| Source | What we take | How | Notes |
|---|---|---|---|
| **SF State Bulletin 2026-27 PDF** (2,932 pp) | Courses, units, grading, prereqs, program requirements, roadmaps, GE & graduation rules | `pdftotext -raw` (the default mode interleaves the two-column course pages) → NFKC (ligatures) → parse | Official, frozen per year → solves "catalog year" versioning |
| **Class Search** `webapps.sfsu.edu/public/classservices/classsearch` | Sections per term: days/times, mode, seats, GE attributes. History back to 2000 | Polite scraper: HTML form POST with CSRF token, cached, a few requests per term | Check SFSU terms of use; later ask SFSU IT for an official feed |
| **Hand-written rules** `rules/` | Major requirement logic + roadmap variants | Humans translate Bulletin text → YAML, cite page | Reviewed like code |
| **SF State office pages** (`international.sfsu.edu/rcl`, `advising.sfsu.edu`, `cs.sfsu.edu/undergrads/advising`, …) | Only what the Bulletin leaves to that office: the F-1 final-term Reduced Course Load (`f1_final_term`) and who to see / how to book (`advising:`) | Humans copy it into `rules/` with `source: "<page>, checked <date>"` and the page's words quoted in a comment | Re-check with each Bulletin year (D21) |

### What may come from where (decided 2026-10-18, D21)

AGENTS.md golden rule 1 in full:

- **Bulletin PDF:** everything academic. Courses, units, grading, prereqs and GE tags (`catalog.db`), and the
  program, university and roadmap rules (`rules/`, `source: "p.<page>"`). It wins over every other source.
- **Class search:** only when a course ran (`offering`). Never units, prereqs or requirements.
- **SF State office pages:** only a policy the Bulletin leaves to that office (the F-1 final-term Reduced Course
  Load, from the Division of International Education; the Bulletin gives only the 12-unit minimum and continuous
  enrollment, pp.2390, 2393) and advising contacts. If a page disagrees with the Bulletin, the Bulletin's rule stays and
  the student is sent to that office; the page's version doesn't go into `rules/`.
- **A memo after publication:** only as an `amendment` (§6.2), citing the memo (or the DPR that quotes it) and its date.
- **The student's DPR:** that student's record (transfer evaluations, substitutions, waivers) in their profile, never
  in `rules/` (§5 "Keeping it current").
- **Never:** model memory, unofficial pages, or another year's Bulletin inside `rules/<kind>/<this year>/`. One
  exception (D23): an older year's GE areas match courses by the newest Bulletin's codes, through its "[Formerly …]"
  headings (2024-25 "A2" is `ge_area: 1A`), because course tags are the newest Bulletin's. The requirement itself
  (units, grades, which areas) and its page stay the older year's.

### Keeping it current (decided 2026-10-16)

Automate everything that is **detection or rebuilding**. A human approves every change to
**requirement rules**, because a wrong rule silently tells a student they're on track when they aren't.

| Change | Example | How it gets in | Who acts |
|---|---|---|---|
| New Bulletin (yearly) | 2027-28 | Scheduled job: fetch the PDF, rebuild `catalog.db`, diff against the last year, open a PR | Job drafts; a human approves the rule diff |
| Course offerings (per term) | Fall 2027 sections | Scheduled scrape, once per term (§5 etiquette) | Job only |
| Campus-wide change after publication | "Area C/E waived 3/12/25 to align with Fall 2025 CSU GE … via Dean's Memo" | Seen on DPRs first; added as an `amendment` (§6.2) citing the memo | Human |
| Personal exception | Petition, substitution (MATH 325 for MATH 225), transfer evaluation | The student's DPR import only. **Never in `rules/`** | Student re-imports each term |

- **Catalog rights:** a student is audited against **their own** catalog year (the DPR's
  `Requirement (Catalog) Term`, or `profile.catalog_year`), not the newest Bulletin. So
  `rules/<kind>/<year>/` folders are added and never replaced.
  Course facts (that a course exists, its units, prereqs and GE tags) are the newest ingested Bulletin's: the
  remaining courses are taken under it, and a newly approved course counts for the student's requirement areas
  (a Fall 2025 DPR lists "Area 2UD … or Area 5UD", though the 2025-26 Bulletin approved no 2UD course). Older years'
  rows only fill in courses dropped since (D23).
- **Rule diff, not rule rewrite:** each program keeps the Bulletin text its YAML was written from
  (`rules/programs/<year>/<program>.source.txt`, public text). The yearly job finds each group's
  heading in the new Bulletin and compares normalized text. Unchanged groups are copied to the new year
  with the new page number and keep `verified`. Changed groups are listed in the PR with old/new text,
  and that program is `verified: false` until reviewed. In a quiet year the PR is just page numbers.
- **The job never merges its own PR** and never edits rule logic. AI drafting (phase 8) may propose
  YAML for a changed group inside that PR, still human-reviewed.
- **Amendments are found through the DPR cross-check** (§7.3). The server keeps no student data, so
  it can't count how many students hit the same disagreement. Instead, the cross-check ⚠️ names the requirement and
  links a GitHub issue template that asks only for program, catalog year, requirement name and what the
  DPR says, with no grades, names or IDs. Several reports of the same thing → amendment; one → probably personal.
- **Getting updates to users:** the job attaches the rebuilt `catalog.db` to a GitHub release, so
  `git pull` + downloading the release is enough. Nobody needs the PDF.

### Known Bulletin quirks (found 2026-10-15)

- **Paired courses:** CSC 671's prereqs are printed inside the CSC 871 entry ("Prerequisites for
  CSC 671: …"). The parser must split these by course.
- **Cross-listed courses:** "offered as HUM 690 and CWL 680. Students may not repeat under an
  alternate prefix."
- **Unverifiable conditions:** "or permission of the instructor", "restricted to … majors".
  Store them as conditions, flag them, and never block on them silently.
- **GPA conditions:** "GPA of 3.0 or higher" (e.g. CSC 653, 671).
- **Concurrent enrollment:** "(may be taken concurrently)".
- **Asterisks:** `CSC 510*`, `ACCT 301*`, even `graduate-level standing*`. The legend is in "Course Descriptions,
  Symbols, and Terms" (p.2436): "An "*" denotes that a course prerequisite is enforced at the time of registration.
  Prerequisites without a "*" may be enforced by the instructor up to the end of add/drop." So `X*` parses as plain
  `X`, with no warning (found 2026-10-17; the 2026-10-15 search missed it).
- **Every course is printed twice:** once in its department section (CSC: PDF pp. 1896–1905) and
  again in the A–Z course catalog (CSC: PDF pp. 2557–2564). **Dedupe on `code`** and keep the
  department-section copy's page. If the two texts differ, store both and add a warning.
- **Page numbers:** printed page = PDF page − 1 (e.g. PDF 1906 is printed "1905"). Bulletin
  cross-references use printed numbers, so `source_page` / `source:` always use the **printed**
  number (read it from the page footer, don't assume the offset).
- **GE tags are on the course entry:** a `Course Attributes:` bullet list (e.g. `• 3UD: Arts or
  Humanities`, `• Graduation Writing Assessment`). Parse it into `course.ge_areas`.
- **Roadmap variants:** BS CS has different 4-year roadmaps by **Quantitative Reasoning (math
  placement) pathway 1/2 vs 3/4**, plus a 2-year transfer roadmap and an ADT roadmap.
- **Course renumbering:** the 2026-27 core uses **CSC 215** (older material says CSC 210).
  Never hard-code course codes from memory. Read them from the Bulletin.
- **A prereq naming a course that isn't in the Bulletin** (found 2026-10-22): MATH 400 asks for "CSC 210 or CSC 215
  or MATH 209 or MATH 309" (p.2093). There's no MATH 309 or CSC 210 in 2026-27, and the BS Applied Mathematics
  option CSC 309 isn't named. It stays as printed: a student with CSC 309 sees MATH 400 blocked and asks the
  department, rather than GatorPath guessing that MATH 309 means CSC 309.

---

## 6. Data model

### 6.1 `data/catalog.db` (SQLite, generated, git-ignored)

```sql
course(
  catalog_year TEXT, code TEXT,            -- '2026-27', 'CSC 653'
  title TEXT, units_min REAL, units_max REAL,
  description TEXT, grading TEXT,          -- 'letter', 'cr_nc', 'letter_or_cr_nc'
  ge_areas TEXT,                           -- JSON list from "Course Attributes:", e.g. ["1B","SJ"]
  source_page INTEGER,
  PRIMARY KEY (catalog_year, code)
)

prereq(
  catalog_year TEXT, code TEXT,
  raw_text TEXT,                           -- exactly as printed
  expr TEXT,                               -- JSON expression tree (6.3), NULL if unparsed
  status TEXT,                             -- 'ok' | 'partial' | 'unparsed' | 'none'
  needs_permission INTEGER,                -- 1 if any 'permission of …' branch
  PRIMARY KEY (catalog_year, code)
)

course_link(
  catalog_year TEXT, code_a TEXT, code_b TEXT,   -- code_a < code_b
  kind TEXT,                               -- 'paired' (671/871) | 'crosslisted' (HUM 690/CWL 680)
  PRIMARY KEY (catalog_year, code_a, code_b, kind)
)

offering(                                  -- ingest/offerings.py, Class Search "Academic Regular Session" (REG)
  term TEXT, code TEXT, section TEXT,      -- term like '2026-fall'
  component TEXT, mode TEXT, enrolled INTEGER,   -- LEC/LAB/SEM/ACT/SUP; In-Person/Online synchronous/…
  PRIMARY KEY (term, code, section, component)
)
offering_scrape(term TEXT, subject TEXT, sections INTEGER, scraped_at TEXT)   -- what was checked, even if empty
-- Days, times and instructors stay in the cached JSON (data/cache/offerings/) until a schedule builder needs them.

-- db.load_catalog adds `offered` to each course of a scraped subject (offered_terms):
-- {fall: [terms it ran, terms checked], spring: […], summer: […], since: '2023-spring', until: '2026-fall',
--  online_only?: ['spring']}: seasons whose latest run had only fully online sections (hybrid isn't). check_plan
-- warns an F-1 student when a spring/fall term would count under 12 with only 3 online units counted (f1_final_term).
-- A subject never scraped has no `offered` (unknown, not "never").

course_fts  -- SQLite FTS5 over code/title/description for search_courses
```

### 6.2 Hand-written rules (`rules/`, in git)

**`rules/programs/2026-27/bs-cs.yaml`** (shape):

```yaml
program: bs-cs
title: Bachelor of Science in Computer Science
catalog_year: 2026-27
verified: true                     # a human checked every rule against the Bulletin
verified_by: "<name>, 2026-10-xx"
total_units: 74
global:
  no_cr_nc: true                   # "CR/NC grades are not accepted in courses for the major"
  source: "Bulletin 2026-27 p.1905"
groups:
  - id: math_physics
    title: Mathematics and Physics
    all_of: [MATH 225, MATH 226, MATH 227, MATH 324, PHYS 220, PHYS 222, PHYS 230, PHYS 232]
    min_grade: C                   # C-or-better covers math/physics, core, advanced. NOT electives
    source: "p.1905"
  - id: core_cs
    all_of: [CSC 101, CSC 215, CSC 220, CSC 230, CSC 256, CSC 300GW, CSC 317, CSC 340, CSC 413]
    min_grade: C
  - id: advanced_cs
    all_of: [CSC 415, CSC 510, CSC 648]
    min_grade: C
  - id: senior_electives
    choose_units: 15
    from:
      - {list: [CSC 520, ...]}     # the printed list (includes 500-level CSC 520)
      - {subject: CSC, level: 600, except: [CSC 601, CSC 602, CSC 648, CSC 694]}
      - {list: [MATH 400, MATH 425, MATH 448]}
      - {subject: CSC, level: "700+", paired: false,
         except: [CSC 895, CSC 897, CSC 898, CSC 899], max_courses: 1}
    min_units_from: {subject: CSC, units: 12}
```

Rule vocabulary (keep it small; add only when a real major needs it):
`all_of`, `choose_n`, `choose_units`, `from` (list | subject+level filter | `ge_area`,
`except`, `paired`, `max_courses`), `min_units_from`, `min_grade`, `no_cr_nc`, `source`,
`waived_if` (a profile flag, e.g. `adt`: SF State Studies are waived for a verified AA-T/AS-T, p.2313),
`distinct_subjects` + `across` (GE Area 4: "the three courses … must be in at least two different
disciplines", p.2317).
`min_grade` compares letter grades; CR counts as C- ("equivalent to grades A through C-", p.2403), so CR
meets a C- minimum but not a C.
Added after the 2026-10-17 second review (Codex, against the PDF):
- `ge_area_all` (filter): the course must carry **every** listed area. US History for first-time students is
  "a Lower-Division Area 4 course with USH" (pp.2313, 2317, 2350) = `{ge_area_all: ["4", USH]}`.
- `first_time_from` (group): the filter used instead of `from` for students who began at SF State as first-time
  college students. `profile.first_time` says so; when it's missing, a profile with transfer units, transfer rows
  or `adt` counts as a transfer student.
- `level: lower | upper` on a GE filter: the course number must be below 300 / 300-699 (p.2391).
- `waiver` (text) next to `waived_if`, and `exam_credit` / `exam_note` on American Institutions groups: the
  Bulletin's exact conditions, returned with the requirements.
- Completed rows may carry `credit: extension | exam | evaluation`: they count toward units but never residence
  (`totals.residence.no_residence_credit`, p.2391).
- `course_units` (choose-group): the unit size the Bulletin names ("five 3-unit senior electives", p.1905). A
  counted course with fewer units gets a ⚠️ (the same list names 1-unit CSC 685/686), never a silent pass or fail.
- `change_of_major` (university, added 2026-10-22): the Bulletin's rule that a student who changes major meets "the
  major requirements in effect at the time they declare or change their major" (pp.2352, 2390), and how (a Change
  of Major through the Student Center after consulting faculty advisors, p.2352). compare_programs quotes it.
- University keys: `transfer.certified_ld_ge` (group ids met by Cal-GETC certification, `profile.ge_certified`,
  p.2304), `totals.max_units_from` (70 community college, 90 all transfer, 30 exam or evaluation, 4 "Projects in Teaching" 685,
  pp.2304, 2313), `max_units` per term (19 fall/spring, 14 summer; more needs a 3.0 SF State GPA and a petition,
  p.2392), `academic_load.normal_min` (12, p.2393), and the repeat policy in `repeats` (p.2392).
  `f1_final_term` (added 2026-10-18, trial 7) is the only rule from an office page instead of the Bulletin (§5 "What may
  come from where"): the one-time final-semester Reduced Course Load, how to apply, and the 3 units of online classes
  that count toward the F-1 load (`international.sfsu.edu/rcl`). check_plan's warning on an F-1 student's light
  last term quotes it.
  `totals.community_college_upper_division: {allowed: false}` (p.2304): a transfer row numbered 300-699 still counts
  as upper division but gets a ⚠️, since a profile doesn't say which transfer rows were community college work.
  A CR course that counts in the major and is CR/NC-only in the catalog stays out of `max_cr_units` (p.2313).

Added 2026-10-20 (2025-26 rules, the second catalog year):
- `min_grade` may be a map `{course: grade}` instead of one grade: only the named courses need it. 2025-26 BS CS:
  "Grades of C or better are required for CSC 510 and CSC 648" (p.1905), not every Advanced course.
Added 2026-10-20 (2024-25 rules, the old GE pattern):
- `amendments` (below) are applied by the audit: `waived: true` reports `waived_by` with the memo, other changes
  report `amended_by`.
- A `legacy_ge_areas.map` value may be a list: 2024-25 "D2" (Social Sciences: US History, p.2259) reads as
  `["4", USH]`, so a DPR's "D2 done" meets a `ge_area_all: ["4", USH]` group.
- A roadmap variant without `qr_pathway` fits every first-time student (2024-25 has one roadmap, p.1947).
- No `transfer` block when the Bulletin doesn't say which areas a certification meets (2024-25): `ge_certified` then
  gets a warning, and the DPR's `ge_done` decides.

Added 2026-10-22 (BS Applied Mathematics, the second program, pp.2129-2137):
- `one_of` (group): options, each a list of courses taken together. "Select One: MATH 209, CSC 101 & CSC 215, or
  CSC 309" = `one_of: [[MATH 209], [CSC 101, CSC 215], [CSC 309]]`. Met when every course of one option counts.
  The audit's `remaining` is one option: the one with the most done or in progress, then one with no attempt that
  didn't count (a CR can't be retaken), then the fewest units left, then the first printed (so build_plan plans it);
  `options` lists each with what's left, for the student to switch.
- `approval` (group text) + `from: {approved: true}`: courses no list names, chosen with someone's consent ("A coherent
  collection of three courses emphasizing applications of mathematics, chosen with the consent of the applied
  mathematics advisor", p.2129). Only the courses in `profile.approved[<group id>]` count: one student's approved
  courses, from their DPR or advisor, never a rule. build_plan leaves slots (ready at upper-division standing: no
  options to check), and list_eligible_electives returns the approval text instead of options.
- Roadmap items: `{one_of: [<item>, …], units}` is the first option still needed (a course in the plan's to-do list,
  or a slot), e.g. "CSC 215 (if CSC 101 taken) / SF State Studies or University Elective"; `{slot: major, group: <id>,
  count, units}` is a slot of that major choose-group (CS's `senior_elective` takes any major slot). A printed range
  ("3-4") keeps the minimum in `units`, with the range in a comment, so the units still add up to the printed minimum.

**AI-drafted rules (phase 8, D5; added 2026-10-22).** Offline, never at question time (D6):
`python -m gatorpath.ingest.programs <bulletin.pdf>` lists every bachelor's program the department pages list
("• Bachelor of … (p. 2129)"), with its requirement pages (the pages from there whose running head is its title) and
roadmap pages (heads that start with it). `--source <id>` writes the requirement pages' text, one `=== p.NNNN ===`
line per page, as `<id>.source.txt` next to the rules (public Bulletin text: the snapshot §5's yearly diff reads).
`--draft <id>` sends that text, this section and the hand-written programs to a headless AI client (`claude -p`, no
tools) and writes `rules/drafts/<year>/<id>.yaml`, which the server never reads. `check_program` (engine/rules.py)
then checks any program file, drafted or hand-written: only this vocabulary, every course code in the catalog, every
`source` page one of the program's pages, every `quote` word for word in the source text, and the groups' minimum
units adding up to `total_units`. A person fixes what it reports, moves the file to `rules/programs/<year>/`, and a
second person sets `verified`. Draft-only keys: `quote` on a group (the Bulletin words it was written from) and
`drafted_by` (client, date); a requirement the vocabulary can't express is a group with `unparsed: true`, its
`quote` and `source`, for the person to write (rule 3: flag, don't guess). A major's choice is `choose_units` (the
printed units): `choose_n` plans a 0-unit designation slot, so check_program flags it in a program file. Advising
contacts aren't drafted: they come from office pages (§5).

`amendments` (a change after the Bulletin was published; §5 "Keeping it current"): a list on a group,
each `{effective: 2025-03-12, change: {waived: true} | {choose_units: 42}, source: "Dean's memo
3/12/25 (quoted on DPRs)"}`. It's applied on top of the group and reported in the audit with its source.
Never use it for one student's exception.

**`rules/university/2026-27.yaml`:** the graduation requirements every bachelor's degree shares,
in the same vocabulary. GE areas are matched with `from: {ge_area: ...}` against
`course.ge_areas`, so no hand-copied GE course lists are needed.

```yaml
catalog_year: 2026-27
totals:                            # p.2313
  min_units: 120
  min_upper_division_units: 30
  residence: {units: 30, upper_division: 24, major: 12}
  max_cr_units: 24                 # SF State units; CR/NC-only major courses excluded
  min_gpa: {all: 2.0, sf_state: 2.0, major: 2.0}
groups:
  - {id: gwar, choose_n: 1, from: {ge_area: GW}, min_grade: C-, source: "p.2313"}
  - id: ge_1a                      # 1A, 1B, 1C, 2, 3A, 3B, 4 (6u), 5A, 5B, 5C (1u), 6,
    choose_units: 3                # 5UD|2UD, 3UD, 4UD: see p.2311 table. 43 units minimum
    from: {ge_area: 1A}
    min_grade: C-                  # Area 1 only: "CR or C- or better" (p.2314)
    source: "p.2314"
  - {id: sfss_aerm, choose_n: 1, from: {ge_area: AERM}, source: "p.2313"}   # + ESCA, GP, SJ
  - {id: ai_usg, choose_n: 1, from: {ge_area: USG}, source: "p.2313"}       # USH via Area 4
```

**Double-counting (what the engine allows):**
- Within one program's groups, a course counts **once**.
- A course can count toward GE, SF State Studies and American Institutions **at the same time**.
  The Bulletin designs it that way: one course is tagged e.g. `(Area 1B, GP, SJ)`.
- Units always count once toward the 120.
- A major course that also carries a GE tag counts for both: "an unlimited number of courses used to
  meet General Education requirements may be used to fulfill major requirements" (p.2352).

**`rules/roadmaps/2026-27/bs-cs.yaml`:** variants `qr-1-2` (p.1908), `qr-3-4` (p.1910), `adt` (p.1912).
The p.1906 "Transfer Student Roadmap (2 Year)" heading links to the ADT roadmap, so there's no separate
transfer variant. Each is a list of semesters. Each semester lists course codes or placeholders
(`{slot: GE, area: "1A", units: 3}`, `{slot: senior_elective, count: 3, units: 9}`), its printed unit
total, and a `source:` page.

### 6.3 Prerequisite expression (JSON)

```json
{"any": [
  {"all": [
    {"standing": "upper"},
    {"course": "CSC 510"},
    {"any": [{"course": "MATH 225", "min_grade": "C"},
             {"course": "MATH 325", "min_grade": "C"}]},
    {"gpa": 3.0}
  ]},
  {"permission": "instructor"}
]}
```

Leaf types: `course` (+ `min_grade`, `max_grade` for "C- or lower" retakes, `concurrent_ok`),
`ge_area` (+ `min_grade`; e.g. "GE Area 1A/A2" → `1A`), `qr_category` (list, e.g. `[1, 2]`;
**Category = roadmap QR pathway**: p.1906 "QR Pathway 1/2" links to p.1908 "Quantitative Reasoning
Category 1/2"; checked against `profile.qr_pathway`), `standing` (`lower|upper|senior|graduate`),
`gpa`, `high_school` (+ `min_grade`; self-reported), `restricted_to` (majors/programs, including bare
"Graduate Mathematics students"), `permission` (instructor|department|advisor|committee_chair),
`equivalent` ("or equivalent"), `requirement` (a named non-course requirement from a fixed list:
First-Year Math Advising Module, Advancement to Candidacy forms, approved study proposal,
"a college-level X course"), `unknown` (raw fragment).
`permission`/`restricted_to`/`equivalent`/`requirement`/`high_school`/`unknown` are **unverifiable**.
They produce a ⚠️, never a silent pass.

Status: `ok` means no `unknown` leaf; `partial` means some; `unparsed` means only unknowns;
`none` means no prereq text. Advice ("recommended", "should"), audience notes ("For students who
…") are not requirements; a prereq that is only advice is `expr: null`, `ok`. How the clause grammar reads SFSU's wording is documented at the top of
`engine/prereq.py`.

### 6.4 Student profile (passed in per call; saved only to the student's own file, on request)

```yaml
catalog_year: 2026-27
program: bs-cs
qr_pathway: "1/2"                  # math placement → roadmap variant
start_term: 2027-spring            # first term to plan
completed:
  - {code: CSC 215, grade: B+, term: 2025-fall}
in_progress: [CSC 220, MATH 227]
gpa: 3.2                           # optional; needed for GPA-gated prereqs
goal: "cybersecurity"              # optional free text; used by the AI client, not the server
chosen_electives: [CSC 652, CSC 653]   # decisions kept between sessions (save_profile), so they aren't re-discussed
plan: []                           # last plan that passed check_plan, if saved
dpr_imported: 2026-10-16           # set by import_dpr; load_profile warns when it's before the current term
ge_done: ["1A", "1B", "2"]         # only for transfer/AP/IB credit; SF State courses are
                                   # matched by their own ge_areas. Also USH/USG/CSLG. Older-catalog DPR codes
                                   # ("A2", "D", "UD-D") are translated via rules/university legacy_ge_areas
dpr_met: [MATH 225]                # required courses the DPR shows met another way (substitution/exception);
                                   # count for the requirement, not for prereqs. One student's record, never a rule
not_on_dpr: ["6"]                  # requirements the 2026-27 rules have but the student's DPR doesn't (older
                                   # catalog): left out ("waived", not "done"), with a UAC see_advisor to confirm
transfer_units: 0                  # total transfer units (from the transcript)
adt: false                         # verified AA-T/AS-T from a CCC in a similar approved major → SF State Studies waived
first_time: true                   # began at SF State as a first-time college student (default: no transfer work)
f1: false                          # F-1 visa: spring/fall terms of 12+ units, none skipped (pp.2390, 2393); the
                                   # last term under 12 is a warning + the international office
ge_certified: false                # Cal-GETC certification of lower-division GE from a CCC (p.2304)
prior_bachelors: false             # bachelor's or higher from a regionally accredited institution → GE and
                                   # graduation requirements waived, major courses still required (p.2313)
# completed rows may add `units` (variable-unit courses) and `transfer: true` (articulated
# transfer course: counts for requirements, not residence or GPA; its units are in transfer_units)
max_units_per_term: 15
current_term: 2026-fall            # set by the server from today's date (month boundaries), never by the client:
                                   # the in-progress courses fill it, so plans start after it (eval run 2026-10-18)
include_summer: false
include_winter: false              # Winter Session (2027-winter = January 2027): up to 4 units (p.1716)
```

---

## 7. MCP tools

All tools are **read-only and deterministic**. Every response includes `catalog_year`,
and wherever rules are involved, `source` page refs and `warnings[]`.

### 7.1 Catalog

| Tool | Input | Output |
|---|---|---|
| `search_courses` | `query`, `subject?`, `level?` (`lower`/`upper`/`600`…), `limit=10` | `[{code, title, units, ge_areas, offered: "fall-only"\|"both"\|"rare"\|"unknown"}]` (FTS5 keyword search; embeddings later if needed) |
| `get_course` | `code` | Full record: description, units, grading, `prereq: {raw_text, expr, status, needs_permission}`, `links`, `offered_terms`, `unlocks` (courses whose prereqs name it: "CSC 340 → CSC 413, CSC 415, CSC 510"), `source_page` |
| `get_prereq_chain` | `code` | Everything that must come before it, as a tree plus a flat ordered list, with min grades and non-course conditions. Answers "what do I need before CSC 653?" |

### 7.2 Programs

| Tool | Input | Output |
|---|---|---|
| `list_programs` | — | `[{id, title, verified}]` |
| `get_program_requirements` | `program` | Requirement groups as in the YAML, plus `verified`, plus sources |
| `get_roadmap` | `program`, `variant` | Official suggested semesters, with placeholders |

### 7.3 Student (profile in, nothing stored)

| Tool | Input | Output |
|---|---|---|
| `audit_progress` | `profile` | Per group: `satisfied`/`in_progress`/`remaining`, which courses counted where, units done vs needed; an open GE / SF State Studies / American Institutions group names the required major courses still ahead that carry it (`major_courses`: PHYS 220 for 5A, CSC 300GW for GWAR; p.2352); university totals (120 total, upper-division units, GWAR) |
| `build_plan` | `profile` | Deterministic baseline plan laid out on the Bulletin roadmap (§8): `semesters: [{term, courses, units}]`, each course with `why` ("term 3: CSC 665, CSC 620 and CSC 648 need it"; "delay it and CSC 665 slips to term 5"), unfilled `slots` (e.g. 5× senior_elective), `warnings`, `see_advisor`, `est_graduation_term`, `pace` (prereq-chain floor vs units floor, `roadmap_load` when the roadmap's own 16-17-unit terms finish sooner, `fold_last_term` when a light last term fits into one earlier term, `graduate_by` → `on_time` / `why_not`). When the profile came from `import_dpr`, what's left comes from the DPR, not our audit (§7.3 DPR-first) |
| `list_eligible_electives` | `profile`, `group_id`, `plan?`, `by_term?`, `limit=25` | Options that satisfy that group, each with description, `readiness` (`ready` / `check`: met except what can't be verified, see `cannot_check` / `blocked`: see `blocked_by`, plus `ready_by: term` when a plan opens it up), `also_covers`, and offering pattern. **The AI picks from this list using the student's goal.** A group with `approval` (an advisor's consent, no list) returns that text, no options, and `see_advisor` |
| `ge_combinations` | `profile`, `plan?`, `by_term?` | Up to 8 minimal ways (3 when more than 5 are open) to finish the open GE / SF State Studies / American Institutions requirements one course can fill, fewest courses first; the first is the fewest a bounded search found, not a proven minimum (one course for 4UD + ESCA + GP, two that split them, or one each); each part: what it covers, how many courses fit, examples (ready first, recently offered first). Requirements the major's own courses cover (GWAR via CSC 300GW) are left out |
| `check_plan` | `profile`, `plan` | `{valid: bool, errors: [...], warnings: [...]}`, each citing the rule and page. Errors include a term already started (`term_in_past`, or `term_in_progress`: the current term, which the in-progress courses fill), prereq not met by that term, grade rule, requirement not covered, excluded course, double-counting, and units over the cap. Warnings include not usually offered that term, permission needed, unparsed prereq, and GPA-gated |
| `compare_programs` | `profile`, `target` (program id) | What-if for a change of major (added 2026-10-22): `current` and `target`, each with `major_units` (done / in progress / needed), build_plan's `terms` and `est_graduation_term`; the target's major groups (counted, in progress, what's left); `courses`: `count_in_both`, `only_current` (they still count toward the 120 and GE), `only_target`; `extra_terms` (target minus current, under the same load). The target major is the Bulletin in effect when the student changes (`change_of_major`, pp.2352, 2390); GE and graduation requirements stay the student's catalog year |
| `import_dpr` | `pdf_path` (local file) | `{profile: {program, catalog_year, completed (SF State rows + transfer rows as the course they sit under, at its minimum grade), in_progress, ge_done (DPR titles of GE areas it shows done, + USH/USG/CSLG designations), dpr_met, gpa, transfer_units}, remaining: [{requirement, what, needed}], warnings}`. Personal info dropped; raw text never returned, logged or stored. Layout below |
| `save_profile` / `load_profile` | `profile`, `path` / `path` | Writes or reads the student's profile as YAML at a path **the student chose**, only when they ask. Default `~/.gatorpath/profile.yaml`; refuses paths inside the repo, relative paths and non-`.yaml` names. Replaces only an earlier GatorPath profile (never another file), atomically, mode 600. `load_profile` returns only a GatorPath profile (a mapping with `program`) and warns when `dpr_imported` is before the current term (month boundaries: spring Jan, summer Jun, fall Aug) |
| `import_transcript` | `pdf_path` (local file) | `{completed: [...], in_progress: [...], transfer_units, warnings}`, with **only** course code, grade, units and term. Name, student ID, birthdate and address are dropped. Raw text is never returned, logged or stored |

**DPR-first (decided 2026-10-16).** For "where do I stand?" the DPR beats both our audit and the
transcript. It includes the student's catalog year, transfer evaluations, substitutions and waivers.
So with a DPR, what's done and what's left come from the DPR, and `audit_progress` becomes the
**cross-check** (each disagreement → ⚠️). GatorPath still needs the student's catalog-year rules for the
choose-from groups ("Electives: 15 units needed" prints only a "View Course List" link). It also needs
prereqs and offerings to *order* what's left. The transcript is optional and adds only attempt history
(W, repeats) for the repeat/forgiveness rules. Merge it only when a real student needs that.
As built (D20, 2026-10-18): `import_dpr` is the main import and `plan_my_degree` asks for the DPR first;
`import_transcript` stays as the fallback for a student who has only the transcript. Whether to keep it: §16.8.

**Unofficial transcript layout (`SSR_TSRPT.pdf`, Oracle Analytics Publisher, confirmed
2026-10-15 from a real sample, which was not kept).** Read it with `pdftotext -layout`.
- Every page header has `Name:` and `SF State ID:`. Drop them.
- `Transfer Credits` blocks are per institution and show **totals only, with no course rows**. Return
  `transfer_units` plus a ⚠️ asking the student to give transfer GE/major credit as `ge_done`
  or confirm it on the DPR.
- A term starts with a line that is only a code: `FA2025` / `SP2026` (summer is probably `SU`,
  unconfirmed). Map it to `2025-fall` / `2026-spring`.
- Course row: `SUBJ  NNN[SFX]  DESCRIPTION  Units  Earned  Grade  Points`. The subject can have
  a space (`I R`). Join the code as `SUBJ NNN[SFX]`.
- **Blank grade + Earned 0.00 → `in_progress`.**
- A term's rows can continue after a page break. `Term GPA`/`Totals`/`Term Honor` lines are
  ignored.
- Seen so far: letter grades only. CR, W, I and repeat markings haven't appeared in a sample
  yet, so `transcript.py` reads any grade symbol (p.2403) in the same column; a repeat is just the same code twice
  (the engine's repeat rules apply). A term code other than FA/SP/SU keeps its courses without a term, with a ⚠️.
  If a row doesn't match, emit a ⚠️ with the row position, never the row text.
- Fixture: `tests/fixtures/transcript_synthetic.txt` (fake name/ID, same layout).

**DPR layout (Student Center → Degree Progress Report, printed from the browser to PDF; confirmed
2026-10-16 from a real transfer student's DPR, which was not kept).** It's Chrome's print of
`cmsweb.sfsu.edu … SSS_STUDENT_CENTER` ("My Academic Requirements"), not a report file. Read it with
`pdftotext -layout`.
- Page header: name (top right and again before `ID nnnnnnnnn`). Drop them. Every page has a
  date line and a `cmsweb.sfsu.edu` footer with `n/N`.
- `Requirement (Catalog) Term` block: `Plan: Computer Science-BS   Spring 2025` is the
  **catalog year the student is held to**. Spring 2025 is the 2024-25 Bulletin, which uses the old GE scheme:
  48 units, Areas A1-A3, B1-B4, C1/C2, D, E, UD-B/C/D, with waivers like
  "Area C/E waived 3/12/25 to align with Fall 2025 CSU GE … Min Units Changed from 48 to 42".
  A DPR on another catalog year than the loaded rules → ⚠️, never audit it against the wrong year.
- Requirement tree: group headings, `[R10742]`-style ids, one line per requirement (`MATH 226`,
  `CSC 101 and CSC 215`, `Area A2 - Written Communication I`), then a table of the courses
  "used to" / "may be used to" satisfy it.
- Table row: `CODE  DESCRIPTION  Units  When  Grade  [Notes]  [Requirement Designation]`. Long
  descriptions wrap onto the line above and below the code. `When` is `Spring 2025` / `Fall 2026`.
- **The status icons don't survive printing.** Status comes from the rows instead: a grade means
  done, a blank grade with a term means in progress, and `When` = `Fall, Spring[, Summer]` means not
  taken (that's the course's typical offering pattern). `Units: 3.00 required, 0.00 taken, 3.00 needed` /
  `Courses: 1 required, 0 taken, 1 needed` lines appear mainly on unmet requirements.
- **Transfer credit:** `SUBJ 100TR  Transfer Credit … T` (grade `T`), plus an optional designation like `GE A2/WER 1`,
  `GE D/USH`, `GE B1/B3`. The DPR doesn't name a course equivalent; the **requirement line the row sits
  under** is the mapping (`MATH 100TR` under `MATH 226` → MATH 226 met by transfer;
  `CSC 100TR` under `CSC 101 and CSC 215`). `Notes` codes (`02`, `03`, `04`) have no legend in the print.
  `TRFX 50NTR` 0-unit rows appear under "Courses Not Used".
- Substitutions show up as rows under another course's requirement (`MATH 325` under `MATH 225`).
  The 2026-27 program page (p.1905) lists only MATH 225, so an audit against our rules would disagree. That's what the DPR cross-check is for.
- **Tables paginate even in print:** `View All | First 1-10 of 33 Last`. Per-requirement tables
  were complete in the sample (`1 of 1`, `1-3 of 3`); the long summary lists (120 units, residence,
  GE minimum units) were cut at 10. If `1-10 of N` (N > 10) appears in a table the import needs, emit a ⚠️ asking the student to
  click "View All" before printing. The summary lists aren't needed: use their `Units:` lines.
- Fixture: `tests/fixtures/dpr_synthetic.txt` (fake name/ID, invented courses, same layout).

### 7.4 MCP prompt: `plan_my_degree`

The AI client is the agent: it holds the conversation and handles the what-ifs. The server stays
deterministic (D6). The prompt gives the client its workflow:

1. `load_profile` if the student has one. If `dpr_imported` is stale, ask them to re-import.
2. Get courses: `import_dpr` (preferred), `import_transcript`, or typed.
3. Ask for the math placement / QR pathway if it's unknown and lower-division math isn't done (it only changes the
   math before MATH 226; `build_plan` returns `needs_input: qr_pathway` only then).
4. Call `audit_progress` (with a DPR: as the cross-check).
5. Call `build_plan`. For "3, 4 or 5 years", call it at three loads (≈18 units + summer, 15, 12)
   and compare `est_graduation_term`, plus the roadmap's own loads when `pace.roadmap_load` is there and one heavier
   term when `pace.fold_last_term` is there. Say why a
   faster pace can't work when it can't (the prereq chain or the units per term).
6. Fill elective slots using `list_eligible_electives` plus the student's goal.
7. **Call `check_plan`. Fix any errors and re-check until `valid`.**
8. Present the plan with `why`, warnings and sources. Show every `see_advisor` item with its link
   and how to book (§7.5).
9. Offer `save_profile` so goal, pace and chosen electives carry over to the next session.

As built (2026-10-17, revised after Desktop trial 3): ask **once**, in one message, for everything missing; the
fastest path is the student's DPR. Say once that an attached PDF carries their name and ID to the AI provider
(black them out, or paste the requirement sections), then accept what they share; `import_dpr` will make this
local. Defaults instead of questions (15 units, no summer). A catalog year GatorPath has rules for (2024-25 to 2026-27) is
audited with that year's rules (D23); another year is planned with the newest rules and a warning, not refused (the DPR
wins on disagreements). Transfer rows the DPR lists under a
requirement become that course with `transfer: true`; substitutions go in `dpr_met`; GE areas in the DPR's own
codes. Then run through to a checked plan without confirmation stops. A test fails if the prompt names a tool that
doesn't exist.

What-ifs map to tools, not to new server logic:
- "Graduate a year early" → step 5 with a heavier load, and say what has to give.
- "Different direction" (AI, cybersecurity, …) → step 6 with the new goal. Required courses don't change.
- "Switch major" → `compare_programs`: what counts, what's left, how many more terms. The official version is
  the Student Center What-If report; the student confirms with the target department's advisor.

### 7.5 Advisor handoff

GatorPath is for getting a direction. An advisor and the DPR are the final word. Instead of a generic
disclaimer, tool responses carry `see_advisor: [{why, who, link, how_to_book, source}]` when:
- an exception or substitution is needed ("Exceptions must be approved in advance by a senior advisor",
  BS CS senior electives, p.1905-1906)
- a GPA-gated course would need permission (CSC 620/648/671: "GPA of 3.0 or higher; or permission")
- a semester goes over the normal unit load (fast pace)
- the DPR cross-check disagrees with our audit
- the program's rules are `verified: false`

Links and booking steps live under `advising:` in `rules/university/<year>.yaml` (UAC, Advising Hub,
DPR) and in each program's YAML (the department's contact). Each has a `role` (`major_advisor`,
`substitutions`, `college_advising`, `general_advising`, `directory`, `dpr`; a program's entry overrides the
university's for the same role, so the engine never names a department) and a `source` (Bulletin
page, DPR link, or department page + date checked). Never from memory. All SF State advising is booked in
Navigator (`sfsu.campus.eab.com`, checked 2026-10-16).

Entries name offices, never people (D15): a program gives at most its department's general contact (page,
email, Navigator), and the department routes a request to the right advisor (e.g. the senior advisor who approves
CS substitutions). A program with no `advising:` entry for a role falls back to `general_advising` (the UAC),
which routes students to their department, so adding a major never needs advisor names.

---

## 8. Planner algorithm (`engine/planner.py`)

The input is the profile, the program rules, the prereq graph and `offered_terms`.

Roadmap-led since 2026-10-18 (D17). Before that, the critical-path greedy in step 3 was the whole planner.

1. **Remaining work:** from `audit_progress`, the concrete required courses still needed, plus the roadmap
   variant's pathway courses on the way (QR 3/4: MATH 197 → 198 → 226), plus **slots** for choose-groups
   (e.g. 5 × senior elective), GE areas and free electives up to the unit totals.
2. **Roadmap first:** each term, starting at `start_term`, first takes its Bulletin roadmap semester's items: its
   courses, its GE areas (a roadmap label maps to the groups taking that area: "1" → 1A/1B/1C, "5UD/2UD" →
   either), senior electives, the US/CA Government course, SF State Studies or electives. Items already done are
   skipped, and items not ready (prereqs, season, room under the cap) carry to the next term.
3. **Greedy fill** of what's left in that term:
   - priority: the **longest downstream prerequisite chain** (critical path; CSC 415 unlocks CSC 653, so it goes
     early), ties broken by position in the roadmap variant
   - eligible = prereqs satisfied by courses completed in *earlier* terms (or in this term if `concurrent_ok`);
     corequisites go together or not at all
   - offered this season according to `offered_terms`: a course that ran in other seasons but in none of the
     checked terms of this one waits (check_plan warns if a plan puts it there); unknown, or never seen in any
     checked term, is allowed with a ⚠️ (rare isn't never)
   - fill up to `max_units_per_term`, then slots; free-elective units split to fill a term
   - **senior electives wait for real readiness (D19):** a senior-elective slot goes in once the student has
     upper-division standing and an option of that group is ready that term (prereqs met, offered that season),
     one ready option per slot in the term. Not at the roadmap's position for it
   - F-1 (`f1: true`): a spring/fall term with more terms to come is filled toward 12 units with elective slots
   - standing (`upper`/`senior`) is computed from cumulative units
4. **Two plans, one kept:** the roadmap-led plan (steps 2 + 3) and the plain greedy (step 3 alone) are built at
   the same cap. The roadmap-led one is kept when it passes check_plan and has no more terms. With
   `include_summer`, only the greedy runs: the roadmaps have no summer terms. Winter Session terms (`include_winter`)
   don't use a roadmap semester and take only GE, American Institutions and free-elective slots, up to the 4-unit
   Winter Session maximum (p.1716): Class Search history has no winter terms, so major courses stay in spring/fall.
5. **The cap stays the student's (D18):** `max_units_per_term`, default 15, the normal load (p.2393), even though
   the first-time roadmaps have 16- and 17-unit terms (qr-1-2: 16, 16; qr-3-4: 16, 16, 17, 16). A roadmap item that
   doesn't fit carries over, so the plan passes check_plan as given. When the student set no cap and the roadmap's
   own loads finish sooner, `pace.roadmap_load` says so (terms, `est_graduation_term`, the `max_units_per_term` to
   pass), and `plan_my_degree` offers it as a pace option. When the last term is light (a 1-unit free elective at
   15), `pace.fold_last_term` names the one earlier spring/fall term it fits into: the lightest that passes
   check_plan with the extra units, up to the 19-unit maximum (p.2392), latest first. A slot moves no earlier than
   the first term the plan gives that slot: check_plan can't see when senior-elective options are ready (D19). The
   plan itself keeps the cap.
6. Stop when nothing remains. Report `est_graduation_term`.
7. If no progress is possible in a term (a blocked prereq), stop and emit an error saying
   which condition blocks it. Never loop forever.

The plan is a **baseline**: elective slots stay open for the AI to fill with goal-matched picks.
`check_plan` is the single source of truth for validity, and `build_plan`'s own output must
pass it (tested).

> ponytail: roadmap-led greedy, not an optimizer. Upgrade to a constraint solver (OR-Tools CP-SAT) only if
> evals show it producing late graduations that a better order fixes.

---

## 9. Privacy & responsible AI

- **No student data at rest, except a file the student asks for.** The profile lives in the
  conversation. The server keeps no database of students and no logs of profiles. `save_profile` writes
  one YAML file at a path the student chose, on their own machine, only when they ask. It's plain
  text they can read or delete, and the server refuses to write it inside the repo. This beats AI-client memory: the
  data stays exact (no half-remembered grades), stays local, and works with any client (D13).
- **Local DPR and transcript parsing.** `import_dpr` and `import_transcript` run on the student's machine and
  return only course rows (code, grade, units, term) and requirement status. The PDF and personal info never go to
  the AI provider *through our tool*. (If a student attaches the PDF directly to the chat, that's the client's
  behavior. The prompt advises using the import tool instead.)
- **Repo hygiene.** `*.pdf`, `data/`, `transcripts/` are git-ignored. Eval profiles are
  **synthetic** only.
- **No invented rules.** Requirements come only from reviewed YAML; prereqs only from the
  Bulletin. The AI can't add a course that doesn't exist, because `check_plan` rejects unknown
  codes.
- **Honest uncertainty.** Every unverifiable condition is surfaced as a warning. Unverified
  programs are labeled. Every answer points to the DPR and an advisor as the final word.
- **Bias / equity note.** Offering-history data favors courses that ran recently. "Rare" ≠
  "never", so we say "not offered in the last N terms" rather than "not offered".

---

## 10. Error handling

| Situation | Behavior |
|---|---|
| Unknown course code | `error: unknown_course` with close matches (same subject, nearest numbers: CSC 210 → CSC 215, CSC 220) |
| Unverified program | Works, but every response has `verified: false` + warning |
| Prereq `unparsed`/`partial` | Course allowed; ⚠️ with raw Bulletin text so the student/AI can read it |
| Missing GPA when a prereq needs it | ⚠️ "requires GPA ≥ 3.0 — not provided" |
| Missing QR pathway | `build_plan` returns `needs_input: qr_pathway` instead of guessing |
| Offering data missing for a course | `offered: unknown` + ⚠️ |
| Transcript PDF not recognized | `error: unrecognized_transcript_format`; suggest typing the list |
| Planner can't make progress | Error naming the blocking condition(s) |

---

## 11. Tech stack & repo layout

- **Python 3.12+**, managed with **uv**
- **`mcp`** (official Python SDK, includes `FastMCP`), stdio transport
- **SQLite** (stdlib `sqlite3`, FTS5)
- **`pdftotext`** from poppler (`brew install poppler`) for the Bulletin and transcripts
- **`httpx` + `beautifulsoup4`** for the class-search scraper
- **`pyyaml`** for the rules, **`pytest`** for tests

```
gatorpath/
├── AGENTS.md            # instructions for AI coding agents (and humans)
├── CLAUDE.md            # → @AGENTS.md
├── README.md
├── TASKS.md             # phased task list
├── docs/ARCHITECTURE.md # this file
├── pyproject.toml
├── src/gatorpath/
│   ├── server.py        # MCP tool + prompt definitions only (thin)
│   ├── db.py            # sqlite access
│   ├── engine/
│   │   ├── prereq.py    # parse + evaluate prereq expressions
│   │   ├── rules.py     # load YAML, evaluate requirement groups (audit)
│   │   └── planner.py   # build_plan, check_plan
│   ├── ingest/
│   │   ├── bulletin.py  # PDF → course/prereq/course_link
│   │   └── offerings.py # class search → offering
│   ├── dpr.py           # local DPR PDF → profile + what's left (PII dropped)
│   └── transcript.py    # local PDF → completed courses (PII dropped)
├── rules/
│   ├── programs/2026-27/bs-cs.yaml
│   ├── university/2026-27.yaml   # GE, SF State Studies, AI, GWAR, totals
│   └── roadmaps/2026-27/bs-cs.yaml
├── evals/
│   ├── profiles/*.yaml  # synthetic students
│   └── run_evals.py
├── tests/
└── data/                # git-ignored: raw PDFs, catalog.db, scrape cache
```

---

## 12. Testing & evaluation

**Unit tests (pytest):**
- prereq parser: a golden set of ~50 real prereq strings (CSC/MATH/PHYS) → expected trees
- rules engine: audit results for hand-built profiles
- planner: every `build_plan` output passes `check_plan`; prereq order respected; unit cap
  respected
- transcript: a **synthetic** transcript fixture (fake name/ID) → only codes/grades/terms come
  out, and the fake name and ID strings never appear in output

**Eval set (`evals/`), reported in the README:**

| Metric | Target |
|---|---|
| Prereq parse coverage (CSC, MATH, PHYS) | ≥ 95% `ok`, rest flagged |
| Audit correctness on 30 synthetic profiles (hand-checked vs Bulletin) | 100% |
| Plans from `build_plan` passing `check_plan` | 100% |
| End-to-end: 30–50 student questions via a real AI client + our server; plan valid and matches the stated goal (rubric) | Report the number honestly |
| Hallucinated course codes in final answers | 0 |

As built (2026-10-18): `evals/questions.yaml` (39 questions, 5 with a follow-up) run through Claude Code and Codex CLI by
`evals/run_evals.py`, each client with only the gatorpath server (no plugins, web search or shell). Facts are computed
from the tools at scoring time; the presented plan is re-checked for the student in the question. `evals/REPORT.md`
has the numbers and a Claude vs Codex alignment table.

The end-to-end number is the resume line: *"…produced valid 4-year plans for 47/50 test
students; 0 hallucinated courses."*

---

## 13. Decisions log

| # | Decision | Why | Date |
|---|---|---|---|
| D1 | MCP server first, UI later | Most differentiated; testable immediately in Claude/Gemini CLI | 2026-10-15 |
| D2 | SFSU only; CS → Math → all majors | Every answer must be checkable; wrong-but-confident is the worst failure | 2026-10-15 |
| D3 | Python + official `mcp` SDK + SQLite | Simplest stack; no DB server; one-file catalog | 2026-10-15 |
| D4 | Bulletin **PDF** as the source, not website scraping (exceptions: offerings, D8; office policies, D21) | Official, frozen per catalog year, clean text extraction | 2026-10-15 |
| D5 | Requirements hand-translated to YAML; later AI-drafted + human-reviewed | Bulletin prose has exceptions a parser would get wrong | 2026-10-15 |
| D6 | No LLM inside the server | Client brings the model; server stays free, testable, non-hallucinating | 2026-10-15 |
| D7 | Course input: typed list **and** local transcript import | Easy start + smooth UX, PII never leaves the machine via our tool | 2026-10-15 |
| D8 | Offering patterns from public class-search history | Bulletin lacks term offerings; history shows fall-only/spring-only | 2026-10-15 |
| D9 | GE + university requirements in v1, not phase 8 | "What's left?" is wrong without GE; GE tags are already on every course entry | 2026-10-15 |
| D10 | Commit `evals/catalog-2026-27.json` (the catalog rows the eval profiles use) | CI has no PDF; a test keeps it equal to `catalog.db` | 2026-10-16 |
| D11 | Automate detection and rebuilds; a human approves rule changes | Manual upkeep goes stale, but auto-written rules can be confidently wrong (§5 "Keeping it current") | 2026-10-16 |
| D12 | Audit each student against their own catalog year; post-publication changes are cited `amendments` | DPRs keep the entry-year Bulletin plus memo waivers (sample: Spring 2025 + 3/12/25 GE waiver) | 2026-10-16 |
| D13 | Memory = a profile file the student owns (`save_profile`/`load_profile`), not client memory, not none | Exact and local, works with any client; saves goal/pace/elective decisions so they aren't re-discussed; one small tool call per session | 2026-10-16 |
| D14 | DPR-first: what's done/left comes from the DPR; our audit cross-checks it | The DPR includes transfer evaluations, substitutions and waivers we can't know | 2026-10-16 |
| D15 | Advisor handoffs name offices (department contact, UAC), never individual advisors | Names change and every major would need its own; the department and the UAC route students to the right advisor | 2026-10-17 |
| D16 | The AI client is the agent; what-ifs and advisor handoff go through the prompt + tool fields (numbered D15 until 2026-10-18, a duplicate) | Keeps the server deterministic (D6); advisor links are sourced data, not model memory | 2026-10-16 |
| D17 | Planning is roadmap-led: each term starts from its Bulletin roadmap semester, and the critical-path greedy fills the rest; the plain greedy is kept only if it finishes sooner (§8) | Trial 8: the student asked for the Bulletin roadmap as the foundation (GE Area 1A in term 2, …). It's the official suggested order (§3: complement, don't replace), and a new QR 1/2 freshman went from 9 terms to 8 at 15 units | 2026-10-18 |
| D18 | The default cap stays 15 though the first-time roadmaps have 16-17-unit terms; `pace.roadmap_load` reports the roadmap's own loads as an option | 15 is the normal load (p.2393): above it is an overload with an advisor handoff (§7.5), which a default plan shouldn't need. The plan must pass check_plan as given | 2026-10-18 |
| D19 | Senior electives go in once an option is ready that term, not at the roadmap's position | Trial 5 left Spring 2027 at 9 units while the slots waited for the roadmap's order; the scenario review found them waiting for the roadmap instead of their prereqs | 2026-10-18 |
| D20 | `import_dpr` is the main import; `import_transcript` is the fallback (D7 kept, D14 as built) | The DPR has the catalog year, transfer evaluations and substitutions; the transcript's transfer blocks are totals only (§7.3). In trial 7 the two PDFs disagreed on a current course and the newer DPR was used | 2026-10-18 |
| D21 | Office policies the Bulletin leaves to an office (F-1 final-term Reduced Course Load) and advising contacts may come from that office's page, cited as page + date checked; the Bulletin wins on any conflict (§5 "What may come from where") | Trial 7: an F-1 student's last term was padded to 12 units, but the international office allows a one-time final-semester RCL (`international.sfsu.edu/rcl`). The Bulletin states only the 12-unit minimum | 2026-10-18 |
| D22 | Work phases in order, but trial feedback can pull work forward, and an item waiting on a person or a real document stays open while later phases go on (TASKS.md header) | Trial 1 needed `build_plan` (Phase 4) to answer "when do I finish?"; Phase 2's `verified: true` needs a second person; Phase 6's CR/W/repeat sample and the DPR Notes legend need real documents. Phases 5 and 6 were done with those open | 2026-10-18 |
| D23 | Requirements from the student's catalog year (`rules/<kind>/<year>/`, picked from `profile.catalog_year` or the DPR's requirement term); course facts from the newest Bulletin, older rows only for dropped courses | A Fall 2025 DPR (test user 1's): the 2025-26 BS CS needs C or better only in CSC 510 and CSC 648, not all of Math/Physics, Core and Advanced as 2026-27 does. Courses still to take run under the newest Bulletin (new courses such as CSC 603; COMM 301 is 2UD from 2026-27) | 2026-10-20 |

---

## 14. Roadmap (detail in TASKS.md)

- **Phase 0, Foundation:** repo, tooling
- **Phase 1, Catalog:** Bulletin → courses + prereqs
- **Phase 2, Rules:** BS CS + GE/university requirements + roadmaps, audit
- **Phase 3, MCP v0:** read-only tools, tried in Claude Desktop
- **Phase 4, Planner:** `build_plan`, `check_plan`, electives, prompt
- **Phase 5, Offerings:** class-search history
- **Phase 6, Transcript import**
- **Phase 7, Evals + demo + first real users**
- **Phase 8, Expand:** Math + `compare_programs` (switch-major cost), AI-drafted rules for more majors
- **Phase 9, Keeping it current:** catalog year per student, yearly Bulletin diff job, per-term
  offerings job, `amendments`, released `catalog.db`

**Later:**
- transfer credit (ASSIST for CA community colleges; similarity + Course Equivalency
  Request drafting for out-of-state)
- week-level schedule builder from live sections
- web roadmap UI on top of the same server

---

## 15. Glossary

- **Bulletin:** SFSU's official yearly catalog of courses and degree requirements.
- **Catalog year:** the Bulletin year whose rules a student follows.
- **DPR:** Degree Progress Report, SFSU's official degree audit.
- **GE:** General Education requirements.
- **GWAR:** Graduation Writing Assessment Requirement (e.g. CSC 300GW).
- **QR pathway:** Quantitative Reasoning / math placement. It selects the roadmap variant.
- **ADT:** Associate Degree for Transfer (California community colleges).
- **MCP:** Model Context Protocol, the standard way to expose tools/data to AI clients.

---

## 16. Open questions

1. ~~**Asterisk meaning** in prereqs (`CSC 510*`)~~ Closed 2026-10-17: enforced at registration (p.2436), see §5.
2. ~~**Class search terms of use / rate limits**~~ **Decided 2026-10-17: scrape politely.** The class search page
   has no terms of use (footer: privacy notice only); `webapps.sfsu.edu/robots.txt` is `User-agent: *` with no
   Disallow; the privacy notice says nothing about automated access. The CSU Responsible Use Policy (ICSUAM 8105,
   campus copy revised 2013-06-05) asks for mission-consistent use (3.2), no misrepresented identity (4.4.4), and use
   "within the limits of system capacities" that doesn't "interfere with the operation ... or ... use ... by others"
   (4.5). The etiquette in AGENTS.md meets those: honest User-Agent, cache, ≥ 2 s apart, once per term, stop if asked.
   Not found: SF State's own IT acceptable-use page. Still to do: ask SF State ITS/Registrar for a data feed, and
   decide before phase 9 whether a released `catalog.db` may carry the offering history.
3. ~~Transcript format~~ **Resolved 2026-10-15**, see §7.3. Still unseen: CR, W, I, repeat
   markings, summer code.
4. ~~GE in v1~~ **Resolved 2026-10-15:** GE, SF State Studies, American Institutions and GWAR are
   in v1 (phase 2), via `rules/university/2026-27.yaml` + `course.ge_areas`.
5. ~~Repeat / grade replacement~~ **Resolved 2026-10-15** (p.2392 "Repeating Courses", p.2406
   "Grade Forgiveness"):
   - C or better, or CR → no repeat unless the course is repeatable for credit.
   - Below C (including W, WU, AU, IC, RD, RP) → one more attempt. A 3rd needs chair consent.
   - Forgiveness: up to 16 SF State units, where the lower grade leaves the GPA. Fall 2017 onward;
     not for academic dishonesty.
   - No repeats after 28 repeated units.
   - Past the 16-unit limit, both grades count in the GPA, but units count once.
   - **Engine:** use the best attempt for requirements, count units once, ⚠️ on 2nd/3rd attempts.
6. **License:** MIT proposed when the repo goes public.
7. ~~Major course ↔ GE double-counting~~ **Resolved 2026-10-16:** p.2352 "Duplicate Use of Credit
   Between the Major and GE": unlimited, units counted once.
8. **Keep `import_transcript`?** (D20) The DPR covers what's done and left; the transcript adds only attempt
   history (W, repeats), and no sample with those rows has been seen yet (TASKS Phase 6). Decide in Phase 7 from
   real users: keep it as the fallback, or drop it.
