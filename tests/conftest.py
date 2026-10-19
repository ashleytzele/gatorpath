"""Pin the server's "today" so tests that plan fixed terms (2027-spring, …) don't age."""

from datetime import date

import pytest

from gatorpath import server


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(server, "today", lambda: date(2026, 10, 18))
