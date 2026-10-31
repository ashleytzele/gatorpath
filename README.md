# GatorPath

An MCP server that helps SF State students plan their degree with any AI assistant.
It answers "what's left?", "what's my 4-year path?", and "which classes for cybersecurity, and
in what order?" Every answer is checked against the official Bulletin.

**The AI suggests, the code verifies.**

> Status: v0.1.0 (2026-10-30), phase 7 (evals, first users). Design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
> Work: [`TASKS.md`](TASKS.md). Changes: [releases](https://github.com/ashleytzele/gatorpath/releases).

## Why

SFSU's Degree Planner and DPR show what's required, but not which direction to take or why. Ask a chatbot
instead and it answers from memory: renumbered courses (CSC 210 is now CSC 215), prerequisites that don't exist,
a graduation term nobody checked. GatorPath gives the assistant tools that read the 2026-27 Bulletin, the major's
roadmaps and SFSU class-search history, and a `check_plan` that every plan has to pass. Each rule cites
its source: a Bulletin page, or the SF State office page it came from.

## Setup (macOS)

You need `gatorpath.zip`, which includes the course catalog: download it from the
[latest release](https://github.com/ashleytzele/gatorpath/releases/latest) (the repo is private: ask the maintainer
for access). Then:

```bash
brew install uv poppler
unzip gatorpath.zip -d ~ && uv --directory ~/gatorpath sync
claude mcp add --scope user gatorpath -- uv --directory ~/gatorpath run gatorpath
```

The last line is for Claude Code. It asks before each GatorPath tool runs; to approve them all once, type
`/permissions` in Claude Code and add the allow rule `mcp__gatorpath__*`. For Codex CLI it's
`codex mcp add gatorpath -- uv --directory ~/gatorpath run gatorpath`.
For Claude Desktop, open Settings → Developer → Edit Config, add this, and restart the app:

```json
{
  "mcpServers": {
    "gatorpath": {
      "command": "uv",
      "args": ["--directory", "/Users/YOU/gatorpath", "run", "gatorpath"]
    }
  }
}
```

If Desktop says it can't find `uv`, put the full path from `which uv` in `"command"`.

**From source** (no zip): clone the repo, put the Bulletin PDF at `data/raw/bulletin-2026-27.pdf`, and build the
catalog with the `ingest` commands in [`AGENTS.md`](AGENTS.md).

## Use

Start with the **Plan my degree** prompt (Claude Code: `/mcp__gatorpath__plan_my_degree`). It asks once for what it
needs. The fastest way in is your DPR: in Student Center, print the Degree Progress Report to a PDF and give the
assistant the file's path (don't attach it). GatorPath reads it on your machine and drops your name and ID.

In a client without MCP prompts (Codex CLI), just ask, and mention SF State, e.g. "I'm an SF State CS major, plan
the rest of my degree": the tools hand it the same steps. Without "SF State" a client may answer from web search,
and nothing checks that plan.

## Evals

47 questions (`evals/questions.yaml`) on synthetic students across the three catalog years, Winter Session included,
run through Claude Code and Codex CLI with only the gatorpath server attached (run 2026-10-29, full report in
[`evals/REPORT.md`](evals/REPORT.md)). Each client starts the way its students do: Claude Code from the Plan my degree
prompt, Codex CLI (no MCP prompts) from the student's words alone.

| Metric | Claude Code | Codex CLI |
|---|---|---|
| Questions fully passed | 45/47 | 45/47 |
| Plans passing check_plan | 15/15 | 14/15 |
| Electives fit the goal | 13/14 | 12/14 |
| Hallucinated course codes | 0 | 0 |
| Used only the gatorpath tools | 47/47 | 47/47 |
| Plan in the first reply (nothing asked back) | 15/15 | 14/15 |
| Median time to a plan | 147 s | 403 s |
| Median tool calls per plan | 10 | 22 |

Misses in that run: goal fit for the same game-development student on both clients (SF State's two game courses
rarely run and ranked past the first 25 electives, so neither plan had them); Codex presented a plan with open slots
for a student retaking CSC 215 without running check_plan; Claude left one student's math placement out of the
profile. Codex's plans took a median 22 tool calls, down from 68 on 2026-10-21 (TASKS.md, "Done 2026-10-29":
efficiency and token usage).

Fixed on 2026-10-30: the electives list names the options past its first 25, and GE suggestions are checked at each
requirement's own term in the plan, not the plan's first. A rerun of the 15 plan questions: both clients 15/15 passed,
plans 15/15, goal fit 14/14, a plan in the first reply 15/15. After that, GE suggestions come from courses that ran in
the last year, each with when it ran; on the four plan questions this touches, every plan passed check_plan with goal
fit, and none picked a course that hadn't run lately.

## Limitations

- Hand-written rules: BS Computer Science and BS Applied Mathematics for three catalog years, 2024-25 (the old GE
  Areas A-F), 2025-26 and 2026-27. Requirements follow the student's catalog year; courses and prereqs
  are the newest Bulletin's. A DPR on a catalog year without rules is planned with 2026-27 rules plus a warning,
  and the DPR wins where they disagree. `import_dpr` recognizes a Computer Science or Psychology DPR; for other
  majors (no sample to read the program line from yet), type the courses or use the transcript instead.
- 106 other bachelor's programs for 2026-27, plus BA Psychology for 2025-26 (`list_programs` marks them
  `drafted: true`), are AI-drafted from the
  Bulletin's text, then checked by program: every course code, page and word-for-word quote, the unit totals, and a
  test plan that passes check_plan. Each had a first-pass review against its Bulletin text (Claude, 2026-10-23;
  docs/review-2026-27-drafts.md); a person hasn't signed them off yet, so they stay `verified: false`. Rules the format can't express
  (a CR/NC unit cap, a course taken four times, a GPA floor) show as `unparsed` with the Bulletin's words: GatorPath
  doesn't check them, and a degree with one is never marked complete. 2 of the Bulletin's 110 aren't served: BA
  Philosophy and Religion (suspended, nothing printed) and BA Family and Community Sciences (no roadmap).
- BS Applied Mathematics: the three application electives are "chosen with the consent of the applied mathematics
  advisor" (p.2129), so GatorPath can't list them; it counts only the ones you say were approved.
- Only the 2025-26 BS CS rules are signed off by a person (`verified: true`). The others are
  `verified: false`: for BS CS 2026-27, eight rounds of independent AI review against the PDF brought the error rate
  from 19.6% to 10.6%, each finding fixed. BS Applied Mathematics hasn't had a review yet.
- Offering history (2023-spring to 2027-spring) covers CSC, MATH, PHYS, PSY and SXS; 89 other subjects have only the
  Spring 2027 schedule, so "not offered" there means one term, and GE suggestions favor courses on it (a fall-only
  course there reads as not run lately); the rest show `offered: unknown`.
- The transcript importer hasn't seen a real CR / W / I / repeat row yet, and the DPR's transfer-row Notes codes have
  no legend. Both get flagged rather than guessed.
- Tested on macOS only.
- Course codes, grades and units go to your AI provider as tool results; your name and ID don't. GatorPath stores
  nothing unless you ask the assistant to `save_profile`.

## Prior art

Earlier projects for SF State students: [GatorWay](https://github.com/dixisouls/gatorway) (MIT; transcript to
interest-based electives over MCP) and Plan-Ed (SF Hacks × GDG 2026, 2nd place; a four-year plan from Gemini and a
rules engine, as a web app). How GatorPath differs: [ARCHITECTURE §3](docs/ARCHITECTURE.md#3-prior-art--how-were-different).

## Scope

- v1: SF State, BS Computer Science (2026-27 Bulletin), then BS Applied Mathematics (2026-27, rules unverified), then
  the other bachelor's programs (2026-27, AI-drafted, unverified)
- Later: transfer credit, week-level schedules, web UI

*Not affiliated with San Francisco State University. Always confirm with your advisor and your
official Degree Progress Report.*

MIT License: see [`LICENSE`](LICENSE).
