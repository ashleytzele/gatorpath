import json
from pathlib import Path

import pytest

from gatorpath.db import load_catalog

ROOT = Path(__file__).parents[1]
DB = ROOT / "data/catalog.db"


@pytest.mark.skipif(not DB.exists(), reason="catalog.db not built (git-ignored)")
def test_eval_catalog_snapshot_matches_catalog_db():
    """evals/catalog-2026-27.json lets CI run audits without the PDF; it must not drift from the Bulletin."""
    snapshot = json.loads((ROOT / "evals/catalog-2026-27.json").read_text())
    assert load_catalog(DB, "2026-27", set(snapshot)) == snapshot


@pytest.mark.skipif(not DB.exists(), reason="catalog.db not built (git-ignored)")
def test_repeatable_wordings():
    rows = load_catalog(DB, "2026-27", {"CSC 699", "S ED 759", "COMM 852", "CSC 220"})
    assert {c: r["repeatable"] for c, r in rows.items()} == {
        "CSC 699": True,    # "May be repeated for a total of 6 units"
        "S ED 759": True,   # "May repeat when topics vary"
        "COMM 852": True,   # "Repeatable once for credit"
        "CSC 220": False,
    }
