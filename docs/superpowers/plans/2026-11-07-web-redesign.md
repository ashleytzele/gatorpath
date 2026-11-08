# GatorPath website redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild every page of the GatorPath website in the agreed calm, card-free style, with the chat beside the plan,
plus the engine and API changes the new pages need.

**Architecture:** Three small Python changes first (math-placement gate, DPR details for the web, the AI allowance), then
the web: shared pieces move out of the 3,800-line `App.tsx` into focused files, pure logic goes in `logic.ts` with a
Node self-check, and each page is rebuilt one task at a time. Plan, Electives & GE and Schedule stay in `App.tsx`, so the
workspace state they share stays in one place.

**Tech Stack:** Python 3.12, FastAPI, pytest (`uv run pytest`); React 19 + TypeScript + Vite (`web/`); Node 25 runs `.ts`
files directly for the logic check.

**Spec:** `docs/superpowers/specs/2026-11-07-web-redesign-design.md` (read it with this plan; it wins on any wording).
Visual reference: `.superpowers/canvas/redesign-2026-11-07/*.dc.html` (made-up data; the canvas's DPR-style row names on
"Does this look right?" are illustration only).

## Global Constraints

- AGENTS.md golden rules hold: no student data at rest; no LLM calls in `server.py`/`engine/`; `check_plan` decides
  every change. No new dependency (front or back) without asking.
- Branch `web-app`. One commit per task; end each message with the session's `Co-Authored-By:` line.
- Fonts: Source Serif 4 (headings), Source Sans 3 (body), Source Code Pro (landing labels), from Google Fonts in
  `web/index.html`. Colours: keep `index.css` tokens (ink #1b1f1d, muted #4f5753, faint #5f6864, line #e3e6e4, accent
  #1f6b4f, green-soft #e3f2ec, blue #2c5fa8, amber #8a4f12 / #fff4df, lavender #5f4b8b, forest #1f332d).
- No widget cards or stat tiles: a section is a heading over a 2px ink rule, rows split by 1px lines. Allowed on purpose:
  the first screen's method cards, floating cards, landing media frames.
- Button words: **Swap** replaces something chosen, **Select** takes an option, **Choose** fills an open choice. Never
  "Change" or "Pick". No "AI pick" tag anywhere.
- WCAG 2.2 AA: 4.5:1 text, keyboard reachable, visible focus, labels, `prefers-reduced-motion` respected; every page
  works at 390px wide.
- Advisor links come from the API's `see_advisor` (rules), never typed into the web code (an existing test checks
  `advising.sfsu.edu` and `/undergrads/advising` never appear in `web/src`).
- **Web check** (run in every web task, all must pass):
  `(cd web && npx tsc --noEmit && npm run build) && node web/src/logic.check.ts && uv run pytest -q tests/test_api.py`
- **Look check** (every web task): `uv run gatorpath-web`, open http://127.0.0.1:8000 at 1440×900 and 390×844 (Chrome
  device toolbar), walk to the task's page with **Type my courses** (MATH 226 B Spring 2026, CSC 215 B Spring 2026, CSC
  220 in progress) or **I'm a new student**, and confirm the task's listed points. No console errors.

## Review Focus

- **No DPR** (typed or new student): Your record has no DPR statuses, no Courses Not Used, no waiver text; every section
  must still render from the audit, with nothing empty or broken. Checked in Task 7's look check.
- **No AI** (no `ANTHROPIC_API_KEY`, a 503, or a 429 at the limit): Building moves on in seconds, the chat shows why and
  disables its input, and GatorPath's own suggestions (finish sooner, lighter terms, summer, Winter Session) still work.
  `leftText` and `suggestions` cases in Task 4's logic check; Tasks 9-10 look checks run once with the key unset.
- **A plan that fails its check**: the heading keeps today's "You could graduate … once the problems above are fixed",
  and a change that leaves the plan invalid logs an amber line, not "✓ Plan updated". Task 10's logic check.
- **Phone width**: floating cards become bottom sheets, the week becomes a day list, the chat a bottom bar. Each owning
  task's look check at 390.
- **Keyboard only**: a floating card takes focus when it opens, Esc closes it, focus returns to the row that opened it.
  Task 4's look check, then each card task.

---

### Task 1: Ask for math placement only while it can change the plan

**Files:**
- Modify: `src/gatorpath/engine/planner.py` (the `needs_input: qr_pathway` condition in `build_plan`, ~line 884)
- Modify: `src/gatorpath/server.py` (new `qr_pathways` near `build_plan`), `src/gatorpath/api.py` (new route)
- Test: `tests/test_planner.py`, `tests/test_api.py`

**Interfaces:**
- Produces: `planner.pathway_courses(roadmap: dict) -> dict[str, list[str]]`: for each roadmap variant with a
  `qr_pathway`, that pathway's MATH courses in semester order, from its first one through the *gate*, leaving out courses
  every QR variant shares except the gate. The gate is the first MATH course of a variant whose first MATH course
  appears in every QR variant. `{}` when there are no QR variants or no gate.
- Produces: `server.qr_pathways(program: str, catalog_year: str | None = None) -> dict` →
  `{"catalog_year": str, "pathways": [{"pathway": "1/2", "courses": [{"code": str, "title": str}]}], "warnings": []}`.
- Produces: `GET /api/pathways?program=<id>&catalog_year=<optional>` returning `qr_pathways(...)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_planner.py
def test_pathway_courses_are_the_math_before_the_shared_gate():
    road = yaml.safe_load((ROOT / "rules/roadmaps/2026-27/bs-cs.yaml").read_text())
    assert pathway_courses(road) == {"1/2": ["MATH 226"], "3/4": ["MATH 197", "MATH 198", "MATH 226"]}

def test_placement_isnt_asked_once_the_gate_course_is_done():
    p = {"catalog_year": "2026-27", "program": "bs-cs", "start_term": "2027-fall",
         "completed": [{"code": "MATH 226", "grade": "B", "term": "2026-spring"},
                       {"code": "CSC 101", "grade": "A", "term": "2026-spring"}]}
    assert "needs_input" not in plan_for(p)          # MATH 227 and 225 are left, the pathway changes nothing
    del p["completed"][0]
    assert plan_for(p)["needs_input"] == "qr_pathway"

# tests/test_api.py
def test_pathways_name_each_placements_first_math():
    got = client.get("/api/pathways", params={"program": "bs-cs"}).json()["pathways"]
    assert [(p["pathway"], [c["code"] for c in p["courses"]]) for p in got] == [
        ("1/2", ["MATH 226"]), ("3/4", ["MATH 197", "MATH 198", "MATH 226"])]
    assert all(c["title"] for p in got for c in p["courses"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_planner.py -k "pathway or gate_course" tests/test_api.py -k pathways`
Expected: FAIL (`pathway_courses` not defined, 404 on `/api/pathways`).

- [ ] **Step 3: Implement**

In `build_plan`, ask only when `variant is None` and the gate is still required: `gate in required` where
`gate = next(iter(paths.values()))[-1]` from `pathway_courses(roadmap)`; with no gate keep today's "any MATH below 300"
rule. Replace the "MATH below 300" ponytail comment with one naming the new rule. `qr_pathways` loads the roadmap the way
`roadmap_plan` does (`roadmap_path(year, program)`) and titles from the catalog. ARCHITECTURE.md §7 step 3 ("Ask for
the math placement…") gets the new condition in one sentence.

- [ ] **Step 4: Run the tests, then the whole suite**

Run: `uv run pytest -q`
Expected: all pass (the existing freshman `needs_input == "qr_pathway"` test still holds).

- [ ] **Step 5: Commit** — `git commit -am "Ask for math placement only while the pathway's gate course is still ahead"`

---

### Task 2: The DPR's details for the web

**Files:**
- Modify: `src/gatorpath/dpr.py` (`cross_check` around a new `disagreements`), `src/gatorpath/server.py` (`dpr_profile`),
  `src/gatorpath/api.py` (import route passes `details=True`)
- Test: `tests/test_dpr.py`, `tests/test_api.py`, `tests/test_assistant.py`

**Interfaces:**
- Produces: `dpr.groups_for(block: dict, audit: dict, university: dict) -> list[str]`: the audit group ids a parsed DPR
  requirement is about (course codes → the groups listing them in `counted`/`in_progress`/`remaining`; GE titles →
  `translate_ge` → area groups; a GWAR title → `["gwar"]`; else `[]`).
- Produces: `dpr.disagreements(dpr, audit, university, program=None) -> list[tuple[str, list[str]]]`: each cross-check
  text with the group ids it names; `cross_check` returns `[t for t, _ in disagreements(...)]` (unchanged output).
- Produces: `server.dpr_profile(read_text, program=None, read_statuses=None, details: bool = False)`. With `details`
  the result also has `not_used: [{"code", "units", "term", "grade"}]` (the DPR's "Courses Not Used" rows),
  `notes_by_group: {group_id: [waiver text]}` and `warnings_by_group: {group_id: [cross-check text]}`. Always:
  `profile["sf_state_gpa"]` when the DPR prints one. MCP's `import_dpr` keeps `details=False` (D31: lean results).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dpr.py (reuse test_cross_check_flags_only_real_disagreements's audit and university)
def test_each_disagreement_names_its_group():
    audit["groups"][0]["status"] = "remaining"                     # ge_1c, the DPR's Area A1
    got = dict(disagreements(DPR, audit, university))
    a1 = next(t for t in got if t.startswith("Area A1"))
    assert got[a1] == ["ge_1c"]
    assert next(ids for t, ids in got.items() if t.startswith("Units toward the 120")) == []

def test_a_waiver_is_kept_under_its_group():
    block = {"id": "x", "title": "Area A1 - Oral Communication", "kind": "ge", "status": "waived", "rows": [],
             "needed": None, "waived": "Area A1: Requirement waived 3/12/25 (Dean's memo)."}
    assert groups_for(block, audit, university) == ["ge_1c"]

# tests/test_api.py
def test_the_web_import_carries_the_dprs_details(monkeypatch):
    monkeypatch.setattr(dpr, "read_pdf_bytes", lambda data: DPR)
    got = upload(b"%PDF-1.4 x").json()
    assert [r["code"] for r in got["not_used"]] == ["TRFX 50NTR"]
    assert {"notes_by_group", "warnings_by_group"} <= set(got) and got["profile"]["sf_state_gpa"] == 3.15
    assert "not_used" not in server.dpr_profile(lambda: DPR)     # the MCP tool's result stays lean

# tests/test_assistant.py
def test_the_sf_state_gpa_never_reaches_the_model():
    assert assistant.hide({"sf_state_gpa": 3.15, "program": "bs-cs"}) == {"program": "bs-cs"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -q tests/test_dpr.py -k "names_its_group or waiver" tests/test_api.py -k details tests/test_assistant.py -k sf_state`
Expected: FAIL (`disagreements`, `groups_for` not defined; no `not_used` key). The `hide` test may already pass; keep it.

- [ ] **Step 3: Implement** `groups_for`, `disagreements` (the current `cross_check` body, each `out.append` paired
  with its ids; the "Not found on this DPR" line pairs with the missing groups' ids), `cross_check` as a wrapper, and the
  `details` branch of `dpr_profile`. The web route passes `details=True`.

- [ ] **Step 4: Run the whole suite** — `uv run pytest -q` → all pass (`test_cross_check_flags_only_real_disagreements`
  unchanged).

- [ ] **Step 5: Commit** — `git commit -am "The web's DPR import carries Courses Not Used, waivers and disagreements by group"`

---

### Task 3: The AI allowance and the reply's shape

**Files:**
- Modify: `src/gatorpath/api.py` (`admit`, `/api/assist`), `src/gatorpath/assistant.py` (`SYSTEM`)
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `api.admit(who: str) -> dict[str, int]` returns `{"hour": <left this hour for who>, "day": <left today for
  everyone>}` after counting the request (still raises 429 as today).
- Produces: `/api/assist` responses add `"left": {"hour": int, "day": int}`.

- [ ] **Step 1: Write the failing test** (in `test_the_ai_helper_has_an_hourly_limit_per_address_and_a_daily_one_for_everyone`,
  which sets `PER_HOUR = 3`, `PER_DAY = 5`; replace its first assert):

```python
    answers = [ask() for _ in range(3)]
    assert [a.status_code for a in answers] == [200, 200, 200]
    assert [a.json()["left"] for a in answers] == [{"hour": 2, "day": 4}, {"hour": 1, "day": 3}, {"hour": 0, "day": 2}]
```

- [ ] **Step 2: Run it** — `uv run pytest -q tests/test_api.py -k hourly_limit` → FAIL (`KeyError: 'left'`).

- [ ] **Step 3: Implement** `admit`'s return and merge it into the route's result. In `assistant.SYSTEM`, add one line:
  "Answer in one short sentence, then at most three short bullets; no headings." (the chat shows a lead and bullets).

- [ ] **Step 4: Run** — `uv run pytest -q` → all pass.

- [ ] **Step 5: Commit** — `git commit -am "The chat answer says how many AI questions are left; replies are a lead and bullets"`

---

### Task 4: Web foundation: shared pieces, logic and its check, the floating card

**Files:**
- Create: `web/src/ui.tsx` (moved, not changed: `Icon`, `iconPaths`, `Tooltip`, `Logo`, `Button`, `StatusBadge`,
  `Header`, `Stepper`, `Footer`, `useLoad`, `Loading`, `ErrorCard`, `plainText`, `nearbyTerms`, `NAVIGATOR`,
  `ASK_ADVISOR`, `PRIVACY`, `DEMO`), all exported
- Create: `web/src/logic.ts`, `web/src/logic.check.ts`, `web/src/FloatingCard.tsx`, `web/src/StatusMark.tsx`
- Modify: `web/src/App.tsx` (imports), `web/src/api.ts` (types), `web/index.html` (fonts), `web/src/index.css`
  (tokens, `.floating-card`, `.status-mark`, step-dot colour), `tests/test_api.py` (`APP` reads every `web/src/*.ts*`
  except `*.check.ts`)

**Interfaces:**
- `api.ts` types: `Left = { hour: number; day: number }`; `Assisted.left?: Left`; `ImportResult.not_used?: Taken[]`,
  `notes_by_group?: Record<string, string[]>`, `warnings_by_group?: Record<string, string[]>`; `Profile.sf_state_gpa?:
  number`; `Group.met_by?: string`; `Pathway = { pathway: string; courses: { code: string; title: string }[] }` and
  `getPathways(program: string, catalogYear?: string): Promise<Pathway[]>`.
- `logic.ts` (no React; `import type` only):
  - `termLabel(term?: string | null): string` (moved from App.tsx)
  - `type Suggestion = { id: "sooner" | "lighter" | "summer" | "winter" | "choose"; label: string }`
  - `suggestions(plan: PlanResult, options: Options, open: number): Suggestion[]` — "Finish sooner (graduate <term>)"
    when `pace.fold_last_term`; "Lighter terms (graduate <term>)" when `pace.normal_load`; "Add summer" / "Add Winter
    Session" when not included; "Choose my open courses" when `open > 0`. At most 3, in that order.
  - `describeChange(before: Semester[], after: Semester[]): string` — e.g. "BIOL 100 added to Spring 2027 · CSC 645
    moved to Fall 2028"; "" when nothing moved.
  - `type Mark = "complete" | "progress" | "incomplete" | "exception" | "warning"`;
    `markOf(g: Group, warned: boolean): Mark` (warning wins; satisfied → complete; waived → exception; in_progress →
    progress; else incomplete) and `countSection(groups: Group[], warned: Set<string>): { done: number; total: number;
    warned: number }` (done = complete + exception, a warned group counts only as warned).
  - `goalText(interests: string[], after: string[]): string` — "AI / Machine Learning, Data Science; after graduating:
    Graduate school"; "Not sure yet" dropped; "" when nothing.
  - `pathwayLine(courses: { code: string; title: string }[]): string` — one course: "You start with Calculus I (MATH
    226) in your first term."; more: "You take MATH 197 and MATH 198 first, then Calculus I (MATH 226)."
  - `withPlanned(profile: Profile, semesters: Semester[]): Profile` — planned course codes added to `completed` with
    grade "A" and their term (for the "With your plan" audit).
  - `leftText(left?: Left): string | null` — `null` when unknown or more than 5 left; "1 question left this hour" /
    "N questions left this hour" (or "today" when the day is the smaller).
- `FloatingCard({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode })` — renders
  inside a `position: relative` row as `<div role="dialog" aria-label={label} className="floating-card">` with an ×
  button; on mount saves `document.activeElement` and focuses its first focusable; Esc and × call `onClose`; on unmount
  focus goes back to the saved element. CSS: under the row, as wide as the row (`left/right: 8px`), pointer, shadow,
  `max-height: 380px; overflow: auto`; at ≤640px a bottom sheet (`position: fixed; left: 0; right: 0; bottom: 0`).
- `StatusMark({ mark }: { mark: Mark })` — the five marks from the spec, with a visually hidden status word.

- [ ] **Step 1: Write the failing check** `web/src/logic.check.ts` with `node:assert/strict`, covering at least:

```ts
assert.equal(pathwayLine([{ code: "MATH 226", title: "Calculus I" }]), "You start with Calculus I (MATH 226) in your first term.");
assert.equal(goalText(["Data Science", "Not sure yet"], ["Graduate school"]), "Data Science; after graduating: Graduate school");
assert.equal(leftText(undefined), null);
assert.equal(leftText({ hour: 1, day: 20 }), "1 question left this hour");
assert.deepEqual(countSection([g("a", "satisfied"), g("b", "waived"), g("c", "in_progress"), g("d", "remaining")], new Set(["d"])),
  { done: 2, total: 4, warned: 1 });
assert.equal(describeChange([term("2027-spring", [slot])], [term("2027-spring", ["BIOL 100"])]), "BIOL 100 added to Spring 2027");
assert.deepEqual(suggestions(planWith({}), {}, 0), []);          // no pace options, nothing open: no suggestions
assert.equal(withPlanned(profile, [term("2027-spring", ["CSC 256"])]).completed!.at(-1)!.code, "CSC 256");
```

- [ ] **Step 2: Run it** — `node web/src/logic.check.ts` → fails (module not found).

- [ ] **Step 3: Implement** `logic.ts`, the type additions, `ui.tsx` (a move: App.tsx imports from it), `FloatingCard`,
  `StatusMark`, the fonts and tokens. Step dots not reached yet use `var(--faint)` instead of `var(--sage)`. Headings use
  the serif token site-wide; body the sans.

- [ ] **Step 4: Web check** passes. **Look check:** every current page still works; headings are serif; step numbers not
  reached yet are dark grey.

- [ ] **Step 5: Commit** — `git commit -am "Web: shared pieces in ui.tsx, logic.ts with its check, the floating card"`

---

### Task 5: Landing page

**Files:** Create `web/src/Landing.tsx` (replaces `Landing` in App.tsx); modify `web/src/index.css`, `tests/test_api.py`.

**Interfaces:** `Landing({ start }: { start: () => void })` (same as today).

- [ ] **Step 1: Failing test** in `tests/test_api.py`:

```python
def test_the_landing_page_says_only_what_is_true():
    majors = len(list((ROOT / "rules/programs/2026-27").glob("*.yaml")))
    assert f"Rules for {majors} majors" in APP and "Watch the demo" in APP
    assert "Trusted by" not in APP and "testimonial" not in APP.lower()
```

- [ ] **Step 2:** `uv run pytest -q tests/test_api.py -k landing` → FAIL.
- [ ] **Step 3: Implement** the eleven sections in the spec's order and copy (nav with scroll links; centered hero with
  the mono label; the 16:9 demo frame whose poster is a slice of the Plan route and a chat exchange, play button saying
  the video is coming soon, no autoplay; the facts strip with the majors count from Step 1 written as a constant with a
  comment naming the count's source; 2×2 "What you get"; the route split; "Helpful, not official"; three steps drawn like
  the step bar; five questions in `<details>`; the forest panel; footer with the Navigator link). Display 76px /
  -0.035em, 46px under 860px.
- [ ] **Step 4: Web check** passes. **Look check:** scroll links land under the sticky nav; questions open with keyboard;
  hero and grid stack at 390.
- [ ] **Step 5: Commit** — `git commit -am "Web: the landing page in the product-launch structure"`

---

### Task 6: Your record, first screen

**Files:** Create `web/src/Record.tsx` (moves `RecordScreen`, `UploadPanel`, `TypedPanel`, `NewStudentPanel`,
`MajorSelect`, `RecordEditor` from App.tsx); modify `web/src/index.css`, `tests/test_api.py`.

**Interfaces:** `RecordScreen({ done }: { done: (profile: Profile, imported?: ImportResult) => void })` (unchanged).

- [ ] **Step 1: Failing test:** the upload panel no longer shows `{PRIVACY}` and has the how-to steps outside `<details>`:

```python
def test_the_first_screen_shows_how_to_get_the_dpr():
    record = (ROOT / "web/src/Record.tsx").read_text()
    assert "How to get your DPR" in record and "help-box" not in record and "{PRIVACY}" not in record
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement:** keep the three method cards as they are (text 15/14px instead of 13px); under Upload, the
  drop zone, then "How to get your DPR": a 16:9 placeholder ("Video coming soon · about 2 minutes, with captions") beside
  the four steps, shown only under Upload. Serif heading "Tell us what you've completed.", line "Choose one. You'll check
  everything before we build your plan."
- [ ] **Step 4: Web check**; **look check:** the three methods switch panels; steps sit under the video at 390.
- [ ] **Step 5: Commit** — `git commit -am "Web: the first screen with the how-to video placeholder and steps"`

---

### Task 7: "Does this look right?" (Your record), with the plan's coverage

**Files:** Modify `web/src/Record.tsx` (new `RequirementsView`, `ReviewScreen` uses it), `web/src/App.tsx`
(`ReviewScreen` call site), `web/src/index.css`, `web/src/logic.check.ts`.

**Interfaces:**
- `RequirementsView(props: { profile: Profile; imported: ImportResult | null; audit: Audit; withPlan?: Audit; edit:
  (profile: Profile) => void; leave?: { label: string; go: () => void } })` — `withPlan` is the audit of
  `withPlanned(profile, semesters)`; when given, the "With your plan" column and "Planned · <term>" show. `leave`
  defaults to "Looks right → Your goals".
- `ReviewScreen` = summary + `RequirementsView`, as a screen.

- [ ] **Step 1: Failing check** in `logic.check.ts`: `warnedGroups(profile: Profile, imported: ImportResult | null):
  Set<string>` (add it to `logic.ts`: `not_on_dpr` ∪ keys of `warnings_by_group`) returns `{"ge_2", "ge_4"}` for a profile
  with `not_on_dpr: ["ge_2"]` and an import with `warnings_by_group: { ge_4: ["…"] }`, and an empty set for `(profile,
  null)` (the no-DPR case).
- [ ] **Step 2:** `node web/src/logic.check.ts` → FAIL (`warnedGroups` not defined).
- [ ] **Step 3: Implement** per the spec's Your record section: summary (major, catalog year; units incl. in progress,
  upper-division, Overall GPA `profile.gpa`, SF State GPA `profile.sf_state_gpa ?? totals.gpa_sf_state`); sections in
  today's bucket order (GE, SF State Studies, American Institutions, other university, major), all closed; a section line
  is chevron · `StatusMark` (complete only when every group is) · name · amber ! when warned · "done/total" under a
  "Complete" label (and "With your plan" when given). Warned groups = `profile.not_on_dpr` ∪ keys of
  `imported.warnings_by_group`. Opened: each group's mark and word, its detail line (`units_needed`, `units_done`), its
  notes (`notes_by_group`), its warnings in plain words (with "Put it back" for not-on-DPR, as today), "Met by transfer
  credit" when `met_by === "ge_done"`, and course rows (code, title from `audit.courses`, units, term and grade from
  `profile.completed`, Edit). Edit and "+ Add a course your DPR doesn't show" open a `FloatingCard` with today's
  `RecordEditor` controls. "Courses not used for a requirement" (`imported.not_used`) closed at the end.
- [ ] **Step 4: Web check**; **look check:** with a typed record (no DPR) every section renders; opening, Edit, Add and
  Esc work by keyboard; at 390 the count stays on the section line.
- [ ] **Step 5: Commit** — `git commit -am "Web: Your record reads like a better DPR, from GatorPath's audit"`

---

### Task 8: Your goals

**Files:** Create `web/src/Goals.tsx` (replaces `GoalsScreen` in App.tsx); modify `web/src/App.tsx` (state for the chip
picks), `web/src/index.css`.

**Interfaces:** `GoalsScreen(props: { profile: Profile; saved: Options; picks: { interests: string[]; after: string[] };
needs?: string; build: (options: Options, picks: { interests: string[]; after: string[] }) => void })`. `options.goal =
goalText(picks.interests, picks.after)`. Units: "12 units" → 12, "About 15 units (recommended)" → no
`max_units_per_term` (the roadmap's loads), "18 units" → 18.

- [ ] **Step 1: Failing test:** `tests/test_api.py` asserts `"Advanced options" not in APP` and `"What's your first
  term?" not in APP`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** the seven questions from the spec (chips + typed box for 1 and 2, `GOALS` lists stay; dropdown
  3; radios 4 and 6; checkboxes 5; question 7 when `!profile.qr_pathway && (brandNew || needs === "qr_pathway")` and
  `getPathways(profile.program)` returns pathways, each option's line from `pathwayLine`, plus the Gator Smart Start link
  `https://gatorsmartstart.sfsu.edu/pathways`). The `needs === "start_term"` question stays (a typed record with no terms
  still needs it) but in the new style.
- [ ] **Step 4: Web check**; **look check:** a typed chip becomes a removable chip; "Not sure yet" clears the others;
  arrow keys move between radio buttons.
- [ ] **Step 5: Commit** — `git commit -am "Web: Your goals as numbered questions, no Advanced options"`

---

### Task 9: Building waits for the AI's first fill

**Files:** Create `web/src/Building.tsx` (replaces `BuildingScreen`); modify `web/src/App.tsx` (`Built` gains the fill's
result; `AppWorkspace` no longer fills on mount).

**Interfaces:** `BuildingScreen(props: { profile: Profile; options: Options; notes: string[]; done: (plan: PlanResult,
audit: Audit, filled: Assisted | null) => void; back: () => void })`. `filled` is the AI's first answer, or `null` when
skipped, unavailable or failed; `AppWorkspace` starts from `filled` when given and shows its `reply` as the first chat
message.

- [ ] **Step 1: Failing test:** `tests/test_api.py` asserts the workspace no longer starts a fill on mount:
  `"started.current" not in APP`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement:** `buildPlan` + `getAudit` as today; then, when the plan has open slots or notes, `assist(...)`
  with no messages. The checklist reveals one line about every 0.9 s for the planner's steps (each line naming a real
  step, the first with the units found), then the AI line with "about a minute" and "Skip and choose my electives myself
  →", which calls `done(plan, audit, null)` and makes the late answer be ignored (a `cancelled` ref). A 503/429/error goes
  on with `null` and the chat's first message says why. Reduced motion: no ring or shimmer animation.
- [ ] **Step 4: Web check**; **look check** twice: with a key (the fill lands before the plan opens) and without (moves on
  in seconds).
- [ ] **Step 5: Commit** — `git commit -am "Web: Building waits for the AI's first fill, with a skip"`

---

### Task 10: The chat

**Files:** Create `web/src/Chat.tsx` (replaces `ChatPanel`); modify `web/src/App.tsx` (`AppWorkspace`: the chat's lines,
suggestions, undo, locks), `web/src/index.css`, `web/src/logic.check.ts`.

**Interfaces:**
- `logic.ts` adds `type ChatLine = { kind: "me" | "ai" | "ok" | "refused"; text: string; codes?: string[] }` and
  `changeLine(before: Semester[], after: Semester[], check: Checked, graduation: string): ChatLine` — `ok` with
  "<describeChange> · graduate <term> · checked against the Bulletin" when `check.valid`, else `refused` with the first
  error in plain words; `codes` are the courses that moved.
- `ChatPanel(props: { lines: ChatLine[]; suggestions: Suggestion[]; onSuggest: (id: Suggestion["id"]) => void; onSend:
  (text: string) => void; onUndo: () => void; onShow: (codes: string[]) => void; busy: string; left?: Left; aiDown:
  boolean; hide: () => void })` — Undo shows only on the last `ok` line.
- `Work` gains `aiBusy: boolean` (already there) used by every course button to disable itself.

- [ ] **Step 1: Failing check** in `logic.check.ts`: `changeLine` on an invalid check gives `kind: "refused"`; on a
  valid one, `kind: "ok"` with "checked against the Bulletin" in `text`.
- [ ] **Step 2:** `node web/src/logic.check.ts` → FAIL.
- [ ] **Step 3: Implement** the chat per the spec (no box; header; the AI's text through today's `Rich`; the student's
  bubbles; suggestions under the latest AI line: "sooner" → `applyFold`, "lighter" → `whatIf({max_units_per_term})`,
  "summer"/"winter" → `whatIf({include_…: true})`, "choose" → `fill`; each logs `changeLine`; Undo restores `previous`;
  Show in plan switches to the Plan tab, scrolls to the first code's row and highlights the rows for 2.5 s; the growing
  input with the send arrow, Enter sends, Shift+Enter breaks; `leftText` under it; at 0 the input is disabled with when
  it's back; "Checking against the Bulletin…" while busy). Fix the lost choice: every Swap/Choose/Select button gets
  `disabled={work.aiBusy}`, and `choose()` no longer runs while the AI works. Hide turns it into an "Ask GatorPath" button (today's
  `docked` state); on a phone a bottom bar opens it full screen.
- [ ] **Step 4: Web check**; **look check:** a suggestion changes the plan and logs a line; Undo restores; with the key
  unset the input explains and the pace suggestions still work.
- [ ] **Step 5: Commit** — `git commit -am "Web: the chat logs every change with Undo and runs pace changes without the AI"`

---

### Task 11: The Plan tab

**Files:** Modify `web/src/App.tsx` (`PlanView`, `Tabs`, `AdvisorCards`, `CourseDrawer` → a `CourseCard` in a
`FloatingCard`, `Tab` type), `web/src/index.css`, `tests/test_api.py`.

**Interfaces:** `logic.ts` adds `splitWhy(why?: string): { now: string; opens: string }`: the planner's `why` (clauses
joined by "; ") with the "opens N senior-elective option(s): …" clause pulled out as `opens` (just the course list) and
the rest as `now`, first letter capitalised, "(s)" dropped. `type Tab = "plan" | "electives" | "schedule" | "record"`;
"record" isn't in the tab bar: it renders
`RequirementsView` with `withPlan` and `leave = { label: "Back to your plan", go: () => setTab("plan") }`, and its edits
re-check the plan as it stands (`checkPlan`, like the chat's `update_record`) and log a `changeLine`.

- [ ] **Step 1: Failing tests:** in `logic.check.ts`, `splitWhy("needed before CSC 220 in this plan; opens 2
  senior-elective option(s): CSC 685, CSC 686")` deep-equals `{ now: "Needed before CSC 220 in this plan", opens: "CSC 685,
  CSC 686" }`; and in `tests/test_api.py`:

```python
def test_the_plan_tab_has_no_what_if_row_or_ai_tags():
    assert "What if I" not in APP and "AI pick" not in APP and '"progress"' not in APP
```

- [ ] **Step 2:** run both → FAIL.
- [ ] **Step 3: Implement** per the spec's Plan tab section: heading lines (keep today's problem-state wording), coverage
  line with "See your requirements"; the route (year labels on the line; dots for in progress, register next with "See
  its schedule →", later, smaller for summer/winter, flag at graduation); course rows with "Not chosen yet" for slots;
  `CourseCard` in a `FloatingCard` (description cut to two lines with More, Needs/Offered/Why now/Opens, Bulletin page,
  Ask about this course, Swap it for choices; an open choice lists options to Select from `getElectives`); "! N things to
  check" closed; "Talk to an advisor" rows from `see_advisor` (who, reasons, `link`, `how_to_book`'s Navigator link,
  `contact`, `location`) and the Advising Hub row from its `directory` entry; Print. Remove the What-if section, the
  Lighter/Faster buttons, the Progress tab and `ProgressView`.
- [ ] **Step 4: Web check**; **look check:** one card open at a time; Esc returns focus; "See your requirements" and
  "Back to your plan" keep the plan's state.
- [ ] **Step 5: Commit** — `git commit -am "Web: the Plan tab as a route, with course cards and the advisor list"`

---

### Task 12: Electives & GE tab

**Files:** Modify `web/src/App.tsx` (`ElectivesView`, `ChoiceRequirementRows`, `ElectiveDrawer` → an options
`FloatingCard`, `OptionCard` → rows), `web/src/index.css`, `tests/test_api.py`.

- [ ] **Step 1: Failing test:** no button says Change or Pick:

```python
def test_buttons_say_swap_select_or_choose():
    words = re.findall(r">\s*([A-Z][A-Za-z ]{1,30}?)\s*(?:<|\{)", APP)
    assert not [w for w in words if re.match(r"(Change|Pick)\b", w)]
    assert "Swap" in APP and "Select" in APP
```

- [ ] **Step 2:** run → FAIL (today's "Change").
- [ ] **Step 3: Implement** per the spec's Electives & GE section (open sections; the CSC-units bar line; rows with Swap
  or Choose; the card: current course "In your plan", three options with Select and a readiness line in words, "N more
  that fit", "N not possible that term" with each reason from `blocked_by`/`not_offered`, "Or ask the chat to choose
  one"). A selection runs today's `choose()` and logs a `changeLine`.
- [ ] **Step 4: Web check**; **look check:** Swap opens under the row, Select swaps and logs, Undo restores.
- [ ] **Step 5: Commit** — `git commit -am "Web: Electives & GE with Swap and an options card"`

---

### Task 13: Schedule tab

**Files:** Modify `web/src/App.tsx` (`ScheduleView`), `web/src/index.css`.

- [ ] **Step 1: Failing check** in `logic.check.ts`: add `blockOf(meeting: Meeting, start: number, hourPx: number): {
  top: number; height: number } | null` (parses `time` like "10:00AM - 11:15AM" the way today's `hours()` does; `null`
  when there's no time) and assert a 10:00–11:15 meeting from an 8:00 start at 60 px/hour is `{ top: 120, height:
  75 }`. Move today's `hourOf`/`hours` into `logic.ts` for it.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** per the spec's Schedule section: the week (hours trimmed to the classes, 60 px per hour, blocks
  showing code, time, and room · type from `meeting.where`); the day list at ≤640px; "Your sections" in today's layout
  (seats pill, big class number with Copy); "Other sections ⌄" opens a `FloatingCard` (time, room, class number,
  instructor, seats, Fits or "Clashes with …" from `clashes_with`, See on week, Select / Select and move others →
  today's `setPeek` and "Use this section" logic); hover or focus on a section previews it dashed on the week; See on week
  scrolls to the week with the preview bar ("Previewing … · Select section 01 · Cancel"). Not offered or always clash:
  one amber line with "Ask the chat to move one" (sends that request to the chat). Terms after the next one say to check
  Class Search when their schedule is out. No "Copy all".
- [ ] **Step 4: Web check**; **look check:** the dashed preview matches the section's time; Select and move others leaves
  "No time clashes".
- [ ] **Step 5: Commit** — `git commit -am "Web: Schedule with times and rooms on the week and an Other sections card"`

---

### Task 14: Docs, then a full look and critique

**Files:** Modify `docs/ARCHITECTURE.md` (§7.6 routes: `/api/pathways`, the import's details, `left`; §7.7 the chat's
GatorPath suggestions and Undo), `TASKS.md` (tick the redesign items, note anything left), `AGENTS.md` (Layout: the new
`web/src` files).

- [ ] **Step 1:** Update the three docs.
- [ ] **Step 2:** `uv run pytest -q` and the **web check** → all pass.
- [ ] **Step 3:** **Look check** of the whole flow at 1440 and 390, once with the key and once without; then
  `/impeccable critique` and `/impeccable audit` and fix what they find that the spec doesn't decide otherwise.
- [ ] **Step 4: Commit** — `git commit -am "Docs: the redesigned site's routes, chat and layout"`
