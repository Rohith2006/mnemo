from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import db
import store


@pytest.fixture
def foreign_tz() -> str:
    """A timezone whose local date is NOT the server's local date right now.

    Kiritimati (UTC+14) and Midway (UTC-11) are 25 hours apart, so their local
    dates always differ from each other — whatever the server's date is, at
    least one of the two disagrees with it. Lets a test pin down "which day did
    this get recorded on" without depending on where the suite happens to run."""
    for name in ("Pacific/Kiritimati", "Pacific/Midway"):
        if datetime.now(ZoneInfo(name)).date() != date.today():
            return name
    raise AssertionError("unreachable: the two zones are 25h apart")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point every test at a fresh SQLite file and reset store's module-level
    singletons (registry, reminder_store, the get_store cache) onto it."""
    monkeypatch.setenv("MNEMO_DB_PATH", str(tmp_path / "test.db"))
    store.reset_state()
    yield
    db.reset_connections()
