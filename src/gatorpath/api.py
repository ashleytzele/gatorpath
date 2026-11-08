"""The web app (ARCHITECTURE §7.6): thin routes over the functions the MCP tools run, plus web/dist. No planning logic
lives here. Nothing is stored or logged: an upload stays in memory, and no student data goes in a URL. /api/assist is
the one route with an LLM behind it (assistant.py); everything else is deterministic."""

import math
import os
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

from gatorpath import assistant, dpr, server
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


def admit(who: str) -> None:
    """Counts one AI request, or refuses it with 429 and when to come back. Planning never comes through here."""
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
    return await run_in_threadpool(server.dpr_profile, lambda: dpr.read_pdf_bytes(data),
                                   program if isinstance(program, str) else None, lambda: dpr.read_statuses_bytes(data))


@app.post("/api/audit")
def audit(profile: Profile = Body(embed=True)) -> dict:
    taken = [server.norm_code(r["code"]) for r in profile.get("completed", [])] + profile.get("in_progress", [])
    return server.audit_progress(profile) | {"courses": server.plan_courses({"semesters": [{"courses": taken}]},
                                                                            server.catalog(server.DB, server.YEAR))}


@app.post("/api/plan")
def plan(profile: Profile = Body(), options: Options = Body(default={})) -> dict:
    return server.build_plan(profile | options)


@app.post("/api/check")
def check(profile: Profile = Body(), plan: Plan = Body()) -> dict:
    return server.check_plan(profile, plan)


@app.post("/api/electives")  # POST, not GET: the profile would be in the URL, and URLs get logged (golden rule 5)
def electives(profile: Profile = Body(), requirement: str = Body(), plan: Plan | None = Body(default=None),
              by_term: str | None = Body(default=None), limit: int = Body(default=25), full: bool = Body(default=False)) -> dict:
    return server.list_eligible_electives(profile, requirement, plan, by_term, limit, full)


@app.post("/api/assist")
def assist(request: Request, profile: Profile = Body(), plan: Plan = Body(), picks: list[Pick] = Body(default=[]),
           messages: list[Message] = Body(default=[]), sections: dict[str, list[str]] = Body(default={}),
           notes: list[str] = Body(default=[])) -> dict:
    """The AI helper: a chat message, or with none, fills the plan. check_plan decides every change (assistant.py).
    sections: {term: [class_nbr]} the student chose on the Schedule, which the chat can change too. notes: what the DPR
    import found, said in the first reply."""
    admit(address(request))
    try:
        return assistant.ask(profile, plan, picks, messages, sections, [n[:LONGEST_NOTE] for n in notes[:12]])
    except assistant.NotConnected as e:
        raise HTTPException(503, str(e)) from e


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


if DIST.is_dir():  # last, so /api wins
    app.mount("/", StaticFiles(directory=DIST, html=True))


def main() -> None:
    """`uv run gatorpath-web`: the site and its API on this computer."""
    if not DIST.is_dir():
        print("web/dist isn't built, so this serves /api only (cd web && npm install && npm run build)")
    uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False)
