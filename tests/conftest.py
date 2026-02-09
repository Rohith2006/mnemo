import pytest

import db
import store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point every test at a fresh SQLite file and reset store's module-level
    singletons (registry, reminder_store, the get_store cache) onto it."""
    monkeypatch.setenv("MNEMO_DB_PATH", str(tmp_path / "test.db"))
    store.reset_state()
    yield
    db.reset_connections()
