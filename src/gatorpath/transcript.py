"""Local unofficial transcript PDF (Student Center, SSR_TSRPT) -> course rows (ARCHITECTURE §7.3).

Only course code, grade, units and term leave this module. Names, IDs, birthdates, schools and the raw text are never
returned, logged or stored (golden rule 5); a row it can't read is reported by its position, never its text.
"""

import re
import subprocess
from pathlib import Path

SEASON = {"FA": "fall", "SP": "spring", "SU": "summer"}  # ponytail: "SU" not yet seen on a real transcript
TERM_LINE = re.compile(r"\s*([A-Z]{2})(\d{4})\s*")  # a line that is only "FA2025"
SUBJECT = r"[A-Z]{1,5}(?: [A-Z]{1,3})?"  # 'CSC', 'I R'
ROW = re.compile(rf"({SUBJECT})\s{{2,}}(\d{{3}}[A-Z]{{0,3}})\s{{2,}}.*?\s{{2,}}(\d+\.\d\d)\s+(\d+\.\d\d)"
                 rf"(?:\s+([A-Z][A-Z+-]{{0,2}}))?\s+(\d+\.\d\d)\s*")  # code, description, units, earned, grade?, points
LOOKS_LIKE_ROW = re.compile(rf"{SUBJECT}\s{{2,}}\d{{3}}")
TRANSFER = re.compile(r"Transfer Totals:\s+(\d+\.\d+)\s+(\d+\.\d+)")


def parse(text: str) -> dict:
    """{completed: [{code, grade, units, term}], in_progress: [codes], transfer_units, warnings}."""
    completed, in_progress, warnings = [], [], []
    transfer_units, term, label, n = 0.0, None, None, 0
    for line in text.splitlines():
        if m := TERM_LINE.fullmatch(line):
            label, n = m[1] + m[2], 0
            term = f"{m[2]}-{SEASON[m[1]]}" if m[1] in SEASON else None
            if term is None:
                warnings.append(f"Term {label}: not a fall, spring or summer code GatorPath knows; its courses are kept "
                                "without a term. Check them against your DPR")
            continue
        if m := TRANSFER.search(line):
            transfer_units += float(m[2])  # earned
            continue
        if label is None or not LOOKS_LIKE_ROW.match(line := line.strip()):
            continue
        n += 1
        if not (m := ROW.fullmatch(line)):
            warnings.append(f"Term {label}, course row {n}: not in the expected layout, so it was left out; add it by hand")
            continue
        code, units, earned, grade = f"{m[1]} {m[2]}", float(m[3]), float(m[4]), m[5]
        if grade is None and earned == 0:
            in_progress.append(code)
        elif grade is None:
            warnings.append(f"Term {label}, course row {n}: units earned but no grade; left out, add it by hand")
        else:
            completed.append({"code": code, "grade": grade, "units": units} | ({"term": term} if term else {}))
    if transfer_units:
        warnings.append(f"{transfer_units:g} transfer units: the transcript lists totals only, not which courses or "
                        "requirements they meet. Give those from your DPR (ge_done, or transfer: true rows)")
    if not completed and not in_progress:
        return {"error": "unrecognized_transcript_format",
                "warnings": warnings + ["No course rows found: is this the SF State unofficial transcript? You can type "
                                        "the courses instead"]}
    return {"completed": completed, "in_progress": in_progress, "transfer_units": transfer_units, "warnings": warnings}


def read_pdf(path: Path) -> str:
    """pdftotext -layout to memory; nothing written to disk."""
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
