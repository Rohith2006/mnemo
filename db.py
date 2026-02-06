"""
SQLite connection + schema for mnemo's persistence layer.

One file, WAL mode, one table per bucket (facts/log_entries/tasks/habits/
journal/reminders) plus a `users` table for registry/prefs. store.py builds
UserStore/UserRegistry/ReminderStore on top of this.
"""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "mnemo.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    chat_id INTEGER,
    name TEXT NOT NULL DEFAULT '',
    tz TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    morning TEXT NOT NULL DEFAULT '08:00',
    evening TEXT NOT NULL DEFAULT '21:00',
    paused INTEGER NOT NULL DEFAULT 0,
    last_nudge_at TEXT,
    nudges_today INTEGER NOT NULL DEFAULT 0,
    nudge_day TEXT
);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    fact TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(user_id);

CREATE TABLE IF NOT EXISTS log_entries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    key TEXT NOT NULL,
    value TEXT,
    unit TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_user_at ON log_entries(user_id, at);
CREATE INDEX IF NOT EXISTS idx_log_user_key ON log_entries(user_id, key);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task TEXT NOT NULL,
    due TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created TEXT NOT NULL,
    done_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);

CREATE TABLE IF NOT EXISTS habits (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    streak INTEGER NOT NULL DEFAULT 1,
    best_streak INTEGER NOT NULL DEFAULT 1,
    last_done TEXT,
    cadence TEXT NOT NULL DEFAULT 'daily'
);
CREATE INDEX IF NOT EXISTS idx_habits_user ON habits(user_id);

CREATE TABLE IF NOT EXISTS journal (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    at TEXT NOT NULL,
    mood INTEGER,
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_journal_user_at ON journal(user_id, at);

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    task TEXT NOT NULL,
    fire_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_chat ON reminders(chat_id);
"""

_connections: dict[str, sqlite3.Connection] = {}


def get_db_path() -> Path:
    override = os.getenv("MNEMO_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


def get_conn(path: Path | None = None) -> sqlite3.Connection:
    """Return a cached, schema-initialized connection for `path` (default: env/data/mnemo.db)."""
    path = path or get_db_path()
    key = str(path)
    conn = _connections.get(key)
    if conn is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(key, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.commit()
        _connections[key] = conn
    return conn


def reset_connections() -> None:
    """Close and drop all cached connections. Tests use this between cases."""
    for conn in _connections.values():
        conn.close()
    _connections.clear()
