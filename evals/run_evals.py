"""End-to-end evals (ARCHITECTURE §12, TASKS Phase 7): evals/questions.yaml through real AI clients (Claude Code and
Codex CLI), each with only the gatorpath MCP server, scored from the transcripts. Facts are computed from the tools at
scoring time, so nothing expected is written from memory.

  uv run python evals/run_evals.py                                  # both clients, every question
  uv run python evals/run_evals.py --clients codex --only plan-p03  # a subset
  uv run python evals/run_evals.py --rescore data/evals/<run>       # score saved transcripts again, no client calls

Transcripts go to data/evals/<run>/ (git-ignored; synthetic profiles only), the summary to evals/REPORT.md.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_server  # noqa: E402  (the scenario profiles live with their tests)

from gatorpath import db, server  # noqa: E402
from gatorpath.engine.planner import term_key  # noqa: E402
from gatorpath.engine.rules import first_time, matches  # noqa: E402

YEAR = server.YEAR
CATALOG = db.load_catalog(server.DB, YEAR)
PROGRAM, UNIVERSITY = server.load_rules(YEAR, "bs-cs")


def major(profile: dict | None) -> tuple[set[str], dict]:
    """The required courses and senior-electives group of the student's rules year (the newest with no profile)."""
    program = server.load_rules(server.rules_year(profile), "bs-cs")[0] if profile else PROGRAM
    return {c for g in program["groups"] for c in g.get("all_of", [])}, next(g for g in program["groups"] if g["id"] == "senior_electives")


REQUIRED, SENIOR = major(None)
SUBJECTS = sorted({c.rsplit(" ", 1)[0] for c in CATALOG}, key=len, reverse=True)
CODE = re.compile(r"\b(" + "|".join(map(re.escape, SUBJECTS)) + r") ?(\d{3}[A-Z]{0,3})\b(?!-?level|\+|s\b)")
MORE = re.compile(r"(?:\s*\([^()]{0,40}\))?\s*(?:,\s*(?:and |or )?|and |or |/|&\s*)(\d{3}[A-Z]{0,3})\b(?!\s*units?\b|-?level|\+)")  # "CSC 230, 256 and 340"
NOW = ("2026-fall", "Fall 2026")  # ponytail: the eval's "today"; move it when the profiles' terms are shifted again
LOAD_KEYS = ("max_units_per_term", "include_summer", "include_winter")
RECORD = ("program", "qr_pathway", "f1", "adt", "ge_certified", "prior_bachelors", "transfer_units", "approved")
PREFS = ("include_summer", "include_winter", "max_units_per_term", "graduate_by")  # checked on build_plan, where they matter
GRADE_WORDS = {"I": "I (incomplete)", "W": "W (withdrew)", "WU": "WU (unauthorized withdrawal)", "IC": "IC (incomplete charged)",
               "RD": "RD (report delayed)", "RP": "RP (report in progress)", "AU": "AU (audit)"}
WORK = Path(tempfile.gettempdir()) / "gatorpath-evals"  # client cwd + Codex home, outside the repo


# ---- profiles and question text ----

def load_profile(ref) -> dict | None:
    if ref is None or isinstance(ref, dict):
        return ref
    if ref.startswith("scenario: "):
        return json.loads(json.dumps(test_server.SCENARIOS[ref[len("scenario: "):]]))
    [path] = (ROOT / "evals/profiles").glob(f"{ref}-*.yaml")
    return yaml.safe_load(path.read_text())["profile"]


def shift(profile: dict) -> dict:
    """Move every term back whole years until the last completed one is before fall 2026 (in-progress courses are then
    this fall), keeping the gaps between terms."""
    terms = [r["term"] for r in profile.get("completed", []) if r.get("term")]
    if not terms:
        return profile
    last = max(terms, key=term_key)
    years = max(0, term_key(last)[0] - 2026 + (1 if last.endswith("fall") else 0))
    move = lambda t: f"{int(t[:4]) - years}{t[4:]}" if t else t
    out = profile | {"completed": [r | ({"term": move(r["term"])} if r.get("term") else {}) for r in profile["completed"]]}
    for key in ("start_term", "graduate_by"):
        if out.get(key):
            out[key] = move(out[key])
    return out


def term_words(term: str) -> str:
    return f"{term[5:].capitalize()} {term[:4]}"


def render(profile: dict | None, goal: str | None, plan: bool) -> str:
    """The student's own words for a profile: what a student would type, nothing a tool would compute."""
    if not profile:
        return ""
    rules = server.programs()[profile.get("program", "bs-cs")]
    major = rules["title"].replace("Bachelor of Science in ", "BS ")
    say = [f"I'm a {major} major at SF State on the {profile.get('catalog_year', YEAR)} catalog."]
    if profile.get("qr_pathway"):
        say.append(f"My math placement is QR {profile['qr_pathway']}.")
    if profile.get("prior_bachelors"):
        say.append("I already have a bachelor's degree from a regionally accredited university.")
    if profile.get("adt"):
        say.append("I have a verified AS-T (Associate Degree for Transfer) in Computer Science from a California "
                   "community college.")
    if profile.get("transfer_units"):
        say.append(f"I transferred in with {profile['transfer_units']:g} units.")
    elif profile.get("first_time") is False:
        say.append("I'm a transfer student.")
    if profile.get("ge_certified"):
        say.append("My lower-division GE is Cal-GETC certified.")
    if profile.get("ge_done"):
        say.append(f"My DPR shows these GE / American Institutions areas done by transfer or AP: {', '.join(map(str, profile['ge_done']))}.")
    rows = profile.get("completed", [])
    if moved := [r for r in rows if r.get("transfer")]:
        say.append("My DPR lists these transfer courses under the SF State requirements they meet: "
                   + ", ".join(f"{r['code']} ({r['grade']})" for r in moved) + ".")
    by_term: dict[str, list[str]] = {}
    for r in rows:
        if not r.get("transfer"):
            by_term.setdefault(r.get("term") or "", []).append(f"{r['code']} {GRADE_WORDS.get(r['grade'], r['grade'])}")
    for term in sorted(by_term, key=lambda t: term_key(t) if t else (0, 0)):
        say.append(f"{term_words(term) if term else 'Also completed'}: {', '.join(by_term[term])}.")
    if profile.get("in_progress"):
        say.append(f"This fall ({NOW[0][:4]}) I'm taking {', '.join(profile['in_progress'])}.")
    elif not (rows or profile.get("ge_done") or profile.get("transfer_units")):
        say.append("I haven't taken any college courses yet.")
    elif any(r.get("term") for r in rows) and not profile.get("start_term"):
        say.append(f"I'm not taking classes this fall ({NOW[0][:4]}).")
    if profile.get("start_term"):
        say.append(f"I start at SF State in {term_words(profile['start_term'])}.")
    titles = {g["id"]: g["title"] for g in rules["groups"]}
    for gid, codes in (profile.get("approved") or {}).items():
        say.append(f"My advisor approved {', '.join(codes)} for my {titles.get(gid, gid)}.")
    if profile.get("gpa"):
        say.append(f"My GPA is {profile['gpa']}.")
    if plan or profile.get("f1"):
        say.append("I'm on an F-1 student visa." if profile.get("f1") else "I'm not on a student visa.")
    if plan:
        units = profile.get("max_units_per_term")
        say.append((f"I can take up to {units:g} units a term" if units else "The normal load is fine")
                   + (", and summers too." if profile.get("include_summer") else ", no summers."))
        say.append(f"I'd like to graduate by {term_words(profile['graduate_by'])}." if profile.get("graduate_by")
                   else "No graduation deadline.")
        if goal:
            say.append(f"I want to go into {goal}.")
    return " ".join(say)


def first_message(q: dict, profile: dict | None) -> str:
    text = " ".join(x for x in (render(profile, q.get("goal"), bool(q.get("prompt"))), q["ask"]) if x)
    if q.get("prompt"):
        lead = server.plan_my_degree(goal=q.get("goal", ""), graduate_by=(profile or {}).get("graduate_by", ""))
        return f"{lead}\n\n---\n\nStudent: {text}"
    return text


# ---- clients ----

def run_claude(text: str, resume: str | None) -> dict:
    cfg = WORK / "claude-mcp.json"
    cmd = ["claude", "-p", text, "--mcp-config", str(cfg), "--strict-mcp-config", "--setting-sources", "project",
           "--tools", "", "--allowedTools", "mcp__gatorpath__*", "--output-format", "stream-json", "--verbose"]
    out = subprocess.run(cmd + (["--resume", resume] if resume else []), cwd=WORK / "cwd", capture_output=True,
                         text=True, stdin=subprocess.DEVNULL, timeout=1800)
    calls, answer, session, by_id, other = [], "", resume, {}, []
    for line in out.stdout.splitlines():
        e = json.loads(line)
        if e.get("type") == "assistant":
            for b in e["message"]["content"]:
                if b.get("type") == "tool_use":
                    if not b["name"].startswith("mcp__gatorpath__"):
                        other.append(b["name"])
                        continue
                    calls.append({"tool": b["name"].removeprefix("mcp__gatorpath__"), "args": b["input"]})
                    by_id[b["id"]] = calls[-1]
        elif e.get("type") == "user":
            for b in e["message"]["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in by_id:
                    c = b["content"]
                    by_id[b["tool_use_id"]]["result"] = "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c)
        elif e.get("type") == "result":
            answer, session = e.get("result") or "", e.get("session_id")
            if e.get("is_error"):
                out.returncode = out.returncode or 1  # e.g. "You've hit your session limit"
    return {"calls": calls, "answer": answer, "session": session, "other_tools": other,
            "error": None if out.returncode == 0 else (out.stderr[-500:] or answer[:500])}


def run_codex(text: str, resume: str | None) -> dict:
    env = os.environ | {"CODEX_HOME": str(WORK / "codex_home")}
    base = ["codex", "exec"] + (["resume"] if resume else []) + ["--json", "--skip-git-repo-check"]
    base += ["-c", 'sandbox_mode="read-only"'] if resume else ["-s", "read-only", "-C", str(WORK / "cwd")]
    out = subprocess.run(base + ([resume] if resume else []) + [text], cwd=WORK / "cwd", capture_output=True, text=True,
                         stdin=subprocess.DEVNULL, env=env, timeout=1800)
    calls, answer, session, other, failed = [], "", resume, [], None
    for line in out.stdout.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = e.get("item", {})
        if e.get("type") == "thread.started":
            session = e["thread_id"]
        elif e.get("type") in ("error", "turn.failed"):  # e.g. a usage limit; stderr only says it read stdin
            failed = e.get("message") or (e.get("error") or {}).get("message") or json.dumps(e)[:300]
        elif e.get("type") == "item.completed" and item.get("type") == "mcp_tool_call" and item.get("server") != "gatorpath":
            other.append(f"{item.get('server')}.{item.get('tool')}")
        elif e.get("type") == "item.completed" and item.get("type") == "mcp_tool_call":
            args = item.get("arguments")
            res = item.get("result") or {}
            calls.append({"tool": item["tool"], "args": json.loads(args) if isinstance(args, str) else args or {},
                          "result": "".join(x.get("text", "") for x in res.get("content", [])) or str(item.get("error"))})
        elif e.get("type") == "item.completed" and item.get("type") == "agent_message":
            answer = item["text"]
        elif e.get("type") == "item.completed" and item.get("type") not in ("reasoning", None):
            other.append(f"{item['type']}: {item.get('command') or item.get('query') or ''}"[:200])
    return {"calls": calls, "answer": answer, "session": session, "other_tools": other,
            "error": failed or (None if out.returncode == 0 else out.stderr[-500:])}


CLIENTS = {"claude": run_claude, "codex": run_codex}


def setup() -> None:
    """A clean client environment: no user plugins, hooks or memory; web search off; only the gatorpath server."""
    (WORK / "cwd").mkdir(parents=True, exist_ok=True)
    server_cfg = {"command": "uv", "args": ["--directory", str(ROOT), "run", "gatorpath"]}
    (WORK / "claude-mcp.json").write_text(json.dumps({"mcpServers": {"gatorpath": server_cfg}}))
    home = WORK / "codex_home"
    home.mkdir(exist_ok=True)
    if not (home / "auth.json").exists():
        (home / "auth.json").symlink_to(Path.home() / ".codex/auth.json")  # the user's own login, never copied
    user = {}
    try:  # the user's usual Codex model, so the eval matches what they'd run
        import tomllib
        user = tomllib.loads((Path.home() / ".codex/config.toml").read_text())
    except (OSError, ValueError):
        pass
    model = "".join(f'{k} = "{user[k]}"\n' for k in ("model", "model_reasoning_effort") if k in user)
    off = "".join(f"{f} = false\n" for f in ("apps", "browser_use", "browser_use_external", "in_app_browser", "shell_tool",
                                             "skill_search"))
    (home / "config.toml").write_text(f'{model}web_search = "disabled"\n[features]\n{off}[mcp_servers.gatorpath]\n'
                                      f'command = "uv"\nargs = {json.dumps(server_cfg["args"])}\ntool_timeout_sec = 300\n')


# ---- scoring ----

def course_leaves(e) -> list[str]:
    if not isinstance(e, dict):
        return []
    if "course" in e:
        return [e["course"]]
    return [c for x in e.get("all") or e.get("any") or [] for c in course_leaves(x)]


def area_names(area: str) -> list[str]:
    """How an answer may name a GE / SF State Studies area: its code, or the first words of its title."""
    names = [area]
    for g in UNIVERSITY["groups"]:
        fs = g.get("from") if isinstance(g.get("from"), list) else [g.get("from") or {}]
        if any(f.get("ge_area") == area for f in fs):
            title = re.sub(r"^(GE \S+ |SF State Studies: |American Institutions: )", "", g["title"])
            names.append(" ".join(title.split()[:2]))
    return names


def fact(kind: str, arg, profile: dict | None) -> list[list[str]]:
    """What the answer must state, from the tools: a list of alternatives lists (each needs one hit)."""
    if kind == "prereqs_of":
        return [[c] for c in dict.fromkeys(course_leaves(server.get_prereq_chain(arg)["requires"]))]
    if kind == "remaining":  # the required courses left; with none, the open major groups and the unit totals short
        audit = server.audit_progress(profile)
        major = [g for g in audit["groups"] if g["kind"] == "major" and g["status"] != "satisfied"]
        courses = [[c] for g in major for c in g.get("remaining", [])]
        if courses:
            return courses
        short = [v for v in audit["totals"].values() if isinstance(v, dict) and not v.get("ok") and "needed" in v]
        return ([[g["title"].split()[0].rstrip("s")] for g in major]  # "Electives" also read as "senior elective"
                + [[f"{v['needed']:g}", f"{v['needed'] - v['value']:g}"] for v in short])
    if kind == "unlocks_of":
        return [[c] for c in server.get_course(arg)["unlocks"] if c in REQUIRED]
    if kind == "seasons_of":
        o = CATALOG[arg].get("offered") or {}
        return [[s] for s in ("fall", "spring", "summer") if o.get(s, [0])[0]]
    if kind == "close_match_of":
        return [[server.get_course(arg)["close_matches"][0]]]
    if kind == "areas_of":
        return [area_names(a) for a in CATALOG[arg]["ge_areas"]]
    if kind == "carries_over_to":  # a change of major: the major courses that count in both programs
        return [[c] for c in server.compare_programs(profile, arg)["courses"]["count_in_both"]]
    raise ValueError(kind)


def cleaned(x: dict) -> dict:
    """The profile as the tools read it: codes normalized, GE areas translated, catalog_year as the rules year used."""
    x = x | {"program": x.get("program", "bs-cs")}
    year = server.rules_year(x)
    return server.prepare(x, server.load_rules(year, x["program"])[1], year)[0]


def profile_diff(expected: dict, got: dict, keys: tuple = RECORD) -> list[str]:
    expected, got = cleaned(expected), cleaned(got)
    norm = lambda rows: {(r["code"], "T" if r.get("transfer") else str(r.get("grade", "")).strip().upper()) for r in rows}
    diffs = []
    if keys != RECORD:
        return [f"{k}: {got.get(k)!r} vs {expected[k]!r}" for k in keys if k in expected and got.get(k) != expected[k]]
    if got["catalog_year"] != expected["catalog_year"]:  # left out or wrong: another year's requirements
        diffs.append(f"catalog_year: rules {got['catalog_year']} vs {expected['catalog_year']}")
    want, have = norm(expected.get("completed", [])), norm(got.get("completed", []))
    if want != have:
        diffs.append(f"completed: missing {sorted(want - have)}, extra {sorted(have - want)}")
    if set(expected.get("in_progress", [])) != set(got.get("in_progress", [])):
        diffs.append(f"in_progress: {sorted(got.get('in_progress', []))} vs {sorted(expected.get('in_progress', []))}")
    if {str(a).upper() for a in expected.get("ge_done", [])} != {str(a).upper() for a in got.get("ge_done", [])}:
        diffs.append(f"ge_done: {got.get('ge_done', [])} vs {expected.get('ge_done', [])}")
    for k in keys:
        if k in expected and got.get(k) != expected[k] and not (k == "transfer_units" and float(got.get(k) or 0) == expected[k]):
            diffs.append(f"{k}: {got.get(k)!r} vs {expected[k]!r}")
    if first_time(expected) != first_time(got):  # a missing first_time follows the transfer work (§6.2)
        diffs.append(f"first_time: {first_time(got)} vs {first_time(expected)}")
    return diffs


def codes_in(text: str) -> set[str]:
    out = set()
    for m in CODE.finditer(text):
        out.add(f"{m.group(1)} {m.group(2)}")
        pos = m.end()
        while n := MORE.match(text, pos):
            out.add(f"{m.group(1)} {n.group(1)}")
            pos = n.end()
    return out


def hallucinated(answer: str, allowed: str) -> list[str]:
    seen, ok = codes_in(answer), codes_in(allowed)
    return sorted(c for c in seen if c not in CATALOG and c not in ok)


def plan_codes(plan: dict) -> list[str]:
    return [c for s in plan.get("semesters", []) for c in s.get("courses", []) if isinstance(c, str)]


def score_turn(expect: dict, turn: dict, earlier: list[dict], profile: dict | None, goal: str | None,
               goals: dict, question: str) -> tuple[dict, dict]:
    calls = turn["calls"]
    every = [c for t in earlier for c in t["calls"]] + calls
    names = {c["tool"] for c in every}
    answer = turn["answer"].replace("\u2019", "'").replace("\u2018", "'")  # "isn’t" reads as "isn't"
    s, why = {}, {}
    s["answered"] = bool(answer.strip()) and not turn.get("error")
    wild = hallucinated(answer, question + " ".join(c.get("result", "") for c in every))
    s["no_hallucinated_codes"] = not wild
    if wild:
        why["hallucinated"] = wild
    s["no_save_profile"] = "save_profile" not in names
    s["only_gatorpath_tools"] = not turn.get("other_tools")
    if turn.get("other_tools"):
        why["other_tools"] = turn["other_tools"]
    if profile is not None:
        given = next((c["args"]["profile"] for c in every if isinstance(c.get("args"), dict) and "profile" in c["args"]), None)
        if given is not None:  # no tool got one: n/a here (expect.tools / plan_valid say when one was needed)
            diffs = profile_diff(profile, given)
            planned = next((c["args"]["profile"] for c in every if c["tool"] == "build_plan" and "profile" in c.get("args", {})), None)
            diffs += profile_diff(profile, planned, PREFS) if planned is not None else []
            s["profile_faithful"] = not diffs
            if diffs:
                why["profile"] = diffs
    if "tools" in expect:
        s["tools"] = set(expect["tools"]) <= names
        if not s["tools"]:
            why["tools_missing"] = sorted(set(expect["tools"]) - names)
    for kind, arg in (expect.get("mention") or {}).items():
        need = fact(kind, arg, profile)
        said = codes_in(answer)
        miss = [alts[0] for alts in need if not any(a in said or a.lower() in answer.lower() for a in alts)]
        s["mention"] = not miss
        if miss:
            why["not_mentioned"] = miss
    if "mention_any" in expect:
        s["mention_any"] = any(w.lower() in answer.lower() for w in expect["mention_any"])
    # The plan presented: the checked plan the answer lists best (the prompt has clients re-check variants, e.g. with
    # a course taken out to see whether it's optional), the later one on a tie
    # On a tie in courses (a variant with fewer free-elective units), the one the client's own check_plan passed: the
    # prompt lets it present only a passing plan. ponytail: courses only; compare per-term units if a tie still misleads
    checked = lambda cs: [c for c in cs if c["tool"] == "check_plan" and isinstance(c.get("args"), dict) and "plan" in c["args"]]
    checks = checked(calls) or checked(every)  # a follow-up presents a plan it checked itself, if it checked one
    said = codes_in(answer)
    passed = lambda c: '"valid": true' in (c.get("result") or "")

    def fit(i):
        codes = set(plan_codes(checks[i]["args"]["plan"]))
        return len(codes & said) - len(codes - said), passed(checks[i]), i

    last = checks[max(range(len(checks)), key=fit)]["args"] if checks else None
    if expect.get("plan_valid"):
        # Re-checked for the student in the question, with the client's plan settings: a plan made for a profile the
        # client got wrong doesn't count
        mine = (profile or {}) | {k: v for k, v in last["profile"].items() if k in PREFS + ("start_term",)} if last else None
        result = server.check_plan(mine if profile else last["profile"], last["plan"]) if last else None
        s["plan_valid"] = bool(result and result["valid"])
        if result and not result["valid"]:
            why["plan_errors"] = [e["message"] for e in result["errors"]][:5]
        if last and (sems := last["plan"].get("semesters")):
            why["graduates"] = sems[-1].get("term")
    for season in ("summer", "winter"):  # a pace run with that season (an earlier turn's counts), or a checked plan with such a term
        if expect.get(f"{season}_tried"):
            s[f"{season}_tried"] = any(c["tool"] == "build_plan" and c["args"].get("profile", {}).get(f"include_{season}")
                                       for c in every) \
                or bool(last) and any(str(x.get("term", "")).endswith(season) for x in last["plan"].get("semesters", []))
    if expect.get("goal_fit") and goal:
        plan = last["plan"] if last else {}
        required, senior = major(profile)
        filters = senior["from"] if isinstance(senior["from"], list) else [senior["from"]]
        picks = [c for c in plan_codes(plan) if c in CATALOG and c not in required
                 and any(matches(f, c, CATALOG[c]) for f in filters)]
        desc = db.descriptions(server.DB, YEAR, picks)
        hits = [c for c in picks if any(k in f"{CATALOG[c]['title']} {desc.get(c) or ''}".lower() for k in goals[goal])]
        open_slots = any(isinstance(x, dict) and x.get("slot") == "senior_electives"
                         for sem in plan.get("semesters", []) for x in sem.get("courses", []))
        s["goal_fit"] = (len(hits) >= min(2, len(picks))) if picks else (False if open_slots or not plan else None)
        why["electives"] = {"picked": picks, "on_goal": hits}
    if expect.get("pace_compared"):
        loads = {tuple(c["args"].get("profile", {}).get(k) for k in LOAD_KEYS) for c in every if c["tool"] == "build_plan"}
        s["pace_compared"] = len(loads) >= 2  # an earlier turn's runs count: the follow-up can answer from them
        why["loads"] = sorted(map(str, loads))
    return s, why


def score(q: dict, turns: list[dict], goals: dict) -> dict:
    profile = shift(load_profile(q.get("profile"))) if q.get("profile") else None
    text = first_message(q, profile)
    scores, why = score_turn(q.get("expect", {}), turns[0], [], profile, q.get("goal"), goals, text)
    if q.get("followup") and len(turns) > 1:
        f = q["followup"]
        s2, w2 = score_turn(f.get("expect", {}), turns[1], turns[:1], profile, f.get("goal", q.get("goal")), goals,
                            text + f["ask"])
        scores |= {f"followup.{k}": v for k, v in s2.items() if k not in ("profile_faithful",)}
        why |= {f"followup.{k}": v for k, v in w2.items()}
    elif q.get("followup"):
        scores["followup.answered"] = False
    return {"scores": scores, "why": why, "passed": all(v is not False for v in scores.values())}


# ---- run + report ----

def run_one(client: str, q: dict, out_dir: Path) -> dict:
    profile = shift(load_profile(q.get("profile"))) if q.get("profile") else None
    start, turns = time.time(), []
    asked = first_message(q, profile)
    try:
        turns.append(CLIENTS[client](asked, None))
        if q.get("followup") and turns[0]["session"]:
            turns.append(CLIENTS[client](q["followup"]["ask"], turns[0]["session"]))
    except subprocess.TimeoutExpired:
        turns.append({"calls": [], "answer": "", "session": None, "other_tools": [], "error": "timeout"})
    record = {"id": q["id"], "client": client, "seconds": round(time.time() - start), "asked": asked, "turns": turns}
    (out_dir / client).mkdir(parents=True, exist_ok=True)
    (out_dir / client / f"{q['id']}.json").write_text(json.dumps(record, indent=1))
    return record


def report(results: dict, questions: list[dict], run: str) -> str:
    clients = sorted({c for c, _ in results})
    lines = [f"# GatorPath eval report", "",
             f"Run `{run}`: {len(questions)} questions (evals/questions.yaml) through {', '.join(clients)}, each with only "
             "the gatorpath MCP server. Generated by `evals/run_evals.py`; profiles are synthetic.", "",
             "| Metric | " + " | ".join(clients) + " |", "|---|" + "---|" * len(clients)]

    def rate(client, key):
        vals = [r["scores"].get(key) for (c, _), r in results.items() if c == client]
        vals = [v for v in vals if v is not None]
        return f"{sum(vals)}/{len(vals)}" if vals else "-"

    lines.append("| Questions fully passed | " + " | ".join(
        f"{sum(r['passed'] for (c, _), r in results.items() if c == x)}/{sum(1 for c, _ in results if c == x)}"
        for x in clients) + " |")
    for key, label in (("plan_valid", "Plans passing check_plan"), ("goal_fit", "Electives fit the goal"),
                       ("profile_faithful", "Profile matches what the student said"),
                       ("no_hallucinated_codes", "Answers with no unknown course codes"), ("mention", "States the facts"),
                       ("tools", "Called the tools it needed"), ("mention_any", "Honesty wording"),
                       ("followup.pace_compared", "What-if: compared paces"), ("no_save_profile", "No unasked save_profile"),
                       ("only_gatorpath_tools", "Used only the gatorpath tools")):
        lines.append(f"| {label} | " + " | ".join(rate(x, key) for x in clients) + " |")
    wild = {x: sum(len(r["why"].get("hallucinated", [])) + len(r["why"].get("followup.hallucinated", []))
                   for (c, _), r in results.items() if c == x) for x in clients}
    lines.append("| Hallucinated course codes (total) | " + " | ".join(str(wild[x]) for x in clients) + " |")
    if len(clients) > 1:
        lines += ["", "## Alignment", "", "| Question | " + " | ".join(clients) + " | Same graduation term |", "|---|"
                  + "---|" * (len(clients) + 1)]
        for q in questions:
            rs = [results.get((x, q["id"])) for x in clients]
            terms = {r["why"].get("graduates") for r in rs if r and r["why"].get("graduates")}
            same = "" if not any(r and "graduates" in r["why"] for r in rs) else ("yes" if len(terms) == 1 else "no: " + ", ".join(sorted(terms)))
            lines.append(f"| {q['id']} | " + " | ".join("pass" if r and r["passed"] else "**fail**" if r else "-" for r in rs)
                         + f" | {same} |")
    lines += ["", "## Failures", ""]
    for (c, qid), r in sorted(results.items()):
        if not r["passed"]:
            failed = [k for k, v in r["scores"].items() if v is False]
            lines.append(f"- **{qid}** ({c}): {', '.join(failed)}. " + json.dumps(r["why"], ensure_ascii=False)[:600])
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", default="claude,codex")
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rescore", type=Path)
    ap.add_argument("--into", type=Path, help="run into this existing run directory, then score all of it")
    ap.add_argument("--retry", action="store_true", help="with --into: rerun only the sessions that errored")
    args = ap.parse_args()
    spec = yaml.safe_load((ROOT / "evals/questions.yaml").read_text())
    questions = [q for q in spec["questions"] if not args.only or q["id"] in args.only.split(",")]
    clients = args.clients.split(",")
    saved = Path.home() / ".gatorpath/profile.yaml"
    if args.rescore:
        out_dir = args.rescore
        records = {(p.parent.name, p.stem): json.loads(p.read_text()) for p in out_dir.glob("*/*.json")}
    else:
        if saved.exists():  # load_profile would hand a real student's profile to the eval (golden rule 5)
            sys.exit(f"{saved} exists; move it away before running evals")
        setup()
        out_dir = args.into or ROOT / "data/evals" / datetime.now().strftime("%Y%m%d-%H%M%S")
        jobs = [(c, q) for q in questions for c in clients]
        if args.retry:
            bad = lambda c, q: (f := out_dir / c / f"{q['id']}.json").exists() and any(
                t.get("error") for t in json.loads(f.read_text())["turns"])
            jobs = [(c, q) for c, q in jobs if bad(c, q)]
            print(f"retrying {len(jobs)}:", ", ".join(c + "/" + q["id"] for c, q in jobs))
        with ThreadPoolExecutor(args.workers * len(clients)) as pool:
            done = list(pool.map(lambda job: run_one(*job, out_dir), jobs))
        records = {(r["client"], r["id"]): r for r in done}
        if args.into:
            records = {(p.parent.name, p.stem): json.loads(p.read_text()) for p in out_dir.glob("*/*.json")}
            questions = spec["questions"]
        if saved.exists():
            saved.unlink()  # written by an eval session (it didn't exist before): synthetic
            print("note: an eval session called save_profile; its file was removed")
    results = {k: score(next(q for q in questions if q["id"] == k[1]), r["turns"], spec["goals"])
               for k, r in records.items() if any(q["id"] == k[1] for q in questions)}
    (out_dir / "scores.json").write_text(json.dumps({f"{c}/{i}": r for (c, i), r in results.items()}, indent=1))
    text = report(results, questions, out_dir.name)
    if not args.only or args.into:
        (ROOT / "evals/REPORT.md").write_text(text)
    errored = sorted(f"{c}/{i}" for (c, i), r in records.items() if any(t.get("error") for t in r["turns"]))
    if errored:
        print(f"errored (rerun with --into {out_dir} --clients … --only …): {', '.join(errored)}")
    print(text)


if __name__ == "__main__":
    main()
