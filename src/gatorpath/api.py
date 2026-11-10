"""The web app (ARCHITECTURE §7.6): thin routes over the functions the MCP tools run, plus web/dist. No planning logic
lives here. Nothing about a student is stored or logged: an upload stays in memory, and no student data goes in a URL.
stats.py keeps anonymous daily totals and the feedback students send (D37). /api/assist is the one route with an LLM
behind it (assistant.py); everything else is deterministic."""

import asyncio
import functools
import hmac
import math
import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal, TypedDict

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartParser

from gatorpath import assistant, db, dpr, server, stats
from gatorpath.engine.rules import number
from gatorpath.server import Plan, Profile

MAX_PDF = 15 * 1024 * 1024  # what the upload screen promises
LONGEST_NOTE = 600  # characters of one DPR note sent on to the chat
MultiPartParser.spool_max_size = MAX_PDF + 1  # Starlette writes past 1 MB to a temp file; larger is refused before parsing
DIST = Path(__file__).parents[2] / "web/dist"

app = FastAPI(title="GatorPath")

# The AI helper costs money per request; nothing else here does. Until there are accounts, one address gets PER_HOUR
# requests in any hour, and everyone together PER_DAY, set where it runs. The defaults fit a $20 a month budget at an
# estimated 2 cents a question (not yet measured); the Anthropic console's spend limit stays the last word.
PER_HOUR = int(os.environ.get("GATORPATH_AI_PER_HOUR", 5))
PER_DAY = int(os.environ.get("GATORPATH_AI_PER_DAY", 30))


@dataclass
class Usage:
    """ponytail: in memory and per process, lost on restart; a shared store, or accounts, once the site runs on more
    than one process or host."""
    day: date | None = None
    today: int = 0
    recent: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))
    lock: threading.Lock = field(default_factory=threading.Lock)


used = Usage()


def address(request: Request) -> str:
    """Who's asking. ponytail: behind a proxy this is the proxy, unless uvicorn runs with --proxy-headers and
    --forwarded-allow-ips set to it"""
    return request.client.host if request.client else "unknown"


def admit(who: str) -> dict[str, int]:
    """Counts one AI request, or refuses it with 429 and when to come back. Returns what's left: this hour for who,
    today for everyone. Planning never comes through here."""
    now, today = time.time(), date.today()
    with used.lock:
        if used.day != today:
            used.day, used.today = today, 0
            used.recent.clear()  # a new day: yesterday's addresses go, so the table can't grow without end
        times = used.recent[who]
        while times and now - times[0] > 3600:
            times.popleft()
        if used.today >= PER_DAY:
            raise HTTPException(429, "The AI helper has reached today's limit for everyone. It's back tomorrow; "
                                     "planning, your schedule and the course lists work without it.")
        if len(times) >= PER_HOUR:
            wait = math.ceil((3600 - (now - times[0])) / 60)
            raise HTTPException(429, f"You've asked the AI helper {PER_HOUR} times this hour. Try again in {wait} "
                                     f"minute{'s' if wait != 1 else ''}; planning works without it.")
        times.append(now)
        used.today += 1
        stats.count("ai_question")
        return {"hour": PER_HOUR - len(times), "day": PER_DAY - used.today}


class Options(TypedDict, total=False):
    """What the Goals screen and the what-ifs change. build_plan reads them from the profile."""
    goal: str
    graduate_by: str
    max_units_per_term: float
    include_summer: bool
    include_winter: bool
    f1: bool
    qr_pathway: str
    start_term: str


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class Pick(TypedDict, total=False):
    group: str
    term: str
    code: str
    readiness: str
    covers: list[str]


@app.post("/api/import-dpr")
async def import_dpr(request: Request) -> dict:
    size = request.headers.get("content-length", "")
    if not size.isdigit() or int(size) > MAX_PDF:  # no length: can't promise it stays in memory
        raise HTTPException(413, "A DPR PDF up to 15 MB")
    async with request.form(max_files=1) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(400, "Send the PDF as the `file` part of a multipart form")
        data = await upload.read()
        program = form.get("program")  # the student's pick from unknown_program's choices
    got = await run_in_threadpool(server.dpr_profile, lambda: dpr.read_pdf_bytes(data),
                                  program if isinstance(program, str) else None, lambda: dpr.read_statuses_bytes(data), details=True)
    stats.count("dpr_import")
    return got


@app.post("/api/audit")
def audit(profile: Profile = Body(embed=True)) -> dict:
    """The audit, plus what the record and plan pages show beside it: each taken course's title, and the rules'
    advising directory ("Not sure who to ask?") under the plan's advisor list."""
    out = server.audit_progress(profile)
    if "error" in out:
        return out
    taken = [server.norm_code(r["code"]) for r in profile.get("completed", [])] + profile.get("in_progress", [])
    advising = server.load_rules(server.rules_year(profile), profile["program"])[1].get("advising", [])
    return out | {"courses": server.plan_courses({"semesters": [{"courses": taken}]}, server.catalog(server.DB, server.YEAR)),
                  "directory": next((a for a in advising if a["role"] == "directory"), None)}


@app.post("/api/plan")
def plan(profile: Profile = Body(), options: Options = Body(default={})) -> dict:
    got = server.build_plan(profile | options)
    known = {p["id"] for p in server.list_programs()["programs"]}
    stats.count("plan_built", profile.get("program") if profile.get("program") in known else "other")  # a bounded set of keys
    return got


@app.post("/api/check")
def check(profile: Profile = Body(), plan: Plan = Body()) -> dict:
    return server.check_plan(profile, plan)


@app.post("/api/electives")  # POST, not GET: the profile would be in the URL, and URLs get logged (golden rule 5)
def electives(profile: Profile = Body(), requirement: str = Body(), plan: Plan | None = Body(default=None),
              by_term: str | None = Body(default=None), limit: int = Body(default=25), full: bool = Body(default=False),
              query: str = Body(default="")) -> dict:
    return server.list_eligible_electives(profile, requirement, plan, by_term, limit, full, query=query)


@app.post("/api/assist")
async def assist(request: Request, profile: Profile = Body(), plan: Plan = Body(), picks: list[Pick] = Body(default=[]),
                 messages: list[Message] = Body(default=[]), sections: dict[str, list[str]] = Body(default={}),
                 notes: list[str] = Body(default=[]), job: str = Body(default="")) -> dict:
    """The AI helper: a chat message, or with none, fills the plan. check_plan decides every change (assistant.py).
    sections: {term: [class_nbr]} the student chose on the Schedule, which the chat can change too. notes: what the DPR
    import found, said in the first reply. job: an id the page made up; GET /api/assist-progress?job= says which
    model call it is on. If the page goes away (the student skipped the AI) no more model calls
    are made; the one in flight finishes and is dropped."""
    gone = threading.Event()

    async def watch():  # ponytail: polls twice a second; a push from the client if that ever matters
        while not gone.is_set():
            if await request.is_disconnected():
                return gone.set()
            await asyncio.sleep(0.5)

    watcher = asyncio.create_task(watch())
    try:
        assistant.connect()  # no key: say so before the hourly limit counts the question
        left = admit(address(request))
        key = job if JOB.fullmatch(job) else ""
        got = await run_in_threadpool(assistant.ask, profile, plan, picks, messages, sections,
                                      [n[:LONGEST_NOTE] for n in notes[:12]], gone.is_set,
                                      (lambda n: steps.__setitem__(key, n)) if key else None)
        return {**got, "left": left}
    except assistant.NotConnected as e:
        raise HTTPException(503, str(e)) from e
    except assistant.Cancelled:
        return {}  # nobody is listening
    finally:
        gone.set()
        watcher.cancel()
        steps.pop(job, None)


JOB = re.compile(r"[A-Za-z0-9-]{8,64}")
steps: dict[str, int] = {}  # job id -> the model call it is on. Only a number; gone when the request ends


@app.get("/api/assist-progress")
def assist_progress(job: str) -> dict:
    """Which model call a running /api/assist is on (0 before the first): the build screen's "step N"."""
    return {"step": steps.get(job, 0) if JOB.fullmatch(job) else 0}


@app.get("/api/ai-status")
def ai_status() -> dict:
    """Whether the AI helper has a key here: the page's "Check again". Free, and no limit counts it."""
    try:
        assistant.connect()
    except assistant.NotConnected:
        return {"connected": False}
    return {"connected": True}


@app.post("/api/visit")
def visit(request: Request, ref: str | None = Body(default=None, embed=True)) -> dict:
    """One per browser tab, sent by the page: a visit, and (once a day per address and browser) a visitor."""
    stats.count("visit", ref=ref or "")
    stats.seen(address(request), request.headers.get("user-agent", ""))
    return {"ok": True}


FEEDBACK_PER_HOUR = 5
feedback_log: dict[str, deque] = defaultdict(deque)  # ponytail: in memory and per process, like `used`


@app.post("/api/feedback")
def feedback(request: Request, message: str = Body(embed=True)) -> dict:
    if not message.strip():
        raise HTTPException(400, "Write a message first")
    now, who = time.time(), address(request)
    with used.lock:
        times = feedback_log[who]
        while times and now - times[0] > 3600:
            times.popleft()
        if len(times) >= FEEDBACK_PER_HOUR:
            raise HTTPException(429, "That's a lot of messages this hour. Try again later.")
        times.append(now)
    if not stats.add_feedback(message):
        raise HTTPException(503, "We couldn't save that just now. Try again later.")
    return {"ok": True}


@app.get("/api/stats")
def usage(request: Request, days: int = 30, feedback: bool = False) -> dict:
    """The owner's numbers. Closed (404) until GATORPATH_STATS_TOKEN is set; the token comes in a header, never the URL."""
    token = os.environ.get("GATORPATH_STATS_TOKEN", "")
    if not token:
        raise HTTPException(404)
    if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
        raise HTTPException(401)
    return stats.report(days, feedback)


@app.get("/api/sections")
def sections(term: str, courses: list[str] = Query(), online: list[str] = Query(default=[]),
             keep: list[str] = Query(default=[])) -> dict:
    return server.get_sections(term, courses, online, keep)


@app.get("/api/programs")
def programs() -> dict:
    return server.list_programs()


@app.get("/api/pathways")
def pathways(program: str, catalog_year: str | None = None) -> dict:
    return server.qr_pathways(program, catalog_year)


@app.get("/api/course")
def course(code: str) -> dict:
    return server.get_course(code)


COURSE_ROWS = 300  # the biggest subject has about 100 courses; this only bounds a surprise


@functools.cache  # built once per process: the catalog doesn't change while it runs
def subject_index(db: Path, year: str) -> dict[str, list[str]]:
    """{"AAS": ["AA S 101", ...]} with the spaces of a subject like "AA S" dropped, each list in number order."""
    out: dict[str, list[str]] = {}
    for code in server.catalog(db, year):
        out.setdefault(code.rsplit(" ", 1)[0].replace(" ", ""), []).append(code)
    return {s: sorted(codes, key=lambda c: (number(c), c)) for s, codes in out.items()}


@app.get("/api/course-lines")
def course_lines(codes: list[str] = Query()) -> dict:
    """For the Electives rows: what each course needs and when it runs, for up to 60 courses in one request."""
    out = {}
    for code in dict.fromkeys(codes[:60]):
        got = server.get_course(code)
        if "error" not in got:
            out[got["code"]] = {"needs": (got.get("prereq") or {}).get("raw_text"), "offered": got.get("offered_terms")}
    return {"courses": out}


@app.get("/api/search-courses")
def search_courses(query: str) -> dict:
    """The course-code box: a subject ("CSC", "AA S") and the start of a number list that subject's courses in number
    order; other text is the keyword search. Rows carry their description here, not in the MCP tool (D31)."""
    query = query.strip()[:60]
    if len(query) < 2:
        return {"results": []}
    cat = server.catalog(server.DB, server.YEAR)
    typed = "".join(query.upper().split())
    by_subject = subject_index(server.DB, server.YEAR)
    # longest first, so "ENGR 1" isn't read as ENG
    hit = next((s for s in sorted(by_subject, key=len, reverse=True)
                if typed.startswith(s) and re.fullmatch(r"(\d{1,3}[A-Z]{0,3})?", typed[len(s):])), None)
    codes = ([c for c in by_subject[hit] if c.replace(" ", "").startswith(typed)][:COURSE_ROWS] if hit
             else [r["code"] for r in server.search_courses(query, limit=50)["results"]])
    text = db.descriptions(server.DB, server.YEAR, codes)
    return {"results": [{"code": c, "title": cat[c]["title"], "description": text.get(c)} for c in codes]}


if DIST.is_dir():  # last, so /api wins
    app.mount("/", StaticFiles(directory=DIST, html=True))


def main() -> None:
    """`uv run gatorpath-web`: the site and its API on this computer."""
    if not DIST.is_dir():
        print("web/dist isn't built, so this serves /api only (cd web && npm install && npm run build)")
    uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False)
