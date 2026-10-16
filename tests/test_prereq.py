"""Golden prereq strings, copied verbatim from the 2026-27 Bulletin, with hand-checked trees (ARCHITECTURE §6.3)."""

import pytest

from gatorpath.engine.prereq import parse_prereq


def c(code, grade=None, conc=False):
    leaf = {"course": code}
    if grade:
        leaf["min_grade"] = grade
    if conc:
        leaf["concurrent_ok"] = True
    return leaf


def ge(area, grade=None):
    return {"ge_area": area, **({"min_grade": grade} if grade else {})}


def all_(*xs):
    return {"all": list(xs)}


def any_(*xs):
    return {"any": list(xs)}


UP, SENIOR, GRAD = {"standing": "upper"}, {"standing": "senior"}, {"standing": "graduate"}
PERM, DEPT, ADVISOR = {"permission": "instructor"}, {"permission": "department"}, {"permission": "advisor"}
GPA3, EQ = {"gpa": 3.0}, {"equivalent": True}
FYMAM = {"requirement": "First-Year Math Advising Module"}
ATC = {"requirement": "Advancement to Candidacy and Culminating Experience forms approved by Graduate Studies"}
PROPOSAL = {"requirement": "Approved study proposal on file by registration"}
CHAIR = {"permission": "committee_chair"}


def r(text):
    return {"restricted_to": text}


GOLDEN = [
    ("CSC 215", "CSC 101 with a grade of C or better.", c("CSC 101", "C")),
    ("CSC 220", "CSC 210 or CSC 215 with a grade of C or better.", any_(c("CSC 210", "C"), c("CSC 215", "C"))),
    ("CSC 221", "CSC 210 or CSC 215; concurrent enrollment in CSC 220.",
     all_(any_(c("CSC 210"), c("CSC 215")), c("CSC 220", conc=True))),
    ("CSC 230", "CSC 210 or CSC 215 or ENGR 213, and MATH 227 (may be taken concurrently) with grades of C or better.",
     all_(any_(c("CSC 210", "C"), c("CSC 215", "C"), c("ENGR 213", "C")), c("MATH 227", "C", conc=True))),
    ("CSC 256", "CSC 230 with a grade of C or better.", c("CSC 230", "C")),
    ("CSC 300GW", "Restricted to upper-division Computer Science majors and minors; GE Area 1A/A2; CSC 210 or CSC 215.",
     all_(r("upper-division Computer Science majors and minors"), ge("1A"), any_(c("CSC 210"), c("CSC 215")))),
    ("CSC 306", "Restricted to Biology, Chemistry, and Biochemistry majors and Certificate in Data Science and Machine "
                "Learning for Biotechnology Professionals students; upper-division standing; or permission of the instructor.",
     any_(all_(r("Biology, Chemistry, and Biochemistry majors and Certificate in Data Science and Machine Learning for "
                 "Biotechnology Professionals students"), UP), PERM)),
    ("CSC 307", "Upper-division standing or permission of the instructor.", any_(UP, PERM)),
    ("CSC 309", "MATH 226 or permission of the instructor.", any_(c("MATH 226"), PERM)),
    ("CSC 310", "Concurrent enrollment in CSC 309 is recommended.", None),
    ("CSC 311", "CSC 306* or equivalent.", any_(c("CSC 306"), EQ)),
    ("CSC 340", "CSC 220 and CSC 230 with grades of C or better.", all_(c("CSC 220", "C"), c("CSC 230", "C"))),
    ("CSC 412", "CSC 220; concurrent enrollment in CSC 340 recommended.", c("CSC 220")),
    ("CSC 413", "CSC 220 and CSC 317 with grades of C or better.", all_(c("CSC 220", "C"), c("CSC 317", "C"))),
    ("CSC 415", "CSC 256, CSC 340*, MATH 324, and PHYS 230 with grades of C or better or graduate standing*.",
     any_(all_(c("CSC 256", "C"), c("CSC 340", "C"), c("MATH 324", "C"), c("PHYS 230", "C")), GRAD)),
    ("CSC 509", "CSC 411 (may be taken concurrently).", c("CSC 411", conc=True)),
    ("CSC 510", "CSC 340* and MATH 324* with grades of C or better.", all_(c("CSC 340", "C"), c("MATH 324", "C"))),
    ("CSC 511", "Restricted to Computing Applications minor and Certificate in Data Science and Machine Learning for "
                "Biotechnology students; CSC 411 (may be taken concurrently).",
     all_(r("Computing Applications minor and Certificate in Data Science and Machine Learning for Biotechnology students"),
          c("CSC 411", conc=True))),
    # Grade phrase without "all" covers only its own clause.
    ("CSC 520", "CSC 220 and CSC 230; MATH 225 or MATH 325 with grades of C or better.",
     all_(c("CSC 220"), c("CSC 230"), any_(c("MATH 225", "C"), c("MATH 325", "C")))),
    ("CSC 600", "CSC 413* and CSC 510* with grades of C or better or graduate-level standing*.",
     any_(all_(c("CSC 413", "C"), c("CSC 510", "C")), GRAD)),
    ("CSC 601", "CSC 408* or CSC 411* or CSC 509*.", any_(c("CSC 408"), c("CSC 411"), c("CSC 509"))),
    ("CSC 603", "CSC 413 with a grade of C or better; GPA of 3.0 or better; or permission of the instructor.",
     any_(all_(c("CSC 413", "C"), GPA3), PERM)),
    ("CSC 615", "CSC 415* with a grade of C or better or permission of the instructor.", any_(c("CSC 415", "C"), PERM)),
    ("CSC 620", "Upper-division standing; CSC 413* with a grade of C or better; GPA of 3.0 or higher; or permission of the instructor.",
     any_(all_(UP, c("CSC 413", "C"), GPA3), PERM)),
    ("CSC 621", "Upper-division standing; CSC 510*; MATH 225* or MATH 325* with grades of C or better; GPA of 3.0 or "
                "higher; or permission of the instructor.",
     any_(all_(UP, c("CSC 510"), any_(c("MATH 225", "C"), c("MATH 325", "C")), GPA3), PERM)),
    ("CSC 630", "CSC 413* and either MATH 225* or MATH 325* with grades of C or better; a GPA of 3.0 or better; or "
                "permission of the instructor.",
     any_(all_(c("CSC 413", "C"), any_(c("MATH 225", "C"), c("MATH 325", "C")), GPA3), PERM)),
    ("CSC 647", "Upper-division standing; CSC 415* and either MATH 225* or MATH 325* with a grade of C or better; CSC 308, "
                "CSC 309, and CSC 656 recommended; GPA of 3.0 or higher; or permission of the instructor.",
     any_(all_(UP, c("CSC 415", "C"), any_(c("MATH 225", "C"), c("MATH 325", "C")), GPA3), PERM)),
    ("CSC 653", "Upper-division standing; CSC 415* with a grade of C or better; GPA of 3.0 or better; or permission of the instructor.",
     any_(all_(UP, c("CSC 415", "C"), GPA3), PERM)),
    ("CSC 656", "CSC 415* (may be taken concurrently) or permission of the instructor.", any_(c("CSC 415", conc=True), PERM)),
    ("CSC 659", "Restricted to upper-division students; CSC 413 with C or better; GPA of 3.0 or better; or permission of the instructor.",
     any_(all_(UP, c("CSC 413", "C"), GPA3), PERM)),
    ("CSC 665", "Restricted to upper-division standing; CSC 413* with a grade of C or better; or permission of the instructor.",
     any_(all_(UP, c("CSC 413", "C")), PERM)),
    ("CSC 668", "Senior standing; CSC 413* with a grade of C or better; GPA of 3.0 or better; or permission of the instructor.",
     any_(all_(SENIOR, c("CSC 413", "C"), GPA3), PERM)),
    ("CSC 680", "Restricted to senior Computer Science majors; CSC 415* with a grade of C or better; 3.0 GPA or higher; "
                "or permission of the instructor.",
     any_(all_(r("senior Computer Science majors"), c("CSC 415", "C"), GPA3), PERM)),
    ("CSC 694", "Permission of the instructor.", PERM),
    ("CSC 697", "CSC 415 and CSC 510, or CSC 648; or permission of the instructor.",
     any_(all_(c("CSC 415"), c("CSC 510")), c("CSC 648"), PERM)),
    ("CSC 720", "Restricted to graduate Computer Science or graduate certificate in Software Engineering students, or "
                "permission of the instructor.",
     any_(r("graduate Computer Science or graduate certificate in Software Engineering students"), PERM)),
    ("CSC 803", "Graduate level standing; or permission of the instructor.", any_(GRAD, PERM)),
    ("CSC 854", "Graduate standing.", GRAD),
    ("CSC 897", "Permission of the Computer Science Department.", DEPT),
    ("CSC 899", "Approval of the department and instructor.", all_(DEPT, PERM)),
    ("MATH 227", "MATH 226* with a grade of C or better.", c("MATH 226", "C")),
    ("MATH 300GW", "GE Area 1A/A2; MATH 227 or equivalent with a grade of C or higher.",
     all_(ge("1A"), any_(c("MATH 227", "C"), EQ))),
    ("MATH 335", "MATH 301GW and either MATH 225 or MATH 325 all with a grade of C or better; or permission of the instructor.",
     any_(all_(c("MATH 301GW", "C"), any_(c("MATH 225", "C"), c("MATH 325", "C"))), PERM)),
    ("MATH 338", "MATH 209* or MATH 309* or CSC 210* or CSC 215* or CSC 309* with a grade of C or better or permission of the instructor.",
     any_(c("MATH 209", "C"), c("MATH 309", "C"), c("CSC 210", "C"), c("CSC 215", "C"), c("CSC 309", "C"), PERM)),
    # "all with grades" at the end of a clause covers every clause before it in the group.
    ("MATH 376", "MATH 228; MATH 225 or MATH 325; MATH 209 or CSC 309 or equivalent, all with grades of C or better.",
     all_(c("MATH 228", "C"), any_(c("MATH 225", "C"), c("MATH 325", "C")), any_(c("MATH 209", "C"), c("CSC 309", "C"), EQ))),
    ("MATH 400", "MATH 228; MATH 225 or MATH 325; and CSC 210 or CSC 215 or MATH 209 or MATH 309, all with grades of C or better.",
     all_(c("MATH 228", "C"), any_(c("MATH 225", "C"), c("MATH 325", "C")),
          any_(c("CSC 210", "C"), c("CSC 215", "C"), c("MATH 209", "C"), c("MATH 309", "C")))),
    ("MATH 420", "Upper-division standing; MATH 301GW; CSC 230 or MATH 310 or MATH 325; all with grades of C or better; "
                 "GPA of 3.0 or higher; or permission of the instructor.",
     any_(all_(UP, c("MATH 301GW", "C"), any_(c("CSC 230", "C"), c("MATH 310", "C"), c("MATH 325", "C")), GPA3), PERM)),
    ("MATH 424", "Upper-division standing; MATH 228*, MATH 325*, and MATH 440* all with grades of C or better; GPA of 3.0 "
                 "or higher; or permission of the instructor.",
     any_(all_(UP, c("MATH 228", "C"), c("MATH 325", "C"), c("MATH 440", "C"), GPA3), PERM)),
    ("MATH 440", "MATH 228* with a grade of C or better (may be taken concurrently); or permission of the instructor.",
     any_(c("MATH 228", "C", conc=True), PERM)),
    ("MATH 442", "MATH 228*, MATH 325*, and MATH 440* all with grades of C or better, or permission of the instructor.",
     any_(all_(c("MATH 228", "C"), c("MATH 325", "C"), c("MATH 440", "C")), PERM)),
    ("MATH 475", "MATH 335 with a grade of C or better and one of the following: concurrent enrollment in MATH 370 or "
                 "permission of the instructor.",
     all_(c("MATH 335", "C"), any_(c("MATH 370", conc=True), PERM))),
    ("MATH 711", "MATH 710 and MATH 725 with grades of B- or better or permission of the instructor.",
     any_(all_(c("MATH 710", "B-"), c("MATH 725", "B-")), PERM)),
    ("MATH 850", "MATH 435/MATH 735 with a grade of C or better or permission of the instructor.",
     any_(c("MATH 435", "C"), c("MATH 735", "C"), PERM)),
    ("PHYS 111", "MATH 198 or MATH 199 or MATH 226 or equivalent with a grade of C-minus or higher. Concurrent enrollment "
                 "in PHYS 112 required.",
     all_(any_(c("MATH 198", "C-"), c("MATH 199", "C-"), c("MATH 226", "C-"), EQ), c("PHYS 112", conc=True))),
    ("PHYS 121", "PHYS 111 with a grade of C- or better; concurrent enrollment in PHYS 122.",
     all_(c("PHYS 111", "C-"), c("PHYS 122", conc=True))),
    ("PHYS 220", "MATH 226 with a grade of C or better; concurrent enrollment in PHYS 222; concurrent enrollment in MATH 227 recommended.",
     all_(c("MATH 226", "C"), c("PHYS 222", conc=True))),
    ("PHYS 222", "Concurrent enrollment in PHYS 220.", c("PHYS 220", conc=True)),
    ("PHYS 200", "Restricted to Physics & Astronomy majors & minors.", r("Physics & Astronomy majors & minors")),
    ("PHYS 305", "GE Areas 1A/A2*, 1B/A3*, 1C/A1*, 2/B4*, and 5A/B1* all with grades of C- or better or permission of the instructor.",
     any_(all_(ge("1A", "C-"), ge("1B", "C-"), ge("1C", "C-"), ge("2", "C-"), ge("5A", "C-")), PERM)),
    ("PHYS 320", "MATH 228, PHYS 230, and PHYS 240 with grades of C or better; MATH 245 or MATH 376 with a grade of C or "
                 "better (may be taken concurrently).",
     all_(c("MATH 228", "C"), c("PHYS 230", "C"), c("PHYS 240", "C"),
          any_(c("MATH 245", "C", conc=True), c("MATH 376", "C", conc=True)))),
    ("PHYS 330", "PHYS 230, PHYS 240, and MATH 228, and either MATH 245 or both MATH 225 & MATH 376, all completed with "
                 "grades of C or better; MATH 376 (may be taken concurrently).",
     all_(c("PHYS 230", "C"), c("PHYS 240", "C"), c("MATH 228", "C"),
          any_(c("MATH 245", "C"), all_(c("MATH 225", "C"), c("MATH 376", "C"))), c("MATH 376", conc=True))),
    # A clause that is only a grade phrase covers every clause before it in the group.
    ("PHYS 360", "MATH 245 or MATH 376; PHYS 385; with grades of C- or better.",
     all_(any_(c("MATH 245", "C-"), c("MATH 376", "C-")), c("PHYS 385", "C-"))),
    ("PHYS 440", "CSC 309 or MATH 209; MATH 245 or MATH 376; and PHYS 320, all with grades of C- or better; overall GPA "
                 "of at least 3.0 or permission of the instructor.",
     all_(any_(c("CSC 309", "C-"), c("MATH 209", "C-")), any_(c("MATH 245", "C-"), c("MATH 376", "C-")),
          c("PHYS 320", "C-"), any_(GPA3, PERM))),
    ("PHYS 491GW", "GE Areas 1A/A2, 1B/A3, 1C/A1; PHYS 320 and PHYS 321 with grades of C- minus or better; CSC 309 strongly recommended.",
     all_(ge("1A"), ge("1B"), ge("1C"), c("PHYS 320", "C-"), c("PHYS 321", "C-"))),
    ("PHYS 685", "Upper-division standing.", UP),
    # A program restriction written without "Restricted to".
    ("MATH 720", "Graduate Mathematics students or permission of the instructor.", any_(r("Graduate Mathematics students"), PERM)),
    ("CSC 830", "MS in Computer Science students.", r("MS in Computer Science students")),
    ("MATH 575", "MATH 565 with a grade of C or better; or BA Math Concentration in Teaching majors; or permission of the instructor.",
     any_(c("MATH 565", "C"), r("BA Math Concentration in Teaching majors"), PERM)),
    ("CSC 890", "Permission of the instructor or graduate advisor.", any_(PERM, ADVISOR)),
    # QR placement Category = roadmap QR pathway (Bulletin p.1906 "QR Pathway 1/2" -> p.1908 "Quantitative Reasoning Category 1/2")
    ("MATH 107", "First-Year Math Advising Module; Category III* or IV* placement for QR/Math.", all_(FYMAM, {"qr_category": [3, 4]})),
    ("MATH 197", "First-Year Math Advising Module; Category III* and IV* placement for QR/Math.", all_(FYMAM, {"qr_category": [3, 4]})),
    ("PHYS 101", "Category I or II placement for QR/Math, or GE Area 2/B4, or MATH 197.",
     any_({"qr_category": [1, 2]}, ge("2"), c("MATH 197"))),
    ("MATH 112", "First-Year Math Advising Module.", FYMAM),
    # Audience notes and "should" advice are not requirements.
    ("MATH 110", "First-Year Math Advising Module. For students who wish to take business calculus in one semester.", FYMAM),
    ("MATH 124", "First-Year Math Advising Module. Students who elect to take additional support should concurrently enroll in MATH 123.", FYMAM),
    ("MATH 122", "First-Year Math Advising Module. Concurrent enrollment in ISED 160* or PSY 171 required.",
     all_(FYMAM, any_(c("ISED 160", conc=True), c("PSY 171", conc=True)))),
    ("MATH 696", "MATH 460 with a grade of C or better. May be replaced by permission of the instructor.", any_(c("MATH 460", "C"), PERM)),
    ("MATH 697", "Successful completion of MATH 696 in a previous semester.", c("MATH 696")),
    # Graduate-studies boilerplate (140 prereqs catalog-wide): one named requirement.
    ("CSC 895", "Permission of the instructor and approval of Advancement to Candidacy (ATC) for the MS in CS and Culminating "
                "Experience (CE) forms by Graduate Studies. Advancement to candidacy and Proposal for Culminating Experience "
                "Requirement forms must be approved by the Graduate Division before registration.", all_(PERM, ATC)),
    ("CSC 898", "Permission of the instructor and graduate adviser and approval of Advancement to Candidacy (ATC) for the Master "
                "of Science in Computer Science and Culminating Experience (CE) forms by Graduate Studies. Advancement to "
                "Candidacy (ATC) and Proposal for Culminating Experience Requirement forms must be approved by the Graduate "
                "Division before registration.", all_(PERM, ADVISOR, ATC)),
    ("MATH 892", "Permission of the instructor and graduate adviser; and approval of Advancement to Candidacy (ATC) and "
                 "Culminating Experience (CE) forms by Graduate Studies. ATC and Proposal for Culminating Experience Requirement "
                 "forms must be approved by the Graduate Division before registration.", all_(PERM, ADVISOR, ATC)),
    ("MATH 896EXM", "Permission of the instructor, committee chair, and approval of Advancement to Candidacy (ATC) and "
                    "Culminating Experience (CE) forms by Graduate Studies. ATC and Proposal for Culminating Experience "
                    "Requirement forms must be approved by the Graduate Division before registration.", all_(PERM, CHAIR, ATC)),
    ("PHYS 895", "Advancement to Candidacy (ATC) and Proposal for Culminating Experience (PCE) forms must be approved by the "
                 "Division of Graduate Studies before registration.", ATC),
    ("CSC 699", "Permission of the department and instructor. An approved study proposal must be on file by the time of registration.",
     all_(DEPT, PERM, PROPOSAL)),
    ("CSC 408", "CSC 220* or CSC 311* or equivalent; a college-level biology course; or permission of the instructor.",
     any_(all_(any_(c("CSC 220"), c("CSC 311"), EQ), {"requirement": "a college-level biology course"}), PERM)),
    ("CSC 657", "Upper-division or graduate standing in a science program or permission of the instructor.",
     any_(all_(any_(UP, GRAD), r("science program")), PERM)),
    ("MATH 700", "Graduate Teaching Assistant status.", r("Graduate Teaching Assistant status")),
    ("CSC 805", "Restricted to graduate Computer Science students. Senior undergraduate Computer Science majors may enroll with "
                "the permission of the instructor.",
     any_(r("graduate Computer Science students"), all_(r("Senior undergraduate Computer Science majors"), PERM))),
    # Calculus I: high-school options, and a retake allowed after "C- or lower".
    ("MATH 226", "One of the following: MATH 198 or MATH 199 or equivalent with a grade of C or better; or MATH 226 or equivalent "
                 "with a grade of C- or lower; or high school pre-calculus with B or better; or high school calculus with a grade "
                 "of C or better.",
     any_(c("MATH 198", "C"), c("MATH 199", "C"), EQ, {"course": "MATH 226", "max_grade": "C-"},
          {"high_school": "pre-calculus", "min_grade": "B"}, {"high_school": "calculus", "min_grade": "C"})),
    ("PHYS 697", "PHYS 491; permission of the faculty adviser.", all_(c("PHYS 491"), ADVISOR)),
]


@pytest.mark.parametrize("code,text,expected", GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden(code, text, expected):
    got = parse_prereq(text)
    assert got["expr"] == expected
    assert got["status"] == "ok"


def test_empty_text_is_none():
    assert parse_prereq("") == {"expr": None, "status": "none", "needs_permission": False}


def test_needs_permission_flag():
    assert parse_prereq("Upper-division standing or permission of the instructor.")["needs_permission"] is True
    assert parse_prereq("CSC 230 with a grade of C or better.")["needs_permission"] is False


def test_unrecognized_fragment_is_kept_and_flagged_partial():
    got = parse_prereq("ENGR 213* (may be taken concurrently); a course in high school algebra and trigonometry.")
    assert got["status"] == "partial"
    assert got["expr"] == all_(c("ENGR 213", conc=True), {"unknown": "a course in"}, {"high_school": "algebra and trigonometry"})


@pytest.mark.parametrize("text", [
    "Final semester of a Physics degree program.",
    # "must" is a requirement, not advice: kept as unknown
    "Category I or II placement for QR/Math, or MATH 70 with a grade of C or better. Students with Category III or IV "
    "placement for QR/Math must concurrently enroll in MATH 111.",
    "Completed undergraduate major in physics.",
    "Formal commitment to write an MA thesis or expository paper.",
])
def test_admin_text_is_not_ok(text):
    assert parse_prereq(text)["status"] in ("partial", "unparsed")


def test_only_unknown_is_unparsed():
    assert parse_prereq("Formal commitment to write an MA thesis or expository paper.")["status"] == "unparsed"
