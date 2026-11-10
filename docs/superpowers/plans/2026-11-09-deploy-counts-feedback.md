# Deploy, Usage Counts and Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put GatorPath online on Fly.io, count how many people use it without any sign-in, and let students send feedback.

**Architecture:** A new `stats.py` keeps daily totals and feedback messages in a small SQLite file on the host's disk. `api.py` gets four small routes (`/api/visit`, `/api/feedback`, `/api/stats`) and counts events inside the routes that already exist. A Dockerfile and `fly.toml` run the same `gatorpath-web` command on one Fly machine. No student is ever identified: the tables hold counts, a one-day hash and message text.

**Tech Stack:** Python 3.12 stdlib (`sqlite3`, `hashlib`, `hmac`, `secrets`), FastAPI (already a dependency), React/TypeScript site, Docker, Fly.io. No new Python or npm dependency.

**Spec:** this plan's "Decisions" section. The sign-in design (`docs/superpowers/specs/2026-11-09-accounts-design.md`) is deferred: build it only if students ask to keep their plan across devices.

## Decisions (owner's, 2026-11-09, unless marked my call)

- No sign-in or accounts for now. Usage is counted from events, so the numbers include everyone who plans, not only people who sign in.
- Host: Fly.io, one machine with a 1 GB volume. Vercel is not used: its functions have no persistent disk and no `pdftotext`, which the DPR import needs.
- Counts are daily totals per event. Events: `visit`, `visitor`, `dpr_import`, `plan_built`, `ai_question`, `feedback`. `plan_built` also records the major's id, `visit` also records the `?ref=` source. **(my call)**
- `visit` is one per browser tab (a flag in the tab's session storage). `visitor` is one per day per network address plus browser, kept as a one-way hash that is deleted the next day. Neither is "people": campus students share addresses, and one person has several devices, so the report calls them visits and visitors. **(my call)**
- Feedback is a text message of at most 2000 characters. No email, name or other details are collected, and the form tells students not to type their name or ID.
- The owner reads the numbers with `curl` and a secret token, or the command `python -m gatorpath.stats`. No dashboard page. **(my call)**
- A domain and Resend are not needed now (no emails are sent). The free `<app>.fly.dev` address has HTTPS. A domain can be added later in Task 6.

## Global Constraints

- Python stdlib first; ask before adding any dependency.
- `server.py` and `engine/` never import `stats` (golden rule 4/5 for the MCP server). A test checks it.
- `api.py` stays thin; counting is one call per event.
- A failure to write a count must never fail the student's request.
- Golden rule 5 is rewritten, not dropped: "The website keeps anonymous daily totals and feedback messages students choose to send; never a profile, DPR, grades or plan."
- No student data in URLs, and the access log stays off.
- Tests are synthetic; `pytest` one file per module (`tests/test_stats.py`); route tests go in `tests/test_api.py`.
- Commit after each task.

## Review Focus

1. The stats file is missing, read-only or the disk is full: the student's plan, import and chat still work (Task 1 test, Task 2 test).
2. A script posts junk `ref`, `program` or huge feedback: rows stay bounded, `ref` is `[a-z0-9_-]{1,20}`, `program` is a known id or `other`, feedback is cut at 2000 characters and refused after 5000 stored messages (Tasks 1, 2).
3. `/api/stats` with no token configured is not open (404), a wrong token is 401, and the token is never read from the URL (Task 2).
4. Behind Fly's proxy every student would look like one address, which would break the AI hourly limit and the visitor count: `address()` reads Fly's `Fly-Client-IP` header only when `GATORPATH_BEHIND_PROXY=1`, and never `X-Forwarded-For`, which a visitor can set (Task 5, checked live in Task 6).
5. Feedback text may contain a name or ID: the report leaves it out unless `feedback=1` is asked for, and the form warns (Tasks 1, 3).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/gatorpath/stats.py` (new) | The counters, the one-day visitor hash, feedback, the report and its command line. Imported only by `api.py`. |
| `src/gatorpath/api.py` | Routes, event counting, `server_settings()` for the deploy. |
| `tests/test_stats.py` (new) | `stats.py` alone, on a temporary file. |
| `tests/test_api.py` | The new routes and the sentences the site now says. |
| `web/src/api.ts`, `web/src/App.tsx`, `web/src/Feedback.tsx` (new), `web/src/ui.tsx`, `web/src/Landing.tsx`, `web/src/index.css` | The visit ping and the feedback dialog. |
| `Dockerfile`, `.dockerignore`, `fly.toml` (new) | The deploy. |
| `docs/ARCHITECTURE.md`, `AGENTS.md`, `TASKS.md` | The rule change (D37) and the commands. |

---

### Task 1: The counters (`stats.py`)

**Files:**
- Create: `src/gatorpath/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Produces:
  - `EVENTS: frozenset[str]` = the six events above.
  - `db_path() -> Path`: `GATORPATH_STATS_DB` if set, else `<repo>/data/stats.db`. Read on every call so tests can change it.
  - `count(event: str, program: str = "", ref: str = "") -> None`: adds 1 to today's row. Raises `ValueError` for an event not in `EVENTS`. `ref` outside `[a-z0-9_-]{1,20}` after lowercasing becomes `""`. Never raises for a database failure (`sqlite3.Error`, `OSError`).
  - `seen(who: str, agent: str) -> None`: counts `visitor` once per day per `(who, agent)`.
  - `add_feedback(message: str) -> bool`: stores the first 2000 characters; returns `False` (and stores nothing) for an empty message, or once 5000 messages are stored.
  - `report(days: int = 30, feedback: bool = False) -> dict`: `{"days": [{"day", "visit", "visitor", "dpr_import", "plan_built", "ai_question", "feedback"}...] newest first, "totals": {event: n}, "majors": {program: n} (plan_built, top 20), "refs": {ref: n} (visit), "feedback": [{"day","message"}...] only when asked}`.
  - `main() -> None`: prints `report` as readable lines; `--days N`, `--feedback`.

- [ ] **Step 1: Write the failing tests** in `tests/test_stats.py`, each with `monkeypatch.setenv("GATORPATH_STATS_DB", str(tmp_path / "s.db"))`:
  - `test_counts_add_up_per_day_event_and_program`: three `count("plan_built", "cs-bs")` and one `count("plan_built", "bio-bs")`; `report()["totals"]["plan_built"] == 4` and `majors == {"cs-bs": 3, "bio-bs": 1}`.
  - `test_unknown_event_is_refused`: `pytest.raises(ValueError)` for `count("login")`.
  - `test_ref_is_cleaned`: `count("visit", ref="Flyer")` → `refs == {"flyer": 1}`; `count("visit", ref="<script>x")` and a 21-character ref both land under `""` (which `report` leaves out of `refs`).
  - `test_a_visitor_counts_once_a_day`: `seen("1.2.3.4", "Safari")` twice → 1; `seen("1.2.3.4", "Chrome")` → 2; `seen("5.6.7.8", "Safari")` → 3.
  - `test_yesterdays_hashes_are_deleted`: after `seen(...)`, move the stored `day` of the `seen` table back one day with SQL, call `seen("9.9.9.9", "x")`; `select count(*) from seen` is 1.
  - `test_feedback_is_cut_refused_empty_and_capped`: 2500-character message stored as 2000; `add_feedback("  ")` is `False`; with 5000 rows inserted by SQL, `add_feedback("hi")` is `False`.
  - `test_report_hides_feedback_text_unless_asked`: after `add_feedback("hello")`, `"feedback" not in report()` at the top level (the per-day `feedback` count is separate and always there); `report(feedback=True)["feedback"][0]["message"] == "hello"`.
  - `test_a_broken_stats_file_never_raises`: `GATORPATH_STATS_DB` pointing into a missing directory: `count("visit")`, `seen("a", "b")` and `add_feedback("x")` return without raising.
  - `test_the_tables_hold_no_student_data`: the column names of every table are exactly `{counts: day,event,program,ref,n; seen: day,h; feedback: day,message}`.
  - `test_server_and_engine_never_import_stats`: no file under `src/gatorpath/engine/` and not `server.py` contains `stats`.
- [ ] **Step 2: Run** `uv run pytest tests/test_stats.py -q`. Expected: all FAIL (no module).
- [ ] **Step 3: Implement** `stats.py` with the signatures above. One `sqlite3.connect(db_path())` per call (creating the directory's file and the three tables `IF NOT EXISTS`), `INSERT ... ON CONFLICT DO UPDATE SET n = n + 1`. The visitor hash is `sha256(f"{salt}{who}|{agent}")` where `salt` is `secrets.token_hex(16)` made once per process per day (a module-level `(day, salt)` pair). Delete `seen` rows with `day < today` inside `seen()`. `# ponytail: the salt lives in memory, so a restart counts a returning visitor once more that day; store it if that matters.`
- [ ] **Step 4: Run** `uv run pytest tests/test_stats.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git add src/gatorpath/stats.py tests/test_stats.py && git commit -m "Stats: anonymous daily counts, a one-day visitor hash and feedback"`.

### Task 2: Routes and event counting

**Files:**
- Modify: `src/gatorpath/api.py` (imports; `admit` ~62-82; `import_dpr` ~110; `plan` ~138; new routes after `ai_status` ~201; the module docstring line 1-4)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `stats.count`, `stats.seen`, `stats.add_feedback`, `stats.report` (Task 1); `server.list_programs()["programs"][i]["id"]`.
- Produces:
  - `POST /api/visit` body `{"ref": str | null}` → `{"ok": true}`; calls `stats.count("visit", ref=ref or "")` and `stats.seen(address(request), request.headers.get("user-agent", ""))`.
  - `POST /api/feedback` body `{"message": str}` → `{"ok": true}`, `400` for empty text, `429` after 5 per address per hour (the same in-memory deque pattern as `used.recent`, in its own dict), counts `feedback`.
  - `GET /api/stats?days=30&feedback=false` with header `Authorization: Bearer <token>`; `404` when `GATORPATH_STATS_TOKEN` is unset, `401` for a wrong or missing token (`hmac.compare_digest`); returns `stats.report(days, feedback)`.
  - Counting: `dpr_import` after a successful `import_dpr`; `plan_built` in `plan()` with `program` = the profile's program if it is a known id, else `"other"`; `ai_question` at the end of `admit()` (only when it admits).

- [ ] **Step 1: Write the failing tests** (use the module's `client`; `monkeypatch.setenv("GATORPATH_STATS_DB", ...)`):
  - `test_visits_and_visitors_are_counted_and_ref_is_kept`: post `/api/visit` `{"ref": "flyer"}` twice with the same `User-Agent`; `stats.report()` shows `visit` 2, `visitor` 1, `refs == {"flyer": 2}`.
  - `test_planning_counts_the_major_and_the_import`: `post("/api/plan", profile=STUDENT)` → `majors` has `STUDENT["program"]: 1`; an unknown program (`{"program": "nope"}`; accept the route's own error response) never adds a key other than `"other"`; a monkeypatched `dpr.read_pdf_bytes` import adds `dpr_import` 1.
  - `test_an_admitted_ai_question_is_counted_and_a_refused_one_is_not`: call `api.admit("x")` `PER_HOUR` times then once more (expect `HTTPException` 429); `ai_question == PER_HOUR`. Reset `api.used` first.
  - `test_feedback_is_stored_limited_and_validated`: `{"message": ""}` → 400; two valid posts → 200; the sixth from one address in an hour → 429; stored text readable through `stats.report(feedback=True)`.
  - `test_stats_needs_the_token`: no `GATORPATH_STATS_TOKEN` → 404; set → missing header 401, wrong 401, right 200 with a `"days"` key; `?feedback=true` adds the `"feedback"` list; `client.get("/api/stats?token=<right>")` is 401.
  - `test_a_broken_stats_file_does_not_break_planning`: set `GATORPATH_STATS_DB` to `/nonexistent/x.db`; `/api/plan` with `STUDENT` still returns 200.
- [ ] **Step 2: Run** `uv run pytest tests/test_api.py -q -k "visits or planning_counts or admitted or feedback or stats"`. Expected: FAIL.
- [ ] **Step 3: Implement** the routes and counting. Update the module docstring: "Nothing about a student is stored or logged: an upload stays in memory, no student data goes in a URL. `stats` keeps anonymous daily totals and feedback messages." `ref` is passed through `stats.count`, which cleans it.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all PASS (the earlier two landing/stylesheet tests included).
- [ ] **Step 5: Commit** `git add src/gatorpath/api.py tests/test_api.py && git commit -m "Web API: count visits, imports, plans and AI questions; feedback; a token-guarded /api/stats"`.

### Task 3: The page: visit ping and the feedback dialog

**Files:**
- Modify: `web/src/api.ts` (add after `getPrograms`), `web/src/App.tsx` (App component), `web/src/ui.tsx` (`Footer`), `web/src/Landing.tsx` (footer), `web/src/index.css`
- Create: `web/src/Feedback.tsx`
- Test: `tests/test_api.py` (source-text checks, as the landing tests do)

**Interfaces:**
- Produces:
  - `api.ts`: `visit(ref: string | null): Promise<void>` posts `/api/visit` and never throws; `sendFeedback(message: string): Promise<void>` posts `/api/feedback`, throws the server's message on failure (use the file's existing error helper).
  - `Feedback.tsx`: `export function FeedbackLink()` renders a button "Send feedback" that opens a native `<dialog>` with a textarea (`maxLength` 2000), the line "Please don't type your name or ID. We keep only your message: no email, no details about you.", buttons "Send" and "Cancel", then "Thanks, we read every message." On a 429 or any error it shows the message and keeps the text.
  - `App.tsx`: once per tab (flag `gatorpath-visited` in session storage, wrapped in try/catch, skipped under `DEMO`) calls `visit(new URLSearchParams(location.search).get("ref"))`.

- [ ] **Step 1: Write the failing test** `test_the_site_counts_a_visit_and_offers_feedback` in `tests/test_api.py`: `APP` contains `"/api/visit"`, `"/api/feedback"`, `"Send feedback"`, `"Please don't type your name or ID"` and `"gatorpath-visited"`.
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Implement** the four pieces above. `FeedbackLink` goes in the app `Footer` after `ClearSaved` and in the landing footer's nav. Style the dialog in `index.css` with existing tokens only (the stylesheet test rejects raw colors).
- [ ] **Step 4: Verify** `uv run pytest tests/test_api.py -q` passes, `cd web && npx tsc --noEmit -p . && npm run build`, then in the browser (Claude in Chrome) open `http://127.0.0.1:8000/?ref=test`, check `GATORPATH_STATS_DB=/tmp/s.db uv run python -m gatorpath.stats` shows `visit 1` and `refs test 1` after a reload (still 1: the flag), send a feedback message and see it under `--feedback`.
- [ ] **Step 5: Commit** `git add web/src tests/test_api.py && git commit -m "Web: a visit ping once per tab and a Send feedback dialog"`.

### Task 4: Say it honestly

**Files:**
- Modify: `docs/ARCHITECTURE.md` (§7.6 "What keeps golden rule 5", §9 first bullet, decisions log: add D37), `AGENTS.md` (golden rule 5, Commands: the stats and deploy commands), `TASKS.md`, `web/src/Landing.tsx` (FAQ "Is my data safe?"), `web/src/ui.tsx` (`PRIVACY`)
- Test: `tests/test_api.py`

**Interfaces:** none produced. The new sentence everywhere: "GatorPath counts visits, plans built and questions asked as anonymous daily totals, and keeps feedback you choose to send. It never keeps your record, grades or plan."

- [ ] **Step 1: Write the failing test** `test_the_site_says_what_it_counts`: `APP` contains `"anonymous daily totals"` and `"feedback you choose to send"`; `docs/ARCHITECTURE.md` contains `"D37"`; `AGENTS.md` contains `"anonymous daily totals"`.
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Edit** the files. D37 row: decision (counts and feedback kept, no accounts for now, sign-in design deferred), why (the owner needs usage numbers; counts include everyone), date 2026-11-09. Keep §7.6's claim "no database" accurate: "no student database; a stats file of totals".
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git add -A docs AGENTS.md TASKS.md web/src tests && git commit -m "Docs and site copy: anonymous counts and feedback (D37)"`.

### Task 5: Deploy files

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `fly.toml`
- Modify: `src/gatorpath/api.py` (`main`, new `server_settings`)
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `server_settings(env: Mapping[str, str] = os.environ) -> dict` returning uvicorn keyword arguments: default `{"host": "127.0.0.1", "port": 8000, "access_log": False}`; `GATORPATH_HOST` sets `host`; `PORT` sets `port` (int). `address(request)` returns the `Fly-Client-IP` header when `GATORPATH_BEHIND_PROXY=1` (never `X-Forwarded-For`), else the connection's address. (Changed after the final review: uvicorn trusts the first `X-Forwarded-For` entry, which a visitor can set.) `main()` calls `uvicorn.run(app, **server_settings())`.

- [ ] **Step 1: Write the failing test** `test_server_settings`: `{}` gives the defaults; `{"GATORPATH_HOST": "0.0.0.0", "PORT": "8080", "GATORPATH_BEHIND_PROXY": "1"}` gives host `0.0.0.0`, port `8080`, `proxy_headers` true and `forwarded_allow_ips` `"*"`; `{"PORT": "8080"}` alone has no `proxy_headers` key.
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Implement** `server_settings` and use it in `main`. Then write the three deploy files:
  - `Dockerfile`: stage 1 `node:22-slim`, `WORKDIR /web`, copy `web/package*.json`, `npm ci`, copy `web/`, `npm run build`. Stage 2 `python:3.12-slim`: `apt-get install -y --no-install-recommends poppler-utils`, install `uv` (`pip install uv`), copy `pyproject.toml uv.lock README.md LICENSE src rules data/catalog.db` into `/app`, `uv sync --frozen --no-dev` (an editable install, so `REPO` resolves to `/app`), copy stage 1's `dist` to `/app/web/dist`, `CMD ["uv", "run", "--no-sync", "gatorpath-web"]`. (If `uv sync` needs `README.md`/`LICENSE`, they are copied above; the build tells you.)
  - `.dockerignore`: `.git`, `.venv`, `web/node_modules`, `web/dist`, `data/*` then `!data/catalog.db`, `*.pdf`, `evals`, `docs`, `tests`, `dist`, `.superpowers`, `.env`.
  - `fly.toml`: `app = "gatorpath"` (the owner picks another if taken), `primary_region = "sjc"`, `[env]` `GATORPATH_HOST = "0.0.0.0"`, `PORT = "8080"`, `GATORPATH_BEHIND_PROXY = "1"`, `GATORPATH_STATS_DB = "/data/stats.db"`; `[[mounts]]` `source = "gatorpath_data"`, `destination = "/data"`; `[http_service]` `internal_port = 8080`, `force_https = true`, `auto_stop_machines = "off"`, `auto_start_machines = true`, `min_machines_running = 1`; `[[http_service.checks]]` `GET /api/ai-status` every 30 s; `[[vm]]` `memory = "1gb"`, `cpu_kind = "shared"`, `cpus = 1`.
- [ ] **Step 4: Verify** `uv run pytest -q` passes. With Docker running: `docker build -t gatorpath-test .` then `docker run --rm -p 8080:8080 -e GATORPATH_HOST=0.0.0.0 -e PORT=8080 gatorpath-test` and `curl -s localhost:8080/api/programs | head -c 200` returns programs JSON and `curl -s -o /dev/null -w "%{http_code}" localhost:8080/` is `200`. (Without Docker, Task 6's remote build is the check.)
- [ ] **Step 5: Commit** `git add Dockerfile .dockerignore fly.toml src/gatorpath/api.py tests/test_api.py && git commit -m "Deploy: Dockerfile, fly.toml and server settings from the environment"`.

### Task 6: First deploy (the owner runs the account steps)

**Files:** none (a checklist). The owner types the secrets; Claude never sees them (`! <command>` in the prompt runs them in the session).

- [ ] **Step 1:** `brew install flyctl`, then `fly auth login` (opens the browser).
- [ ] **Step 2:** `fly launch --no-deploy --copy-config --name <app>` (answer no to a database and to Redis). Then `fly volumes create gatorpath_data --size 1 --region sjc`. Expected: the volume listed by `fly volumes list`.
- [ ] **Step 3:** `fly secrets set ANTHROPIC_API_KEY=<key> GATORPATH_STATS_TOKEN=$(openssl rand -hex 24)`; keep the token somewhere private.
- [ ] **Step 4:** `fly deploy`, then `fly scale count 1`. Expected: the deploy ends with "Visit your newly deployed app at https://<app>.fly.dev".
- [ ] **Step 5: Check live.** Open `https://<app>.fly.dev`: the landing page loads and the demo video plays; build a new-student plan end to end; `curl -s https://<app>.fly.dev/api/ai-status`; `curl -s -H "Authorization: Bearer $TOKEN" https://<app>.fly.dev/api/stats` shows `visit`, `plan_built` and the major.
- [ ] **Step 6: Check the proxy.** Note today's `visitor` total from `/api/stats`, then open the site once on a phone over cellular (a different network address). `visitor` goes up by 1. If it does not, Fly's proxy is being counted as the one address: check `GATORPATH_BEHIND_PROXY` with `fly ssh console -C "env"`. (This also protects the AI hourly limit, which is per address.) Then send two `POST /api/visit` requests from your laptop with `-H "Fly-Client-IP: 1.2.3.4"` and `-H "X-Forwarded-For: 5.6.7.8"` changed between them: if `visitor` rises by two, Fly is not overwriting `Fly-Client-IP` and the limits can be dodged; tell Claude before opening the site to students.
- [ ] **Step 7: Volume backup.** Run `fly volumes snapshots list gatorpath_data` and note the retention it shows; `stats.db` is the only data that cannot be rebuilt.
- [ ] **Step 8 (later, optional): A domain.** Buy one, `fly certs add <domain>`, add the DNS records the command prints, wait for `fly certs show <domain>` to say issued. Needed only for looks, and for email if sign-in is ever built.
- [ ] **Step 9: Commit** any `fly.toml` changes `fly launch` made (`git add fly.toml && git commit -m "Deploy: fly.toml as launched"`).

---

## Self-Review

- **Spec coverage:** Fly deploy (Tasks 5, 6), counts of visits, visitors, imports, plans with the major, AI questions, feedback (Tasks 1, 2), `?ref` source (Tasks 1, 3), feedback form (Task 3), a private way to read it (Tasks 1, 2), rule and copy changes (Task 4), no sign-in, accounts design deferred (Decisions).
- **Types:** `count(event, program, ref)`, `seen(who, agent)`, `add_feedback(message) -> bool`, `report(days, feedback)` and `server_settings(env)` are used with the same names in Tasks 2, 3 and 5.
- **Proportion:** each task has the test's name and assertions, the signature and the values the decisions fix; bodies are left to the implementer.
