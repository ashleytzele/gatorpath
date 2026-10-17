# AGENTS.md — GatorPath

Instructions for AI coding agents (Claude Code, Codex, Gemini CLI, …) and for humans
joining the project.

## What this is

An **MCP server** that gives AI assistants accurate tools for planning an SF State degree.
Full design: `docs/ARCHITECTURE.md`. Current work: `TASKS.md` (work phase by phase, in order).

## Golden rules (do not break these)

1. **Never invent academic rules.** Course data comes from the Bulletin PDF. Program
   requirements come only from `rules/**/*.yaml`. Never hard-code course codes, units, or
   prerequisites from memory. Courses get renumbered (e.g. CSC 210 → CSC 215).
2. **Every rule cites its source.** Each YAML group has `source: "p.<page>"`. Every `course`
   row has `source_page`. An `amendment` (a change after publication) cites its memo and date.
   One student's exception never goes into `rules/`.
3. **Flag, don't guess.** If prereq text can't be parsed, store it with `status: unparsed` and
   surface a warning. Never drop it and never approximate it silently.
4. **No LLM calls in the server.** Tools are deterministic. The AI client does the talking.
5. **No student data at rest.** Don't store, log, cache, or print student profiles or transcript
   text. Never commit a real transcript or any real student data. Test fixtures are synthetic.
6. **`check_plan` is the source of truth.** Anything that produces a plan must pass it in tests.

## Commands

```bash
brew install uv poppler            # one-time
uv sync                            # install deps
uv run pytest                      # tests
uv run python -m gatorpath.ingest.bulletin data/raw/bulletin-2026-27.pdf   # build catalog.db
uv run python -m gatorpath.db evals/profiles/*.yaml rules/programs/2026-27/*.yaml rules/roadmaps/2026-27/*.yaml > evals/catalog-2026-27.json   # refresh eval catalog rows
uv run python -m gatorpath.ingest.offerings --subjects CSC,MATH,PHYS        # offering history
uv run gatorpath                   # start MCP server (stdio)
uv run python evals/run_evals.py   # eval report
```

(These commands get added as each phase lands. If one doesn't exist yet, check `TASKS.md`.)

### Claude Desktop config

```json
{
  "mcpServers": {
    "gatorpath": {
      "command": "uv",
      "args": ["--directory", "/ABSOLUTE/PATH/TO/gatorpath", "run", "gatorpath"]
    }
  }
}
```

## Layout

| Path | What lives there |
|---|---|
| `src/gatorpath/server.py` | MCP tool/prompt definitions only. Keep it thin and call the engine |
| `src/gatorpath/engine/` | `prereq.py`, `rules.py`, `planner.py`: all logic, pure functions |
| `src/gatorpath/ingest/` | Offline builders: Bulletin PDF and class search → `data/catalog.db` |
| `src/gatorpath/transcript.py` | Local transcript PDF → course list (PII dropped) |
| `rules/programs/<year>/` | Hand-written requirement YAML (reviewed) |
| `rules/university/<year>.yaml` | GE, SF State Studies, American Institutions, GWAR, unit totals |
| `rules/roadmaps/<year>/` | Official roadmap variants as YAML |
| `evals/` | Synthetic profiles + eval runner |
| `data/` | **git-ignored**: raw PDFs, `catalog.db`, scrape cache |

## Conventions

- Python 3.12+, type hints, stdlib first. Ask before adding a dependency.
- Engine functions take plain data (dicts/dataclasses) and return plain data. No DB or
  network inside `engine/`.
- Tool responses always include `catalog_year`, plus `warnings: []` where rules apply.
- Course codes are normalized as `SUBJ NNN[SUFFIX]`, e.g. `CSC 300GW`, `MATH 226`.
- Terms are written as `YYYY-fall` / `YYYY-spring` / `YYYY-summer`.
- Tests: `pytest`, one test file per module. Prefer real Bulletin strings in parser tests.
- Shortcuts with a known ceiling get a `# ponytail:` comment that names the upgrade path.

## Adding or changing a program's rules

1. Copy the Bulletin text for each requirement group and note the page.
2. Write it in `rules/programs/<year>/<program>.yaml` using only the vocabulary in
   ARCHITECTURE §6.2. If you need a new rule type, update ARCHITECTURE first.
3. Add or extend synthetic profiles in `evals/profiles/` that exercise the new groups.
4. A second person checks the YAML against the PDF, then sets `verified: true` and `verified_by`.

## Scraping etiquette (class search)

Cache everything. Space requests at least 2 seconds apart. Scrape once per term, not per user
question. Identify the client honestly in the User-Agent. Stop if SFSU asks.
