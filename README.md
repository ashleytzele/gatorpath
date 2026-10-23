# GatorPath

An MCP server that helps SF State students plan their degree with any AI assistant.
It answers "what's left?", "what's my 4-year path?", and "which classes for cybersecurity, and
in what order?" Every answer is checked against the official Bulletin.

**The AI suggests, the code verifies.**

> Status: phase 7 (evals, first users). Design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Work:
> [`TASKS.md`](TASKS.md).

## Why

SFSU's Degree Planner and DPR show what's required, but not which direction to take or why. Ask a chatbot
instead and it answers from memory: renumbered courses (CSC 210 is now CSC 215), prerequisites that don't exist,
a graduation term nobody checked. GatorPath gives the assistant tools that read the 2026-27 Bulletin, the major's
roadmaps and SFSU class-search history, and a `check_plan` that every plan has to pass. Each rule cites
its source: a Bulletin page, or the SF State office page it came from.

## Setup (macOS)

You need `gatorpath.zip`, which includes the course catalog (ask the maintainer for it). Then:

```bash
brew install uv poppler
unzip gatorpath.zip -d ~ && uv --directory ~/gatorpath sync
claude mcp add --scope user gatorpath -- uv --directory ~/gatorpath run gatorpath
```

The last line is for Claude Code. For Codex CLI it's `codex mcp add gatorpath -- uv --directory ~/gatorpath run gatorpath`.
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

In a client without MCP prompts, say "use the gatorpath tools" and mention SF State: a client that isn't pointed at
them may answer from web search, and nothing checks that plan.

## Evals

44 questions (`evals/questions.yaml`) on synthetic students across the three catalog years, Winter Session included,
run through Claude Code and Codex CLI with only the gatorpath server attached (run 2026-10-21, full report in
[`evals/REPORT.md`](evals/REPORT.md)):

| Metric | Claude Code | Codex CLI |
|---|---|---|
| Questions fully passed | 43/44 | 43/44 |
| Plans passing check_plan | 15/15 | 14/15 |
| Electives fit the goal | 13/14 | 13/14 |
| Hallucinated course codes | 0 | 0 |
| Used only the gatorpath tools | 44/44 | 44/44 |

Claude's miss is goal fit (it passed over web electives that need a 3.0 GPA and named them as backups). Codex's
miss: it stopped to ask a transfer student for their DPR though they had said what their transfer credit meets; the
prompt now plans from that, and a rerun of that question passes on both.

## Limitations

- Two programs: BS Computer Science for three catalog years, 2024-25 (the old GE Areas A-F), 2025-26 and 2026-27,
  and BS Applied Mathematics for 2026-27 only. Requirements follow the student's catalog year; courses and prereqs
  are the newest Bulletin's. A DPR on a catalog year without rules is planned with 2026-27 rules plus a warning,
  and the DPR wins where they disagree. `import_dpr` doesn't recognize an Applied Mathematics DPR yet (no sample
  to read its program line from); type the courses or use the transcript instead.
- 95 other bachelor's programs (2026-27 only; `list_programs` marks them `drafted: true`) are AI-drafted from the
  Bulletin's text, then checked by program: every course code, page and word-for-word quote, the unit totals, and a
  test plan that passes check_plan. A person hasn't checked them against the PDF yet. Rules the format can't express
  (a CR/NC unit cap, a course taken four times, a GPA floor) show as `unparsed` with the Bulletin's words: GatorPath
  doesn't check them, and a degree with one is never marked complete. 13 of the Bulletin's 110 aren't served yet
  (`rules/drafts/`, see TASKS.md).
- BS Applied Mathematics: the three application electives are "chosen with the consent of the applied mathematics
  advisor" (p.2129), so GatorPath can't list them; it counts only the ones you say were approved.
- Only the 2025-26 BS CS rules are signed off by a person (`verified: true`). The others are
  `verified: false`: for BS CS 2026-27, eight rounds of independent AI review against the PDF brought the error rate
  from 19.6% to 10.6%, each finding fixed. BS Applied Mathematics hasn't had a review yet.
- Offering history covers CSC, MATH and PHYS only (2023-spring to 2026-fall); other subjects show `offered: unknown`.
- The transcript importer hasn't seen a real CR / W / I / repeat row yet, and the DPR's transfer-row Notes codes have
  no legend. Both get flagged rather than guessed.
- Tested on macOS only.
- Course codes, grades and units go to your AI provider as tool results; your name and ID don't. GatorPath stores
  nothing unless you ask the assistant to `save_profile`.

## Scope

- v1: SF State, BS Computer Science (2026-27 Bulletin), then BS Applied Mathematics (2026-27, rules unverified), then
  the other bachelor's programs (2026-27, AI-drafted, unverified)
- Later: transfer credit, week-level schedules, web UI

*Not affiliated with San Francisco State University. Always confirm with your advisor and your
official Degree Progress Report.*
