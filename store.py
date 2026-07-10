"""
Persistence + tracking layer for mnemo.

Backed by SQLite (see db.py) instead of a JSON blob. Three repositories:

  • UserStore     — per-user structured memory (profile, log, tasks, habits,
                     journal, cached digests)
  • UserRegistry  — accounts (email/password hash, tz)
  • ReminderStore — pending NLP reminders, scoped per user

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


def _derive_title(message: str) -> str:
    """First-message-derived conversation title: collapse whitespace, truncate
    to ~50 chars on a word boundary with an ellipsis, or a hard cut if there's
    no space to break on."""
    message = " ".join(message.split())
    if len(message) <= 50:
        return message
    cut = message[:50]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return f"{cut}…"


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


def _conversation_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "title": r["title"],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def _message_row_to_dict(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "role": r["role"], "content": r["content"], "created_at": r["created_at"]}


def _user_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "user_id": r["user_id"], "email": r["email"], "password_hash": r["password_hash"],
        "name": r["name"], "tz": r["tz"], "created_at": r["created_at"],
        "push_enabled": bool(r["push_enabled"]),
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
            self.conn.execute(
                "SELECT fact FROM facts WHERE user_id=? AND active=1", (self.user_id,)
            )
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
            "SELECT fact FROM facts WHERE user_id=? AND active=1 ORDER BY rowid",
            (self.user_id,),
        )
        return [r["fact"] for r in rows]

    def _match_active_fact(self, needle: str) -> sqlite3.Row | None:
        """Find one active fact by loose substring, the way complete_tasks matches tasks."""
        needle = (needle or "").strip().lower()
        if not needle:
            return None
        rows = self.conn.execute(
            "SELECT * FROM facts WHERE user_id=? AND active=1 ORDER BY rowid",
            (self.user_id,),
        ).fetchall()
        for r in rows:
            fact_lower = r["fact"].lower()
            if needle in fact_lower or fact_lower in needle:
                return r
        return None

    def update_fact(self, old_match: str, new_fact: str) -> str | None:
        """
        Supersede the fact matching `old_match` with `new_fact`.

        The old row is deactivated rather than deleted, so a profile keeps its
        history ("lived in Bengaluru" stays recoverable after moving to Dubai).
        Returns the new fact text, or None if nothing matched / the text is unusable.
        """
        new_fact = (new_fact or "").strip()
        if len(new_fact) < 3:
            return None
        row = self._match_active_fact(old_match)
        if row is None:
            return None
        now = _now_iso()
        self.conn.execute(
            "UPDATE facts SET active=0, updated_at=? WHERE id=?", (now, row["id"])
        )
        self.conn.execute(
            "INSERT INTO facts (id, user_id, fact, at, updated_at, active) VALUES (?,?,?,?,?,1)",
            (_sid(), self.user_id, new_fact, row["at"], now),
        )
        self.conn.commit()
        return new_fact

    def remove_facts(self, matches: list[str]) -> list[str]:
        """Deactivate facts the user has contradicted. Returns the texts removed."""
        removed = []
        now = _now_iso()
        for m in matches:
            row = self._match_active_fact(m)
            if row is None:
                continue
            self.conn.execute(
                "UPDATE facts SET active=0, updated_at=? WHERE id=?", (now, row["id"])
            )
            removed.append(row["fact"])
        if removed:
            self.conn.commit()
        return removed

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

    def completed_tasks(self, limit: int = 30) -> list[dict]:
        """Most-recently-completed first — the closed-by-default "Completed" log."""
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE user_id=? AND status='done' ORDER BY done_at DESC LIMIT ?",
            (self.user_id, limit),
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
        today = now.date()
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
            # A date-only due (no time given) only counts as overdue once that whole
            # day has passed — not from midnight of the due day itself, which would
            # flag a task due "today" as overdue for most of today.
            has_time = "T" in t["due"]
            is_overdue = due < now if has_time else due.date() < today
            if is_overdue:
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

    # ── digest cache (one generated digest per user/kind/day) ──
    def get_cached_digest(self, kind: str, date_str: str) -> str | None:
        row = self.conn.execute(
            "SELECT text FROM digests WHERE user_id=? AND kind=? AND date=?",
            (self.user_id, kind, date_str),
        ).fetchone()
        return row["text"] if row else None

    def save_digest(self, kind: str, date_str: str, text: str) -> None:
        self.conn.execute(
            "INSERT INTO digests (id, user_id, kind, date, text, created_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(user_id, kind, date) DO UPDATE SET text=excluded.text",
            (_sid(), self.user_id, kind, date_str, text, _now_iso()),
        )
        self.conn.commit()

    def invalidate_today_digests(self, tz: ZoneInfo) -> None:
        """Drop today's cached digests so the next fetch regenerates them. Called
        after any mutation that could make a cached digest's claims stale (a new
        task/fact/log entry, a completed task, a logged habit) — otherwise a
        digest fetched once early in the day (even a near-empty first one) would
        keep showing that same stale text regardless of everything captured
        afterward, since nothing else ever expires the cache."""
        today = datetime.now(tz).date().isoformat()
        self.conn.execute("DELETE FROM digests WHERE user_id=? AND date=?", (self.user_id, today))
        self.conn.commit()

    # ── push notifications ──
    def add_push_token(self, token: str, platform: str) -> None:
        # ON CONFLICT(token): the same physical token can re-register under a
        # different user_id (logout/login as someone else on the same device)
        # — ownership must move to the new account, not duplicate or stick
        # with the old one.
        self.conn.execute(
            "INSERT INTO push_tokens (id, user_id, token, platform, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(token) DO UPDATE SET user_id=excluded.user_id, platform=excluded.platform, "
            "created_at=excluded.created_at",
            (_sid(), self.user_id, token, platform, _now_iso()),
        )
        self.conn.commit()

    def push_tokens(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT token FROM push_tokens WHERE user_id=?", (self.user_id,)
        )
        return [r["token"] for r in rows]

    def remove_push_token(self, token: str) -> None:
        self.conn.execute(
            "DELETE FROM push_tokens WHERE user_id=? AND token=?", (self.user_id, token)
        )
        self.conn.commit()

    def has_pushed(self, kind: str, ref_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM push_log WHERE user_id=? AND kind=? AND ref_id=?",
            (self.user_id, kind, ref_id),
        ).fetchone()
        return row is not None

    def log_push_sent(self, kind: str, ref_id: str) -> None:
        self.conn.execute(
            "INSERT INTO push_log (id, user_id, kind, ref_id, sent_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, kind, ref_id) DO NOTHING",
            (_sid(), self.user_id, kind, ref_id, _now_iso()),
        )
        self.conn.commit()

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
        conv_ids = [r["id"] for r in self.conn.execute(
            "SELECT id FROM conversations WHERE user_id=?", (self.user_id,)
        )]
        if conv_ids:
            placeholders = ",".join("?" * len(conv_ids))
            self.conn.execute(
                f"DELETE FROM chat_messages WHERE conversation_id IN ({placeholders})", conv_ids
            )
        for table in ("facts", "log_entries", "tasks", "habits", "journal", "digests", "conversations"):
            self.conn.execute(f"DELETE FROM {table} WHERE user_id=?", (self.user_id,))
        self.conn.commit()

    def complete_task_by_id(self, task_id: str) -> dict | None:
        """Mark one open task done by id — for a direct tap-to-complete UI action."""
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE user_id=? AND id=? AND status='open'",
            (self.user_id, task_id),
        ).fetchone()
        if not row:
            return None
        now = _now_iso()
        self.conn.execute("UPDATE tasks SET status='done', done_at=? WHERE id=?", (now, task_id))
        self.conn.commit()
        d = _task_row_to_dict(row)
        d["status"], d["done_at"] = "done", now
        return d

    def reopen_task(self, task_id: str) -> dict | None:
        """Undo a completion — moves a done task back to open, for the Completed log's undo action."""
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE user_id=? AND id=? AND status='done'",
            (self.user_id, task_id),
        ).fetchone()
        if not row:
            return None
        self.conn.execute("UPDATE tasks SET status='open', done_at=NULL WHERE id=?", (task_id,))
        self.conn.commit()
        d = _task_row_to_dict(row)
        d["status"], d["done_at"] = "open", None
        return d

    # ── conversations / chat messages ──
    def create_conversation(self, first_message: str) -> dict:
        conv_id = _sid()
        now = _now_iso()
        title = _derive_title(first_message)
        self.conn.execute(
            "INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
            (conv_id, self.user_id, title, now, now),
        )
        self.conn.commit()
        return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}

    def list_conversations(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC", (self.user_id,)
        )
        return [_conversation_row_to_dict(r) for r in rows]

    def _owns_conversation(self, conversation_id: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM conversations WHERE id=? AND user_id=?", (conversation_id, self.user_id)
        ).fetchone() is not None

    def conversation_messages(self, conversation_id: str) -> list[dict] | None:
        """None means "no such conversation for this user" — distinct from an
        empty list, which shouldn't normally happen since a conversation only
        exists once its first message has been added."""
        if not self._owns_conversation(conversation_id):
            return None
        rows = self.conn.execute(
            "SELECT * FROM chat_messages WHERE conversation_id=? ORDER BY created_at",
            (conversation_id,),
        )
        return [_message_row_to_dict(r) for r in rows]

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        # Matches complete_task_by_id/reopen_task's pattern: check ownership
        # here rather than trusting the caller to have checked separately.
        if not self._owns_conversation(conversation_id):
            return
        now = _now_iso()
        self.conn.execute(
            "INSERT INTO chat_messages (id, conversation_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (_sid(), conversation_id, role, content, now),
        )
        self.conn.execute(
            "UPDATE conversations SET updated_at=? WHERE id=? AND user_id=?",
            (now, conversation_id, self.user_id),
        )
        self.conn.commit()

    def rename_conversation(self, conversation_id: str, title: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE id=? AND user_id=?", (conversation_id, self.user_id)
        ).fetchone()
        if not row:
            return None
        self.conn.execute("UPDATE conversations SET title=? WHERE id=?", (title, conversation_id))
        self.conn.commit()
        d = _conversation_row_to_dict(row)
        d["title"] = title
        return d

    def delete_conversation(self, conversation_id: str) -> bool:
        if not self._owns_conversation(conversation_id):
            return False
        self.conn.execute("DELETE FROM chat_messages WHERE conversation_id=?", (conversation_id,))
        self.conn.execute("DELETE FROM conversations WHERE id=? AND user_id=?",
                           (conversation_id, self.user_id))
        self.conn.commit()
        return True


_stores: dict[str, UserStore] = {}


def get_store(user_id: str) -> UserStore:
    user_id = str(user_id)
    if user_id not in _stores:
        _stores[user_id] = UserStore(user_id)
    return _stores[user_id]


# ── Accounts ─────────────────────────────────────────────────────────────────
class UserRegistry:
    """Accounts: email/password hash + prefs (tz). Password hashing/JWT issuance
    live in the API layer — this just persists whatever hash it's given."""

    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn or db.get_conn()

    def create(self, email: str, password_hash: str, name: str = "", tz: str = DEFAULT_TZ) -> dict:
        """Create a new account. Raises ValueError if the email is already taken."""
        if self.get_by_email(email):
            raise ValueError(f"email already registered: {email}")
        user_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO users (user_id, email, password_hash, name, tz, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, email.strip().lower(), password_hash, name, tz, _now_iso()),
        )
        self.conn.commit()
        return self.get(user_id)

    def get(self, user_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE user_id=?", (str(user_id),)
        ).fetchone()
        return _user_row_to_dict(row) if row else None

    def get_by_email(self, email: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE email=?", (email.strip().lower(),)
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


registry = UserRegistry()


# ── Reminder store (NLP reminders) ──────────────────────────────────────────
class ReminderStore:
    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn or db.get_conn()

    def add(self, user_id: str, task: str, fire_at: datetime) -> str:
        rid = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO reminders (id, user_id, task, fire_at) VALUES (?,?,?,?)",
            (rid, str(user_id), task, fire_at.isoformat()),
        )
        self.conn.commit()
        return rid

    def remove(self, rid: str):
        self.conn.execute("DELETE FROM reminders WHERE id=?", (rid,))
        self.conn.commit()

    def remove_for_user(self, user_id: str):
        """Drop every reminder for one user — the reminders half of /forget."""
        self.conn.execute("DELETE FROM reminders WHERE user_id=?", (str(user_id),))
        self.conn.commit()

    def get_pending(self) -> list[dict]:
        now = datetime.now().astimezone()
        pending, expired = [], []
        for r in self.conn.execute("SELECT * FROM reminders").fetchall():
            fire_at = datetime.fromisoformat(r["fire_at"])
            if fire_at > now:
                pending.append({"id": r["id"], "user_id": r["user_id"], "task": r["task"],
                                 "fire_at": r["fire_at"], "fire_at_dt": fire_at})
            else:
                expired.append(r["id"])
        for rid in expired:
            self.remove(rid)
        return pending

    def get_all_for_user(self, user_id: str) -> list[dict]:
        now = datetime.now().astimezone()
        result = []
        for r in self.conn.execute(
            "SELECT * FROM reminders WHERE user_id=?", (str(user_id),)
        ).fetchall():
            fire_at = datetime.fromisoformat(r["fire_at"])
            if fire_at > now:
                result.append({"id": r["id"], "user_id": r["user_id"], "task": r["task"],
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
