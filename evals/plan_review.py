"""Plan review over every scenario in tests/test_server.py at 12 / 15 / 18 / 18+summer units, on data/catalog.db.

Each cell: terms / lower bound (longest prereq chain or units / cap), flags (R = laid out on the roadmap, INVALID,
STOP, OVER, EMPTY), graduation term. Run after planner changes: uv run python evals/plan_review.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_server as scenarios  # noqa: E402  (the scenario profiles live with their tests)

from gatorpath import server  # noqa: E402

server.DB = ROOT / "data/catalog.db"
LOADS = [(12, False), (15, False), (18, False), (18, True)]

print(f"{'scenario':34}" + "".join(f"{str(u) + ('+summer' if su else ''):24}" for u, su in LOADS))
for name, profile in scenarios.SCENARIOS.items():
    cells = []
    for cap, summer in LOADS:
        out = server.build_plan(profile | {"max_units_per_term": cap, "include_summer": summer})
        sem, pace = out.get("semesters", []), out.get("pace", {})
        bound = max(pace.get("min_terms_by_prereqs", 0), pace.get("min_terms_by_units", 0))
        flags = "".join(f for f, bad in (("INVALID ", not out.get("check", {}).get("valid")),
                                         ("STOP ", any("Stopped at" in w for w in out.get("warnings", []))),
                                         ("OVER ", any(s["units"] > cap for s in sem)),
                                         ("EMPTY ", any(not s["courses"] for s in sem)),
                                         ("R", any(w.startswith("Laid out on the Bulletin") for w in out.get("warnings", []))))
                        if bad)
        cells.append(f"{len(sem):>2}/{bound:<2} {flags:8} {out.get('est_graduation_term') or '-':11}")
    print(f"{name:34}" + " ".join(cells))
