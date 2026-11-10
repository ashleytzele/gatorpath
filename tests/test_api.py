"""The web API over the fixture catalog: real routes, the same functions as the MCP tools, no AI client."""

import re
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_server import DPR, SCENARIOS, fixture_db, use_fixture_db  # noqa: F401  (the fixtures apply here too)

from gatorpath import api, dpr, server

client = TestClient(api.app)
APP = "\n".join(  # every web source file but the node checks
    f.read_text() for f in sorted((Path(__file__).parents[1] / "web/src").glob("*.ts*")) if not f.name.endswith(".check.ts")
)
STUDENT = SCENARIOS["new freshman, QR 1/2"]
SOPHOMORE = SCENARIOS["sophomore"]


def post(route: str, **body) -> dict:
    response = client.post(route, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def upload(data: bytes = b"%PDF-1.4"):
    return client.post("/api/import-dpr", files={"file": ("dpr.pdf", data, "application/pdf")})


# ---- /api/import-dpr ----

def test_the_web_import_carries_the_dprs_details(monkeypatch):
    monkeypatch.setattr(dpr, "read_pdf_bytes", lambda data: DPR)
    got = upload(b"%PDF-1.4 x").json()
    assert [r["code"] for r in got["not_used"]] == ["TRFX 50NTR"]
    assert {"notes_by_group", "warnings_by_group"} <= set(got) and got["profile"]["sf_state_gpa"] == 3.15
    assert "not_used" not in server.dpr_profile(lambda: DPR)     # the MCP tool's result stays lean


def test_import_dpr_reads_the_upload_in_memory_and_drops_pii(monkeypatch):
    seen = []
    monkeypatch.setattr(dpr, "read_pdf_bytes", lambda data: seen.append(data) or DPR)

    def on_disk(*_):
        raise AssertionError("the PDF was written to disk")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", on_disk)  # what Starlette does past its 1 MB default
    big = b"%PDF-1.4" + b"x" * (3 * 1024 * 1024)
    response = upload(big)
    assert response.status_code == 200 and seen == [big]
    got = response.json()
    assert got["profile"]["program"] == "bs-cs" and {"remaining", "cross_check", "see_advisor"} <= set(got)
    assert not {"name", "student_id", "emplid"} & set(got["profile"])
    for pii in ("Zzfake", "Testperson", "900000001"):  # the fixture's name and ID
        assert pii not in response.text


def test_import_dpr_takes_the_students_pick_of_major(monkeypatch):
    # A Plan line that is more than one program: the page asks, then sends the same file with the pick
    physics = DPR.replace("Computer Science-BS", "Physics-BS").replace("B.S. in Computer Science", "Major Requirements")
    monkeypatch.setattr(dpr, "read_pdf_bytes", lambda data: physics)
    asked = upload().json()
    assert asked["error"] == "unknown_program" and len(asked["choices"]) == 3
    picked = client.post("/api/import-dpr", files={"file": ("dpr.pdf", b"%PDF-1.4", "application/pdf")},
                         data={"program": "bs-physics"})
    assert picked.json()["profile"]["program"] == "bs-physics"


def test_import_dpr_refuses_what_it_wont_read(monkeypatch):
    monkeypatch.setattr(dpr, "read_pdf_bytes", lambda data: pytest.fail("read past the limit"))
    too_big = client.post("/api/import-dpr", files={"file": ("dpr.pdf", b"x" * (api.MAX_PDF + 1))})
    assert too_big.status_code == 413
    assert client.post("/api/import-dpr", data={"note": "no file"}).status_code == 400
    assert client.post("/api/import-dpr", json={"file": "not multipart"}).status_code == 400


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="poppler not installed")
def test_a_file_that_isnt_a_pdf_says_so():
    got = upload(b"not a pdf at all").json()
    assert got["error"] == "unreadable_pdf" and got["warnings"]


# ---- the planning routes return the engine's own fields ----

def test_course_search_lists_the_whole_subject_with_descriptions():
    response = client.get("/api/search-courses", params={"query": "CSC"})
    assert response.status_code == 200
    rows = response.json()["results"]
    assert len(rows) > 50
    assert all(row["code"].startswith("CSC ") for row in rows)
    assert rows[0]["code"] == "CSC 101"
    assert any(row["description"] for row in rows)
    narrowed = client.get("/api/search-courses", params={"query": "CSC 6"}).json()["results"]
    assert narrowed and all(row["code"].startswith("CSC 6") for row in narrowed)
    assert narrowed == [row for row in rows if row["code"].startswith("CSC 6")]
    # a subject with a space, typed with or without it, and a word that isn't a subject
    spaced = client.get("/api/search-courses", params={"query": "aa s 2"}).json()["results"]
    assert [row["code"] for row in spaced] == ["AA S 210", "AA S 213"]
    assert client.get("/api/search-courses", params={"query": "AAS2"}).json()["results"] == spaced
    assert "CSC 101" in [row["code"] for row in client.get("/api/search-courses", params={"query": "intro"}).json()["results"]]
    assert "description" not in server.search_courses("CSC")["results"][0]  # the MCP tool stays lean (D31)


def test_plan_returns_the_engine_fields_and_applies_the_options():
    got = post("/api/plan", profile=STUDENT)
    assert {"semesters", "est_graduation_term", "pace", "see_advisor", "check", "courses", "warnings"} <= set(got)
    assert got["check"]["valid"] and got["semesters"][0]["why"] and "longest_chain" in got["pace"]
    summers = post("/api/plan", profile=STUDENT, options={"include_summer": True})
    assert summers["pace"]["include_summer"] is True and got["pace"]["include_summer"] is False
    assert got == server.build_plan(STUDENT) | {"check": got["check"]}


def test_plan_asks_for_what_it_needs_rather_than_guessing():
    assert post("/api/plan", profile={"program": "bs-cs"})["needs_input"]
    assert post("/api/plan", profile={"program": "no-such-major"})["error"]
    assert client.post("/api/plan", json={"profile": {}}).status_code == 422


def test_check_returns_errors_and_honors_each_terms_cap():
    plan = {"semesters": post("/api/plan", profile=STUDENT)["semesters"]}
    assert post("/api/check", profile=STUDENT, plan=plan)["valid"] is True
    capped = {"semesters": plan["semesters"][:-1] + [plan["semesters"][-1] | {"max_units": 1}]}
    got = post("/api/check", profile=STUDENT, plan=capped)
    assert got["valid"] is False and got["errors"] and "see_advisor" in got


def test_electives_take_the_profile_in_the_body_never_the_url():
    plan = {"semesters": post("/api/plan", profile=STUDENT)["semesters"]}
    term = next(s["term"] for s in plan["semesters"] if any(isinstance(c, dict) and c["slot"] == "senior_electives" for c in s["courses"]))
    got = post("/api/electives", profile=STUDENT, requirement="senior_electives", plan=plan, by_term=term)
    assert got["group"] == "senior_electives" and {"readiness", "description", "offered"} <= set(got["options"][0])
    found = post("/api/electives", profile=STUDENT, requirement="senior_electives", plan=plan, by_term=term,
                 query=got["options"][0]["code"])
    assert found["options"][0]["code"] == got["options"][0]["code"] and found["total_options"] >= 1
    assert post("/api/electives", profile=STUDENT, requirement="no_such_group")["error"]
    assert client.get("/api/electives", params={"requirement": "senior_electives"}).status_code in (404, 405)


def test_sections_return_the_schedule_fields():
    got = client.get("/api/sections", params={"term": "2027-spring", "courses": ["CSC 340", "MATH 225"]}).json()
    assert {"sections", "schedule", "sets", "always_clash", "not_offered", "unknown", "scraped_at", "warnings"} <= set(got)
    assert client.get("/api/sections", params={"term": "spring", "courses": ["CSC 340"]}).json()["error"] == "bad_term"
    assert client.get("/api/sections", params={"term": "2027-spring", "courses": ["CSC 340"], "online": ["CSC 340"]}).status_code == 200


def test_a_requirement_a_student_leaves_out_reaches_the_audit_and_the_plan():
    """Review's "not on my DPR": for this student only, flagged for an advisor, and nothing plans for it."""
    student = SCENARIOS["Fall 2024 catalog (old GE)"]
    slots = lambda plan: [c["slot"] for s in plan["semesters"] for c in s["courses"] if isinstance(c, dict)]
    assert "ge_f" in slots(post("/api/plan", profile=student))
    left_out = student | {"not_on_dpr": ["ge_f"]}
    plan = post("/api/plan", profile=left_out)
    assert "ge_f" not in slots(plan) and plan["check"]["valid"]
    assert any("confirm with an advisor" in w and "Ethnic" in w for w in plan["warnings"])
    assert next(g for g in post("/api/audit", profile=left_out)["groups"] if g["id"] == "ge_f")["waived_by"]


def test_the_screens_other_reads():
    audit = post("/api/audit", profile=SOPHOMORE)
    assert audit["groups"] and audit["totals"]["units"]["needed"] and "see_advisor" in audit
    assert audit["courses"]["CSC 101"]["title"] == "Introduction to Computing"  # Review shows titles
    assert any(p["id"] == "bs-cs" for p in client.get("/api/programs").json()["programs"])
    assert client.get("/api/course", params={"code": "CSC 340"}).json()["title"] == "Programming Methodology"


def test_the_audit_carries_the_advising_directory_for_the_plans_advisor_list():
    found = post("/api/audit", profile=SOPHOMORE)["directory"]
    assert found["role"] == "directory" and found["link"].startswith("https://")


def test_the_plan_tab_has_no_what_if_row_or_old_progress_view():
    assert "What if I" not in APP and '"Progress"' not in APP and "ProgressView" not in APP


def test_the_workspace_is_the_main_landmark_and_its_copy_matches_its_buttons():
    assert '<main id="main" tabIndex={-1} className="workspace-main">' in APP  # the plan, Electives and Schedule screens have one, like the others
    assert "Swap or Choose a row" not in APP  # a chosen row's button says Details; an open one says Choose
    assert "of ${same.length}" in APP  # rows of one requirement are numbered, not five of "Electives (15 units)"
    assert "Clear my saved data" in APP and "wiped.on" in APP  # the footer clears this tab's saved record and plan
    assert "Still working" in APP + (Path(__file__).parents[1] / "web/src/Building.tsx").read_text()


def test_every_screen_has_a_main_landmark_and_a_skip_link():
    web = Path(__file__).parents[1] / "web/src"
    for name in ("App.tsx", "Goals.tsx", "Record.tsx", "Building.tsx"):
        mains = re.findall(r"<main\b[^>]*>", (web / name).read_text())
        assert mains and all('id="main"' in m and 'role="status"' not in m for m in mains), (name, mains)  # role=status would drop the landmark
    assert 'href="#main"' in (web / "App.tsx").read_text() and 'href="#top"' in (web / "Landing.tsx").read_text()


def test_the_landing_page_is_built_around_the_products_own_screens():
    root = Path(__file__).parents[1]
    landing = (root / "web/src/Landing.tsx").read_text()
    assert landing.count('className="ld-label"') == 1  # the hero's; the other sections have only their headings
    assert "<svg" not in landing and "ld-grid2" not in landing  # no icon card grid
    for picture in ("requirements", "route", "chat", "schedule"):  # every screen you gave is on the page, with alt text
        name = f"landing-{picture}.jpg"
        assert f'src="/{name}"' in landing and (root / "web/public" / name).exists(), name
    assert not (root / "web/public/landing-plan.jpg").exists() and not (root / "web/public/landing-weekly.jpg").exists()  # the old ones
    assert all(img.count('alt="') == 1 and 'alt=""' not in img for img in re.findall(r"<img [^>]*>", landing))
    assert "Compare with another major" in landing  # the asks are the chat's real buttons
    assert not (root / "web/public/landing-building.jpg").exists() and "landing-building" not in landing
    assert 'className="lp-steps"' in landing and "Upload your DPR" in landing  # the three steps are a timeline, not a picture


def test_the_chat_note_is_short_and_shows_no_question_counter():
    chat = (Path(__file__).parents[1] / "web/src/Chat.tsx").read_text()
    assert "Checked against the Bulletin. For official answers, see your DPR or" in chat
    assert "leftText" not in APP and "{free" not in chat  # the limit is shown only once it is reached


def test_the_chat_offers_to_compare_majors_while_gator_ai_is_available():
    assert '"Compare with another major"' in APP and "work.aiAvailable ? [{ id: \"major\"" in APP
    assert "compare my plan with another major" in APP


def test_the_dpr_video_plays_on_repeat_but_can_be_paused_and_respects_reduced_motion():
    record = (Path(__file__).parents[1] / "web/src/Record.tsx").read_text()
    video = record[record.index('<video className="howto-video"'):record.index("</video>")]
    assert "autoPlay: true, loop: true" in video and " muted " in video and " controls " in video
    assert "prefers-reduced-motion: reduce" in video  # no autoplay for a student who asks for less motion


def test_the_stylesheet_uses_tokens_for_colors_and_stacking():
    css = (Path(__file__).parents[1] / "web/src/index.css").read_text()
    tokens, _, rules = css.partition("  * {\n    box-sizing: border-box;")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", rules), "a color outside the :root tokens"
    assert not re.findall(r"z-index:\s*\d", css), "a raw z-index: use --z-raised, --z-sticky, --z-bar, --z-sheet, --z-overlay or --z-toast"


def test_every_goals_question_but_summer_and_winter_has_to_be_answered_before_the_plan_is_built():
    goals = (Path(__file__).parents[1] / "web/src/Goals.tsx").read_text()
    for needed in ('"q-interests"', '"q-after"', '"q-f1"', '"q-qr"', '"q-start"'):  # each has a message and an id to scroll to
        assert goals.count(needed) >= 2, needed
    assert "setTried(true)" in goals and "Object.keys(unanswered)[0]" in goals  # Build stops at the first unanswered one
    assert "AI / Machine Learning" not in goals and "Clinical / Counseling" not in goals  # no preset interest chips, for any major
    assert 'value="skip"' in goals and "Not sure yet" in goals  # "Prefer not to say" and "Not sure yet" are answers
    assert "group optional title=\"Will you take summer or Winter Session classes?\"" in goals  # the one optional question


def test_the_site_never_calls_a_plan_verified_and_sends_questions_to_navigator():
    assert "verified" not in APP.lower() and "https://sfsu.campus.eab.com/" in APP
    assert "advising.sfsu.edu" not in APP and "/undergrads/advising" not in APP


def test_the_preview_bars_stay_behind_demo():
    bars = [m.start() for m in re.finditer(r'variant-switcher|demo-error|Preview goal options', APP)]
    assert len(bars) == 3  # the Schedule tab has none now: its problems are one line, not states
    assert all("{DEMO && (" in APP[max(0, at - 250):at] for at in bars)


# ---- /api/assist: how much one address, and everyone, can ask of the AI ----

def test_the_ai_helper_has_an_hourly_limit_per_address_and_a_daily_one_for_everyone(monkeypatch):
    monkeypatch.setattr(api.assistant, "ask", lambda *a, **k: {"reply": "ok"})
    monkeypatch.setattr(api.assistant, "connect", lambda: None)  # a key is set
    monkeypatch.setattr(api, "PER_HOUR", 3)
    monkeypatch.setattr(api, "PER_DAY", 5)
    monkeypatch.setattr(api, "used", api.Usage())
    ask = lambda who="1.1.1.1": client.post("/api/assist", json={"profile": STUDENT, "plan": {"semesters": []}},
                                         headers={"X-Test-Client": who})
    monkeypatch.setattr(api, "address", lambda request: request.headers.get("X-Test-Client", "?"))
    answers = [ask() for _ in range(3)]
    assert [a.status_code for a in answers] == [200, 200, 200]
    assert [a.json()["left"] for a in answers] == [{"hour": 2, "day": 4}, {"hour": 1, "day": 3}, {"hour": 0, "day": 2}]
    over = ask()
    assert over.status_code == 429 and "this hour" in over.json()["detail"] and "minute" in over.json()["detail"]
    assert ask("2.2.2.2").status_code == 200 and ask("3.3.3.3").status_code == 200  # someone else: their own hour
    full = ask("4.4.4.4")  # 5 today, from everyone
    assert full.status_code == 429 and "today" in full.json()["detail"] and "planning" in full.json()["detail"]
    assert client.post("/api/plan", json={"profile": STUDENT}).status_code == 200  # planning isn't limited


def test_without_a_key_a_question_isnt_counted_against_the_limit(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(api, "used", api.Usage())
    got = client.post("/api/assist", json={"profile": STUDENT, "plan": {"semesters": []}})
    assert got.status_code == 503 and "isn't connected" in got.json()["detail"]
    assert api.used.today == 0 and not any(api.used.recent.values())



def test_check_again_says_whether_the_ai_has_a_key_and_counts_nothing(monkeypatch):
    monkeypatch.setattr(api, "used", api.Usage())
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    assert client.get("/api/ai-status").json() == {"connected": False}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert client.get("/api/ai-status").json() == {"connected": True}
    assert api.used.today == 0 and not any(api.used.recent.values())


def test_the_build_screen_can_ask_which_model_call_a_fill_is_on(monkeypatch):
    seen = {}
    monkeypatch.setattr(api.assistant, "connect", lambda: None)
    monkeypatch.setattr(api.assistant, "ask", lambda *a, **k: seen.update(progress=a[7]) or {"reply": "ok"})
    monkeypatch.setattr(api, "used", api.Usage())
    body = {"profile": STUDENT, "plan": {"semesters": []}}
    client.post("/api/assist", json=body | {"job": "build-abc12345"})
    assert callable(seen["progress"])  # a valid job id gets a progress callback
    client.post("/api/assist", json=body | {"job": "../../etc"})
    assert seen["progress"] is None  # anything else doesn't
    api.steps["build-abc12345"] = 4
    assert client.get("/api/assist-progress", params={"job": "build-abc12345"}).json() == {"step": 4}
    assert client.get("/api/assist-progress", params={"job": "unknown-job-id"}).json() == {"step": 0}
    assert client.get("/api/assist-progress", params={"job": "../x"}).json() == {"step": 0}
    api.steps.clear()


def test_electives_rows_get_what_each_chosen_course_needs_and_when_it_runs():
    got = client.get("/api/course-lines", params=[("codes", "CSC 340"), ("codes", "csc340"), ("codes", "NOPE 999")]).json()["courses"]
    assert list(got) == ["CSC 340"]  # one entry, however it was typed; an unknown course is left out
    assert "needs" in got["CSC 340"] and "offered" in got["CSC 340"]
    assert client.get("/api/course-lines", params=[("codes", "CSC 215")] * 100).status_code == 200  # bounded to 60


def test_pathways_name_each_placements_first_math():
    got = client.get("/api/pathways", params={"program": "bs-cs"}).json()["pathways"]
    assert [(p["pathway"], [c["code"] for c in p["courses"]]) for p in got] == [
        ("1/2", ["MATH 226"]), ("3/4", ["MATH 197", "MATH 198", "MATH 226"])]
    assert all(c["title"] for p in got for c in p["courses"])
    for program in ("no-such-major", "../../university/2026-27"):  # a made-up id never becomes a file path
        assert client.get("/api/pathways", params={"program": program}).json()["error"] == "unknown_program"


def test_the_landing_page_says_only_what_is_true():
    majors = len(list((Path(__file__).parents[1] / "rules/programs/2026-27").glob("*.yaml")))
    assert f"Rules for {majors} majors" in APP
    assert "Trusted by" not in APP and "testimonial" not in APP.lower()


def test_every_course_on_the_landing_page_is_in_the_catalog():
    import json

    rows = {r["code"]: r["title"] for r in json.loads((Path(__file__).parents[1] / "tests/fixtures/catalog_rows.json").read_text())}
    text = (Path(__file__).parents[1] / "web/src/Landing.tsx").read_text()
    codes = re.findall(r"\b[A-Z]{2,5} \d{3}[A-Z]{0,3}\b", text)
    assert all(c in rows for c in codes), [c for c in codes if c not in rows]  # the samples are pictures now: none is fine
    for code, after in re.findall(r"\b([A-Z]{2,5} \d{3}[A-Z]{0,3}) ([A-Z][a-z][^·<\"]*)", text):  # a title written next to a code
        assert after.strip().startswith(rows[code]), (code, after)


def test_the_first_screen_shows_how_to_get_the_dpr():
    record = (Path(__file__).parents[1] / "web/src/Record.tsx").read_text()
    assert "How to get your DPR" in record and "help-box" not in record and "{PRIVACY}" not in record


def test_your_goals_are_numbered_questions_with_no_advanced_options():
    assert "Advanced options" not in APP and "What’s your first term?" not in APP and "What's your first term?" not in APP
    assert "Find your Pathway/Category on Gator Smart Start" in APP and "https://gatorsmartstart.sfsu.edu/pathways" in APP


def test_building_waits_for_the_ai_and_the_workspace_no_longer_fills_on_mount():
    assert "started.current" not in APP and "function BuildingScreen" not in (Path(__file__).parents[1] / "web/src/App.tsx").read_text()
    building = (Path(__file__).parents[1] / "web/src/Building.tsx").read_text()
    assert "Rather pick your own electives?" in building and "Skip, I’ll choose myself" in building
    assert "skeleton" not in building and 'className="skip-card"' in building  # a card with the choice, no grey boxes
    assert "abort.current?.abort()" in building and "setSkipped(true)" in building and "finish(" not in building[building.index("<section"):building.index("</section>")]
    assert "skipped" in APP and "You chose your own electives" in APP  # the chat's first line says so
    assert "work.aiAvailable ? state.semesters" in APP  # no "Choose my open courses" while Gator AI is off


def test_buttons_say_swap_select_or_choose():
    words = re.findall(r">\s*([A-Z][A-Za-z ]{1,30}?)\s*(?:<|\{)", APP)
    assert not [w for w in words if re.match(r"(Change|Pick)\b", w)]
    assert re.findall(r'"(Change|Pick)"', APP) == []
    assert "Swap" in APP and "Select" in APP
