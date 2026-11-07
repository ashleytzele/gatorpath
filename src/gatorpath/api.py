"""The web app (ARCHITECTURE §7.1): thin routes over the functions the MCP tools run, plus web/dist. No planning logic
lives here. Nothing is stored or logged: an upload stays in memory, and no student data goes in a URL."""

from pathlib import Path
from typing import TypedDict

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartParser

from gatorpath import dpr, server
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
    return server.audit_progress(profile)


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


@app.get("/api/sections")
def sections(term: str, courses: list[str] = Query()) -> dict:
    return server.get_sections(term, courses)


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
