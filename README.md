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

39 questions (`evals/questions.yaml`) on synthetic students, run through Claude Code and Codex CLI with only the
gatorpath server attached (run 2026-10-18, full report in [`evals/REPORT.md`](evals/REPORT.md)):

| Metric | Claude Code | Codex CLI |
|---|---|---|
| Questions fully passed | 38/39 | 37/39 |
| Plans passing check_plan | 13/13 | 13/13 |
| Electives fit the goal | 11/12 | 10/12 |
| Hallucinated course codes | 0 | 0 |
| Used only the gatorpath tools | 39/39 | 39/39 |

All three misses are goal fit: electives that matched fewer of the goal's keywords.

## Limitations

- One program and one year: BS Computer Science, 2026-27 Bulletin. A DPR on an older catalog is planned with
  2026-27 rules plus a warning, and the DPR wins where they disagree.
- The rules are `verified: false`: eight rounds of independent AI review against the PDF brought the error rate
  from 19.6% to 10.6%, each finding fixed, but no second person has signed them off yet.
- Offering history covers CSC, MATH and PHYS only (2023-spring to 2026-fall); other subjects show `offered: unknown`.
- The transcript importer hasn't seen a real CR / W / I / repeat row yet, and the DPR's transfer-row Notes codes have
  no legend. Both get flagged rather than guessed.
- Tested on macOS only.
- Course codes, grades and units go to your AI provider as tool results; your name and ID don't. GatorPath stores
  nothing unless you ask the assistant to `save_profile`.

## Scope

- v1: SF State, BS Computer Science (2026-27 Bulletin), then Mathematics
- Later: transfer credit, week-level schedules, web UI

*Not affiliated with San Francisco State University. Always confirm with your advisor and your
official Degree Progress Report.*
