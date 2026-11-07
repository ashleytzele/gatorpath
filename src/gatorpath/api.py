"""The web app (ARCHITECTURE §7.6): thin routes over the functions the MCP tools run, plus web/dist. No planning logic
lives here. Nothing is stored or logged: an upload stays in memory, and no student data goes in a URL. /api/assist is
the one route with an LLM behind it (assistant.py); everything else is deterministic."""

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
MultiPartParser.spool_max_size = MAX_PDF + 1  # Starlette writes past 1 MB to a temp file; larger is refused before parsing
DIST = Path(__file__).parents[2] / "web/dist"

app = FastAPI(title="GatorPath")


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
    return await run_in_threadpool(server.dpr_profile, lambda: dpr.read_pdf_bytes(data))


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
def assist(profile: Profile = Body(), plan: Plan = Body(), picks: list[Pick] = Body(default=[]),
           messages: list[Message] = Body(default=[])) -> dict:
    """The AI helper: a chat message, or with none, fills the plan. check_plan decides every change (assistant.py)."""
    try:
        return assistant.ask(profile, plan, picks, messages)
    except assistant.NotConnected as e:
        raise HTTPException(503, str(e)) from e


@app.get("/api/sections")
def sections(term: str, courses: list[str] = Query(), online: list[str] = Query(default=[])) -> dict:
    return server.get_sections(term, courses, online)


@app.get("/api/programs")
def programs() -> dict:
    return server.list_programs()


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
