# GatorPath

An MCP server that helps SF State students plan their degree with any AI assistant.
It answers "what's left?", "what's my 4-year path?", and "which classes for cybersecurity, and
in what order?" Every answer is checked against the official Bulletin.

**The AI suggests, the code verifies.**

> Status: phase 4 (planner) done; offering history (phase 5) next. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
> and [`TASKS.md`](TASKS.md).

## Use

Add the server to your MCP client (Claude Desktop config in [`AGENTS.md`](AGENTS.md)), then start with the
**Plan my degree** prompt. In a client without MCP prompts, say "use the gatorpath tools": a client that isn't
pointed at them may answer from web search instead, and nothing checks that plan.

## Why

SFSU's Degree Planner and DPR show what's required, but not which direction to take or why.
GatorPath adds career-direction planning, prerequisite-aware sequencing, and course offering
patterns, all of it verifiable and with no student data stored.

## Scope

- v1: SF State, BS Computer Science (2026-27 Bulletin), then Mathematics
- Later: transfer credit, week-level schedules, web UI

*Not affiliated with San Francisco State University. Always confirm with your advisor and your
official Degree Progress Report.*
