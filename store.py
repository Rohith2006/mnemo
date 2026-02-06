"""
Persistence + tracking layer for the proactive PA.

Backed by SQLite (see db.py) instead of a JSON blob. Three repositories:

  • UserStore     — per-user structured memory (profile, log, tasks, habits, journal)
  • UserRegistry  — who the bot knows + per-user prefs (chat_id, tz, digest times, pause)
  • ReminderStore — pending NLP reminders

The `log` bucket is deliberately schema-free on the Python side: ANY
{category, key, value, unit} data point can be tracked, so the assistant is
extensible to anything — weight, water, sleep, money spent, books read,
study hours, whatever shows up.
"""

import sqlite3
import uuid
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import db

DEFAULT_TZ = "Asia/Kolkata"


def _sid() -> str:
    return uuid.uuid4().hex[:8]


def _now_iso() -> str:
    return datetime.now().isoformat()


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _value_to_text(value):
    return None if value is None else str(value)


def _log_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "category": r["category"], "key": r["key"],
        "value": r["value"], "unit": r["unit"], "note": r["note"], "at": r["at"],
    }


def _task_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "task": r["task"], "due": r["due"], "status": r["status"],
        "created": r["created"], "done_at": r["done_at"],
    }


def _habit_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "name": r["name"], "streak": r["streak"],
        "best_streak": r["best_streak"], "last_done": r["last_done"], "cadence": r["cadence"],
    }


def _user_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "user_id": r["user_id"], "chat_id": r["chat_id"], "name": r["name"], "tz": r["tz"],
        "morning": r["morning"], "evening": r["evening"], "paused": bool(r["paused"]),
        "last_nudge_at": r["last_nudge_at"], "nudges_today": r["nudges_today"],
        "nudge_day": r["nudge_day"],
    }


# ── Per-user structured memory ──────────────────────────────────────────────
class UserStore:
    """Structured, trend-aware memory for one user."""

    def __init__(self, user_id: str, conn: sqlite3.Connection | None = None):
        self.user_id = str(user_id)
        self.conn = conn or db.get_conn()

    # ── profile facts ──
    def add_facts(self, facts: list[str]) -> list[str]:
        existing = {
            r["fact"].lower() for r in
            self.conn.execute("SELECT fact FROM facts WHERE user_id=?", (self.user_id,))
        }
        added = []
        now = _now_iso()
        for fact in facts:
            fact = (fact or "").strip()
            if len(fact) < 3 or fact.lower() in existing:
                continue
            self.conn.execute(
                "INSERT INTO facts (id, user_id, fact, at) VALUES (?,?,?,?)",
                (_sid(), self.user_id, fact, now),
            )
            existing.add(fact.lower())
            added.append(fact)
        if added:
            self.conn.commit()
        return added

    def facts(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT fact FROM facts WHERE user_id=? ORDER BY rowid", (self.user_id,)
        )
        return [r["fact"] for r in rows]

    # ── generic log (extensible to anything) ──
    def add_log(self, entries: list[dict]) -> list[dict]:
        added = []
        now = _now_iso()
        for e in entries:
            key = (e.get("key") or "").strip()
            if not key:
                continue
            entry = {
                "id": _sid(),
                "category": (e.get("category") or "general").strip(),
                "key": key,
                "value": e.get("value"),
                "unit": (e.get("unit") or "").strip(),
                "note": (e.get("note") or "").strip(),
                "at": now,
            }
            self.conn.execute(
                "INSERT INTO log_entries (id, user_id, category, key, value, unit, note, at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (entry["id"], self.user_id, entry["category"], entry["key"],
                 _value_to_text(entry["value"]), entry["unit"], entry["note"], entry["at"]),
            )
            added.append(entry)
        if added:
            self.conn.commit()
        return added

    def recent_log(self, days: int = 7, category: str | None = None) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        if category:
            rows = self.conn.execute(
                "SELECT * FROM log_entries WHERE user_id=? AND category=? AND at>=? ORDER BY rowid",
                (self.user_id, category, cutoff),
            )
        else:
            rows = self.conn.execute(
                "SELECT * FROM log_entries WHERE user_id=? AND at>=? ORDER BY rowid",
                (self.user_id, cutoff),
            )
        return [_log_row_to_dict(r) for r in rows]

    def metric_series(self, key: str) -> list[tuple[str, float]]:
        """Time-ordered numeric points for one key — for trends."""
        rows = self.conn.execute(
            "SELECT at, value FROM log_entries WHERE user_id=? AND key=? ORDER BY at",
            (self.user_id, key),
        )
        pts = []
        for r in rows:
            try:
                pts.append((r["at"], float(r["value"])))
            except (TypeError, ValueError):
                continue
        return pts

    def numeric_keys(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT key, value FROM log_entries WHERE user_id=? ORDER BY rowid", (self.user_id,)
        )
        keys = []
        for r in rows:
            try:
                float(r["value"])
            except (TypeError, ValueError):
                continue
            if r["key"] not in keys:
                keys.append(r["key"])
        return keys

    # ── tasks ──
    def add_tasks(self, entries: list[dict]) -> list[dict]:
        added = []
        open_lower = {t["task"].lower() for t in self.open_tasks()}
        now = _now_iso()
        for e in entries:
            task = (e.get("task") or "").strip()
            if not task or task.lower() in open_lower:
                continue
            t = {
                "id": _sid(), "task": task, "due": e.get("due"),
                "status": "open", "created": now, "done_at": None,
            }
            self.conn.execute(
                "INSERT INTO tasks (id, user_id, task, due, status, created, done_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (t["id"], self.user_id, t["task"], t["due"], t["status"], t["created"], t["done_at"]),
            )
            open_lower.add(task.lower())
            added.append(t)
        if added:
            self.conn.commit()
        return added

    def open_tasks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE user_id=? AND status='open' ORDER BY rowid", (self.user_id,)
        )
        return [_task_row_to_dict(r) for r in rows]

    def complete_tasks(self, matches: list[str]) -> list[dict]:
        done = []
        now = _now_iso()
        for m in matches:
            m = (m or "").strip().lower()
            if not m:
                continue
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE user_id=? AND status='open' ORDER BY rowid",
                (self.user_id,),
            ).fetchall()
            for r in rows:
                task_lower = r["task"].lower()
                if m in task_lower or task_lower in m:
                    self.conn.execute(
                        "UPDATE tasks SET status='done', done_at=? WHERE id=?", (now, r["id"])
                    )
                    d = _task_row_to_dict(r)
                    d["status"] = "done"
                    d["done_at"] = now
                    done.append(d)
                    break
        if done:
            self.conn.commit()
        return done

    def tasks_due_within(self, hours: int, tz: ZoneInfo) -> list[dict]:
        now = datetime.now(tz)
        horizon = now + timedelta(hours=hours)
        out = []
        for t in self.open_tasks():
            if not t.get("due"):
                continue
            try:
                due = datetime.fromisoformat(t["due"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=tz)
            except ValueError:
                continue
            if now <= due <= horizon:
                out.append({**t, "due_dt": due})
        return sorted(out, key=lambda x: x["due_dt"])

    def overdue_tasks(self, tz: ZoneInfo) -> list[dict]:
        now = datetime.now(tz)
        out = []
        for t in self.open_tasks():
            if not t.get("due"):
                continue
            try:
                due = datetime.fromisoformat(t["due"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=tz)
            except ValueError:
                continue
            if due < now:
                out.append({**t, "due_dt": due})
        return sorted(out, key=lambda x: x["due_dt"])

    # ── habits + streaks ──
    def _find_habit(self, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM habits WHERE user_id=? AND lower(name)=?",
            (self.user_id, name.lower()),
        ).fetchone()
        return _habit_row_to_dict(row) if row else None

    def log_habit(self, name: str, on: date | None = None) -> dict:
        """Mark a habit done; maintain the streak. Returns the habit + status."""
        name = (name or "").strip()
        if not name:
            return {}
        today = on or date.today()
        h = self._find_habit(name)
        if h is None:
            hid = _sid()
            self.conn.execute(
                "INSERT INTO habits (id, user_id, name, streak, best_streak, last_done, cadence) "
                "VALUES (?,?,?,1,1,?,'daily')",
                (hid, self.user_id, name, today.isoformat()),
            )
            self.conn.commit()
            return {
                "id": hid, "name": name, "streak": 1, "best_streak": 1,
                "last_done": today.isoformat(), "cadence": "daily", "_status": "started",
            }

        last = _parse_date(h.get("last_done"))
        if last == today:
            streak, status = h["streak"], "already"
        elif last == today - timedelta(days=1):
            streak, status = h["streak"] + 1, "continued"
        else:
            streak, status = 1, "reset"
        best = max(h.get("best_streak", 0), streak)
        self.conn.execute(
            "UPDATE habits SET streak=?, best_streak=?, last_done=? WHERE id=?",
            (streak, best, today.isoformat(), h["id"]),
        )
        self.conn.commit()
        h.update({"streak": streak, "best_streak": best, "last_done": today.isoformat(), "_status": status})
        return h

    def active_habits(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM habits WHERE user_id=? ORDER BY rowid", (self.user_id,)
        )
        return [_habit_row_to_dict(r) for r in rows]

    def habits_at_risk(self, tz: ZoneInfo) -> list[dict]:
        """Daily habits with a live streak that hasn't been done today yet."""
        today = datetime.now(tz).date()
        out = []
        for h in self.active_habits():
            if h.get("cadence", "daily") != "daily":
                continue
            last = _parse_date(h.get("last_done"))
            if last is None:
                continue
            if last == today - timedelta(days=1) and h.get("streak", 0) >= 1:
                out.append(h)
        return out

    # ── journal / mood ──
    def add_journal(self, mood: int | None, note: str = "") -> dict:
        entry = {"id": _sid(), "at": _now_iso(), "mood": mood, "note": (note or "").strip()}
        self.conn.execute(
            "INSERT INTO journal (id, user_id, at, mood, note) VALUES (?,?,?,?,?)",
            (entry["id"], self.user_id, entry["at"], entry["mood"], entry["note"]),
        )
        self.conn.commit()
        return entry

    def recent_mood(self, days: int = 14) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            "SELECT * FROM journal WHERE user_id=? AND mood IS NOT NULL AND at>=? ORDER BY rowid",
            (self.user_id, cutoff),
        )
        return [{"id": r["id"], "at": r["at"], "mood": r["mood"], "note": r["note"]} for r in rows]

    # ── views for prompts / dashboards ──
    def summary(self) -> str:
        """Compact snapshot injected into the chat system prompt."""
        lines = []
        if self.facts():
            lines.append("PROFILE:")
            lines += [f"  - {f}" for f in self.facts()]

        habits = self.active_habits()
        if habits:
            lines.append("HABITS:")
            for h in habits:
                lines.append(f"  - {h['name']}: streak {h.get('streak', 0)} (best {h.get('best_streak', 0)}), last {h.get('last_done')}")

        open_t = self.open_tasks()
        if open_t:
            lines.append("OPEN TASKS:")
            for t in open_t:
                due = f" (due {t['due']})" if t.get("due") else ""
                lines.append(f"  - {t['task']}{due}")

        recent = self.recent_log(days=7)
        if recent:
            lines.append("RECENT LOG (7d):")
            for e in recent[-12:]:
                v = e.get("value")
                unit = f" {e['unit']}" if e.get("unit") else ""
                vstr = f": {v}{unit}" if v is not None else ""
                lines.append(f"  - [{e['category']}] {e['key']}{vstr}")

        mood = self.recent_mood(7)
        if mood:
            avg = sum(m["mood"] for m in mood) / len(mood)
            lines.append(f"MOOD (7d avg): {avg:.1f}/10 over {len(mood)} entries")

        return "\n".join(lines) if lines else "(Nothing tracked yet — this is a new user.)"

    def trends(self) -> list[str]:
        """Human-readable trend lines for numeric metrics."""
        out = []
        for key in self.numeric_keys():
            series = self.metric_series(key)
            if len(series) < 2:
                continue
            first, last = series[0][1], series[-1][1]
            delta = last - first
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "▬")
            out.append(f"{key}: {first:g} → {last:g} {arrow} ({delta:+g}) over {len(series)} entries")
        return out

    # ── reset ──
    def forget_all(self) -> None:
        """Wipe every bucket for this user (the /forget command)."""
        for table in ("facts", "log_entries", "tasks", "habits", "journal"):
            self.conn.execute(f"DELETE FROM {table} WHERE user_id=?", (self.user_id,))
        self.conn.commit()


_stores: dict[str, UserStore] = {}


def get_store(user_id: str) -> UserStore:
    user_id = str(user_id)
    if user_id not in _stores:
        _stores[user_id] = UserStore(user_id)
    return _stores[user_id]


# ── Who the bot knows + per-user prefs ──────────────────────────────────────
class UserRegistry:
    """
    Tracks every user the bot has met so proactive jobs know where to send.
    Per-user prefs: timezone, digest times, pause flag, last nudge timestamp.
    """

    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn or db.get_conn()

    def register(self, user_id: str, chat_id: int, name: str = "") -> dict:
        user_id = str(user_id)
        self.conn.execute(
            "INSERT INTO users (user_id, chat_id, name, tz, morning, evening, paused, "
            "last_nudge_at, nudges_today, nudge_day) VALUES (?,?,?,?,?,?,0,NULL,0,NULL) "
            "ON CONFLICT(user_id) DO UPDATE SET chat_id=excluded.chat_id, "
            "name=CASE WHEN excluded.name != '' THEN excluded.name ELSE users.name END",
            (user_id, chat_id, name, DEFAULT_TZ, "08:00", "21:00"),
        )
        self.conn.commit()
        return self.get(user_id)

    def get(self, user_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE user_id=?", (str(user_id),)
        ).fetchone()
        return _user_row_to_dict(row) if row else None

    def all(self) -> dict[str, dict]:
        rows = self.conn.execute("SELECT * FROM users ORDER BY rowid").fetchall()
        return {r["user_id"]: _user_row_to_dict(r) for r in rows}

    def set(self, user_id: str, **fields):
        user_id = str(user_id)
        if not fields or self.get(user_id) is None:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE users SET {cols} WHERE user_id=?", (*fields.values(), user_id))
        self.conn.commit()

    def tz(self, user_id: str) -> ZoneInfo:
        u = self.get(user_id)
        return ZoneInfo(u["tz"] if u else DEFAULT_TZ)

    # nudge rate-limiting ("balanced": ≤2/day, ≥4h apart)
    def can_nudge(self, user_id: str, max_per_day: int = 2, min_gap_h: int = 4) -> bool:
        u = self.get(user_id)
        if not u or u.get("paused"):
            return False
        tz = self.tz(user_id)
        today = datetime.now(tz).date().isoformat()
        if u.get("nudge_day") != today:
            return True
        if u.get("nudges_today", 0) >= max_per_day:
            return False
        last = u.get("last_nudge_at")
        if last:
            try:
                if datetime.now(tz) - datetime.fromisoformat(last) < timedelta(hours=min_gap_h):
                    return False
            except ValueError:
                pass
        return True

    def record_nudge(self, user_id: str):
        u = self.get(user_id)
        if not u:
            return
        tz = self.tz(user_id)
        today = datetime.now(tz).date().isoformat()
        nudges_today = 1 if u.get("nudge_day") != today else u.get("nudges_today", 0) + 1
        self.conn.execute(
            "UPDATE users SET nudge_day=?, nudges_today=?, last_nudge_at=? WHERE user_id=?",
            (today, nudges_today, datetime.now(tz).isoformat(), str(user_id)),
        )
        self.conn.commit()


registry = UserRegistry()


# ── Reminder store (NLP reminders) ──────────────────────────────────────────
class ReminderStore:
    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn or db.get_conn()

    def add(self, chat_id: int, task: str, fire_at: datetime) -> str:
        rid = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO reminders (id, chat_id, task, fire_at) VALUES (?,?,?,?)",
            (rid, chat_id, task, fire_at.isoformat()),
        )
        self.conn.commit()
        return rid

    def remove(self, rid: str):
        self.conn.execute("DELETE FROM reminders WHERE id=?", (rid,))
        self.conn.commit()

    def get_pending(self) -> list[dict]:
        now = datetime.now().astimezone()
        pending, expired = [], []
        for r in self.conn.execute("SELECT * FROM reminders").fetchall():
            fire_at = datetime.fromisoformat(r["fire_at"])
            if fire_at > now:
                pending.append({"id": r["id"], "chat_id": r["chat_id"], "task": r["task"],
                                 "fire_at": r["fire_at"], "fire_at_dt": fire_at})
            else:
                expired.append(r["id"])
        for rid in expired:
            self.remove(rid)
        return pending

    def get_all_for_chat(self, chat_id: int) -> list[dict]:
        now = datetime.now().astimezone()
        result = []
        for r in self.conn.execute(
            "SELECT * FROM reminders WHERE chat_id=?", (chat_id,)
        ).fetchall():
            fire_at = datetime.fromisoformat(r["fire_at"])
            if fire_at > now:
                result.append({"id": r["id"], "chat_id": r["chat_id"], "task": r["task"],
                                "fire_at": r["fire_at"], "fire_at_dt": fire_at})
        return sorted(result, key=lambda x: x["fire_at_dt"])


reminder_store = ReminderStore()


def reset_state() -> None:
    """Testing hook: drop cached stores/registry/reminder_store and close DB
    connections, so a freshly-set MNEMO_DB_PATH takes effect on next access."""
    global registry, reminder_store
    db.reset_connections()
    _stores.clear()
    registry = UserRegistry()
    reminder_store = ReminderStore()
