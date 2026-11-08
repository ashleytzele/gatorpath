# GatorPath website redesign: design

2026-11-07 · branch `web-app` · decided with the project owner page by page, each one described in text first, then
prototyped.

- **Visual reference:** the private Claude canvas https://claude.ai/artifact/7bqvvHgUn4oNUD3qWRAxWE (one board per page,
  interactive in Play). Its source is copied to `.superpowers/canvas/redesign-2026-11-07/*.dc.html` (not in git). Every
  course, grade, section and name on it is made up; the boards "Ledger" and "Checklist" are rejected alternatives.
- **Decision log:** TASKS.md "Now — Redesign every page" records each decision as it was made. This document is the
  version to build from; where they differ, this one wins.

## Why

The site works, but it looks like a generic dashboard: stat tiles and widget cards on every page, side drawers, a
What-if row of buttons. The owner wants it calm, clear and trustworthy (PRODUCT.md), reading more like a better version
of the student's DPR than like an app. The chat is the product (`chat-is-the-product`): the page shows what the chat
did. The redesign keeps every behaviour that works today and changes how it is laid out and worded.

## Goals

- Every page from the landing page to Schedule in one consistent style: serif headings, sans body, thin lines between
  sections instead of cards, one clear next step per screen.
- "Does this look right?" lets a student check every requirement, course, grade, unit count and GPA against their DPR
  before planning.
- The chat sits beside the plan from the start, and every change it makes is visible, checked and undoable.
- The AI helper stays inside a $20 a month budget.

## Non-goals

- No change to the engine's rules or planning logic, except the two fixes under "Engine and API work".
- No accounts or sign-in in this design (see "Not in this design").
- No new features without a planner behind them (time of day, work schedule, online/in person, minors).

## Anti-goals (failure even if it works)

- Widget cards, stat tiles, gradient heroes, badges, mascots, "AI pick" tags (PRODUCT.md anti-references; the owner
  rejected the tags).
- Side drawers for details (the owner called the course drawer "lame").
- Anything made up presented as real: no fake logos, testimonials, statistics or claims. "Rules for 108 majors" is the
  count of `rules/programs/2026-27/*.yaml`.
- A plan change the student can't see or undo, or a Bulletin check whose verdict is hidden (golden rule 6, D35).

## Constraints

- AGENTS.md golden rules hold. In particular: no student data at rest (rule 5); no LLM calls in `server.py`/`engine/`
  (rule 4); `check_plan` decides every change (rule 6).
- Keep today's behaviour: the record editor (add a course, change a grade, finish or remove one), "Not on your DPR"
  with one put-back control, units the DPR's way ("74 of 120, incl. 19 in progress"), the AI's first fill, the chat's
  tools, what-ifs (now through the chat), section clash checks, the advisor handoff, Print.
- Stack: React + Vite in `web/` (`App.tsx`, `index.css` with tokens, `api.ts`). Stdlib-first; ask before adding a
  dependency. Fonts load from Google Fonts like any stylesheet.
- WCAG 2.2 AA (PRODUCT.md): 4.5:1 text, keyboard use with visible focus, labels, reduced motion; every page works at
  390px wide.

## Site-wide decisions

**Flow.** Landing → Your record (first screen, then "Does this look right?") → Your goals → Building → Your plan with
three tabs: **Plan · Electives & GE · Schedule**. The Progress tab is dropped (see Your record).

**Step bar.** The site's current stepper, unchanged in look: numbered dots joined by lines, the current step a filled
green dot with a light ring, finished steps a soft green dot with ✓; on a phone only the dots and the current label.
Steps: Your record · Your goals · Your plan · Your schedule (Schedule tab = step 4). One change: the numbers on steps
not reached yet are dark grey (#5f6864) instead of light green, for contrast. The Building page has no step bar.

**Type and colour.** Headings Source Serif 4 (600; the landing page's display uses 500 at 76px with -0.035em
tracking), body Source Sans 3, small section labels on the landing page Source Code Pro. Keep `index.css`'s tokens:
ink #1b1f1d, muted #4f5753, faint #5f6864, line #e3e6e4, accent green #1f6b4f, green-soft #e3f2ec, blue #2c5fa8
(in progress), amber #8a4f12 / #fff4df (warnings), lavender #5f4b8b (exceptions), forest #1f332d.

**No cards.** Sections are a heading over a 2px ink rule; rows are separated by 1px lines. Exceptions the owner chose
on purpose: the three method cards on the first screen (today's design), the floating cards below, and the landing
page's media frames.

**Status marks** (Your record and wherever requirements show): ✓ Complete (filled green), ◐ In progress (half blue),
○ Incomplete (grey ring), E Exception (lavender), ! Warning (amber). The words are always next to or under the mark.

**Floating card.** One pattern for "show me more about this row": a card under the row with a small pointer, as wide as
fits the column, one open at a time, closed by ×, Esc, or clicking the row again; focus moves into it and back to the
row on close; on a phone it is a sheet from the bottom. Used for: a course on the Plan tab, a choice on Electives &
GE, "Other sections" on Schedule. Never a side drawer, never an inline dropdown that pushes the rows below.

**Button words.** **Swap** replaces something chosen, **Select** takes an option, **Choose** fills an open choice.
Never "Change" or "Pick".

**The chat** (on every Your plan tab, docked on the right on a laptop from the start; a "Ask GatorPath" bar at the
bottom on a phone that opens full screen; Hide turns it into an "Ask GatorPath" button):
- No box: a thin line between it and the page. Header: small green route icon, "GatorPath", Hide.
- The AI writes a short lead sentence and a few bullets. Its 2–3 suggested replies show only under its latest message.
- The student's messages are light green bubbles on the right.
- Every plan change gets one line: "✓ Plan updated · what changed · the graduation term · checked against the
  Bulletin" with **Show in plan** (scrolls to and briefly highlights the rows) and **Undo**. A change the check refuses:
  amber "! Not changed · why".
- While the AI works: a small spinner and "Checking against the Bulletin…", and the plan's course buttons are locked.
- Input: a box that grows with the text, a round send arrow inside (grey until there's text); Enter sends, Shift+Enter
  is a new line. Under it: "Every change is checked against the Bulletin. Your DPR and an advisor have the final word."
- Suggested replies come from GatorPath, not the model: the plan's own figures (finish sooner from
  `pace.fold_last_term`, lighter terms from `pace.normal_load`, add summer, add Winter Session, choose my open courses).
  Tapping a pace one runs today's what-if (`build_plan` / `check_plan`) without the AI, costs no AI question, and is
  logged like any change. Only free text and "choose for me" go to the AI. (My call; see below.)
- Undo is on the latest change line only (a newer change removes the older line's Undo). It restores the whole state
  from just before that change: plan, choices, sections and any record change the chat made. (My call.)
- Limits: under the input once 5 or fewer questions are left, "5 questions left this hour"; at zero the input is
  disabled with when it's back and "Your plan, schedule and course lists still work without the chat"; the daily limit
  for everyone gets one line that it's back tomorrow.

## Page by page

### Landing

Structure borrowed from the Figma template "Modern Product Launch" (plugin-value-scrum.figma.site); content is
GatorPath's own. Top to bottom:

1. Sticky nav: logo, What you get · How it works · Questions (scroll links), round green **Start planning**.
2. Centered hero: mono label "For SF State students"; "Plan your path to graduation in 5 minutes."; one line; **Start
   planning →** and **Watch the demo** (scrolls to the video); "No account needed. Your DPR is never stored."
3. Demo video in a large frame with 28px corners: poster with a play button, no autoplay or sound, captions, made-up
   DPR. Until it is recorded, the poster is a slice of the Plan page and a chat exchange, and play says it's coming soon.
4. A mono strip: ✓ Built from the 2026–27 SF State Bulletin · ✓ Rules for 108 majors · ✓ Every plan checked · ✓ Your
   DPR is never stored. (Take the count from `rules/` at build time.)
5. "What you get": "Everything your DPR leaves you to work out.", four items in a 2×2 grid with lines: Your record, read
   for you · A plan that passes the Bulletin · Ask, and it changes · Next term's schedule.
6. "See your whole route": split, a route picture on the left, four points and Start planning on the right.
7. "Helpful, not official": GatorPath does (reads your DPR, plans every term, checks against the Bulletin, builds next
   term's schedule) / Only SF State does (official audit · your DPR; approvals and substitutions · your advisor;
   registration · Student Center).
8. "How it works": three steps drawn like the step bar.
9. Questions (closed, + to open): Is GatorPath official? · Is my data safe? (today's PRIVACY text) · What's a DPR, and
   how do I get it? · Does it work for my major? · Does it use AI? (only electives and the chat; daily limit; planning
   works without it).
10. Dark green (#1f332d) rounded panel: "Ready before your registration date." with Start planning.
11. Footer: links, Talk to an advisor (Navigator), "Unofficial student-built tool, not affiliated with SF State."

### Your record: first screen

Step bar, serif "Tell us what you've completed.", "Choose one. You'll check everything before we build your plan."
The three method cards exactly as the site has them now (icon box, "Recommended" on Upload, check circle, green border
and soft shadow when chosen), text at 15/14px instead of 13px. Under **Upload my DPR**: today's drop zone, then "How
to get your DPR": a 16:9 video (placeholder until recorded) beside the four written steps (Student Center → Degree
Progress Report → Expand All, then View All on every list → Print → Save as PDF). The video and steps show only under
Upload. **Type my courses** and **I'm a new student** keep today's panels (the new-student panel asks the first term).
The privacy sentence is removed from this screen (the landing page keeps it).

### Your record: "Does this look right?"

Reads like a better DPR, but shows **GatorPath's reading of the DPR**: the audit the plan is built from, so the student
checks what the plan will use (owner's decision, 2026-11-07). The rows are the audit's groups from `rules/` for the
student's catalog year, so names follow the Bulletin ("GE 1A English Composition", "Mathematics and Physics"); the
canvas board's DPR-style row names ("A1 Oral Communication", one line per major course) are illustration only.
Statuses are the DPR's own where a DPR was imported (D36, the import already reads its icons) and the audit's
otherwise, so typed-course and new students get the same page, and an Edit updates it. Wherever GatorPath and the DPR
disagree (a `cross_check` line), the group it names shows a Warning with that disagreement in plain words.
- Summary like the DPR header: major and catalog year, then one row of numbers: units (71 of 120, incl. 12 in
  progress), upper-division units, Overall GPA, SF State GPA. No "requirements complete" figure.
- Requirements in the DPR's order: General Education, SF State Studies, American Institutions, other university
  requirements, the major. **Every section starts closed.** A section line: chevron, status mark (✓ when all complete,
  ○ otherwise), the name, an amber ! when anything inside has a warning (no "1 warning" text), and the count "8/16"
  under a small "Complete" column label, the ! just left of the count.
- Counting: a requirement with a warning counts only as a warning; complete = Complete or Exception; everything else,
  in progress included, is incomplete.
- Opened: each requirement with its mark and status word, its detail line ("9 units required, 6 taken, 3 needed"),
  any warning as one amber note (with "Put it back" for "Not on your DPR"), and its courses: code, title, units,
  term, grade, Edit.
- Waivers and exceptions in the DPR's own words where the DPR has them ("Waived 3/12/25 to align with Fall 2025 CSU
  GE, Dean's memo"); a GE area met by transfer credit (`ge_done`) says so instead of listing a course.
- "Courses not used for a requirement" closed at the end, then "+ Add a course your DPR doesn't show" and **Looks
  right → Your goals**. The record editor's actions move onto the rows (Edit) and that link; the side panel goes.
- **After a plan exists** (reached from the Plan's "See your requirements"), the section lines gain a second column
  "With your plan" (8/16 → 15/16) and opened requirements show "Planned · Spring 2027". This replaces the Progress tab.
  Edits there work as the chat's `update_record` does today: the plan is re-checked as it stands (no rebuild, no new AI
  fill, choices kept), the change is logged in the chat with Undo, and a failed check shows its problem. "Looks right"
  reads "Back to your plan" there. (My call.)

### Your goals

Serif "What matters to you?", one line, "Goals for Computer Science, B.S.", then numbered questions divided by lines:
1. What are you interested in? Chips for the major, several allowed, "Not sure yet" (clears the others), and a box
   "Something else? Type it and press Enter" whose entries become removable chips.
2. What do you want to do after you graduate? The same, with Start working · Graduate school · Not sure yet.
3. When do you want to graduate? Dropdown, "Follow the recommended pace" first.
4. How many units can you take each term? Radio buttons 12 · 15 (recommended) · 18 units; note "More than the
   roadmap's load needs an advisor's OK."
5. Will you take summer or Winter Session classes? Two checkboxes.
6. Are you on an F-1 student visa? Radio No · Yes · Prefer not to say; Yes shows "Every fall and spring stays at 12
   units or more. For other visa questions, ask the international office."
7. Only when needed: math placement, two choices with one line each from the major's roadmaps (CS: QR 1/2 "You start
   with Calculus I (MATH 226) in your first term", p.1908; QR 3/4 "You take MATH 197 and MATH 198 first, then Calculus
   I", p.1910) and "Not sure? Find your Pathway/Category on Gator Smart Start" (the Bulletin's link). No "I'm not sure".
   Shown up front only to a new student, or one who hasn't reached that course; otherwise only if build_plan asks.

No first-term question (the new-student card asks it), no Advanced options. Bottom: "You can change these later." and
**Build my plan →**. Questions 1–2 go into the profile's `goal` as text; the AI helper reads it when choosing electives.

### Building

Today's look (ringed route icon, "Building your plan from the Bulletin…", the line under it, three shimmering
placeholder bars), and it now **waits for the AI's first fill too**. A checklist grows one line per step, each running
with a spinner then ✓ with its result: reading your DPR (units found) · mapping requirements · semesters from the
roadmap · prerequisites in order · units per term · offerings checked · choosing electives and GE with AI ("about a
minute") · checked against the Bulletin. Every line names something the planner or the AI really does. During the AI
step: "Skip and choose my electives myself →", which opens the plan with its choices open and ignores the AI's late
answer. Without the AI helper the page moves on in seconds. Ends with "Your plan is ready · Opening your plan…".

### Your plan: Plan tab

- Tabs as plain text with an underline under the current one; chat on the right.
- "You can graduate **Spring 2029**", "5 semesters after this one · 2 choices still open", "Your longest prerequisite
  chain, CSC 220 → CSC 340 → CSC 413 → CSC 648, sets this date.", and one coverage line with "See your requirements".
- The route: one column down a vertical line, the year on the line where it starts; a dot per term: half blue "In
  progress" (rows grey), filled green "Register next" with "See its schedule →", hollow for later terms, a smaller dot
  for summer or Winter Session, a flag at "Graduate".
- Course rows: code, title, units, what it counts for. An open choice is a plain row whose last column says "Not chosen
  yet" in amber. No "AI pick" tag, no "Choose a course" link.
- Clicking a course opens the floating card: code, title, units; the description cut to two lines with More; Needs ·
  Offered · Why now (plain words, not the planner's text) · Opens; Bulletin page · Ask about this course · Swap it
  (choices only). An open choice's card lists courses to **Select**, or "ask the chat to choose one".
- Below: "! N things to check" closed; "Talk to an advisor" with one row per office `see_advisor` names, each with its
  own links, place and hours from the rules' `advising:` (CS department: Book in Navigator, CS advising page, email;
  Undergraduate Advising Center: Navigator, advising.sfsu.edu, email; the international office only for F-1 students),
  each row's reason being that student's reasons, and "Not sure who to ask? The Advising Hub"; Print my plan.
- Gone: the What-if row and the Lighter / Faster buttons. Those become the chat's suggestions.

### Your plan: Electives & GE tab

Heading line says what the choices were picked around and how many are open. Open sections: Major electives (with one
thin bar "15 of 15 units planned, 12 of 12 in CSC"), GE still needed, SF State Studies and American Institutions, Free
electives when any. Rows: requirement · the course or "Not chosen yet" · term · **Swap** or **Choose**. That opens the
floating card: the current course ("In your plan"), up to three options with **Select**, readiness in words ("Ready",
"Check: needs …"), when it's offered, "also counts for …", then "N more that fit", "N not possible that term" (each with
its reason) and "Or ask the chat to choose one". A selection is checked and logged in the chat with Undo.

### Your plan: Schedule tab

- Next term only ("Your Spring 2027 schedule"); later terms say to check Class Search when their schedule is out.
- "No time clashes · N classes · N units"; seats' date with a Class Search link.
- A Mon–Fri week trimmed to the class hours; one soft block per meeting showing code, time, and room · type; a
  day-by-day list on a phone; classes with no set time in one line under it; an unchosen choice says so with a link to
  Electives & GE.
- "Your sections" in today's layout: code, title and a seats pill (green "12 seats open", amber "Full · N waitlist
  spots"); section, type, days and time, room; mode and instructor with ratings; on the right, big, "Class number
  #24816" with Copy.
- "Other sections ⌄" opens the floating card under the course: each section with time, room, class number, instructor,
  seats, "Fits" or "Clashes with …" from GatorPath's clash check (never worked out in the browser), **See on week**
  (scrolls up to the week with it dashed in, and a bar "Previewing … · Select section 01 · Cancel"), and **Select**, or
  "Select and move others" when it clashes. Pointing at a section shows it dashed on the week when the week is in
  view; clicking a block on the week opens that course's card.
- Problems (not offered, always clash) are one amber line with "Ask the chat to move one". Print. No "Copy all class
  numbers".

## AI limits and budget

$20 a month. The Anthropic console's spend limit on the API key's workspace is the hard ceiling (the owner sets it).
The site's defaults are already 30 AI requests a day for everyone and 5 an hour per address (`api.py`, commit
db3b337), from an unmeasured estimate of about 2 cents a question on Haiku 5.5. The AI's first fill counts as one.
Prompt caching on the assistant's fixed system prompt and tools, then measuring the real cost per question, comes
before raising the limits.

## Engine and API work this design needs

1. **Lost choice during the AI fill (bug).** Today the fill starts when the plan opens; "Choose a course" and "Change"
   stay enabled, `choose()` clears the busy line in its `finally`, and the fill's `setState(withAnswer(r))` then
   replaces the plan. Fixed by running the first fill on Building and locking course buttons during any AI change.
2. **Math placement asked too often.** `build_plan` asks for `qr_pathway` while any MATH below 300 is left; ask only
   while the first math course the pathways share (CS: MATH 226) isn't done or in progress, read from the roadmap
   variants, with a test.
3. **The API returns what the pages show that it doesn't return yet:** questions left (with each chat answer); the
   DPR's "Courses Not Used" rows and its waiver/exception text per requirement (`dpr.py` parses both; `ImportResult`
   doesn't carry them); the DPR's SF State GPA in the profile (parsed, not yet kept); each `cross_check` line tied to
   the group it names, for the Warnings; plain-word "why" text for the course card.

## Not in this design

- **Sign-in with an SF State email** (a one-time code, the chat only, a hashed email and a count stored, a quota per
  student). The owner's concern is API spend; the spend limit and daily cap cover the bill, sign-in would cover
  fairness. It goes against golden rule 5, so it needs a decision in ARCHITECTURE.md before any design.
- Recording the demo and how-to videos (made-up DPR, captions).
- A real testimonial, once classmates have used the site.
- Interest chips for majors other than CS and Psychology (the type-your-own box covers them meanwhile).

## Left to the builder

Component structure and file split; whether the floating card is one component; animation timing; exact breakpoints
beyond "works at 390px"; how the Building checklist paces steps the planner finishes in one call (each line must still
name a real step); prompt caching details; test layout.

## Calls I made (check these)

- The chat's suggested replies are GatorPath's own, and pace changes from them run without the AI (no AI question
  used, and they work with no key or at the limit).
- Undo only on the latest change, restoring everything from before it.
- Editing the record after a plan exists re-checks the plan as it stands and keeps the choices.

- The "With your plan" column on Your record replaces Progress; reached from a link on the Plan heading.
- Your goals' question 7 is shown up front only when the placement can still change the plan.
- The Plan's open-choice card says Select, and the chat's suggestion is "Choose them for me".
- Step numbers not reached yet are dark grey, not light green; the first screen's card text is 15/14px, not 13px.
- On Schedule, hover previews only work when the week is in view; "See on week" covers the rest.
- The landing page's facts strip and FAQ wording; "Rules for 108 majors" depends on the count at build time.
