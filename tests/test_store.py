"""Tests for store.py — the SQLite-backed persistence layer. No network calls."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import store


# ── facts ────────────────────────────────────────────────────────────────────
def test_add_facts_dedupes_case_insensitively():
    s = store.get_store("u1")
    added = s.add_facts(["Lives in Bengaluru", "lives in bengaluru", "CS student"])
    assert added == ["Lives in Bengaluru", "CS student"]
    assert s.facts() == ["Lives in Bengaluru", "CS student"]


def test_add_facts_skips_blank_and_too_short():
    s = store.get_store("u1")
    assert s.add_facts(["", "  ", "hi"]) == []
    assert s.facts() == []


# ── log / trends ─────────────────────────────────────────────────────────────
def test_recent_log_respects_cutoff():
    s = store.get_store("u1")
    s.add_log([{"category": "health", "key": "weight", "value": 80, "unit": "kg"}])
    entry_id = s.recent_log(days=999)[0]["id"]
    old_at = (datetime.now() - timedelta(days=10)).isoformat()
    s.conn.execute("UPDATE log_entries SET at=? WHERE id=?", (old_at, entry_id))
    s.conn.commit()
    assert s.recent_log(days=7) == []
    assert len(s.recent_log(days=30)) == 1


def test_recent_log_filters_by_category():
    s = store.get_store("u1")
    s.add_log([{"category": "health", "key": "weight", "value": 80}])
    s.add_log([{"category": "money", "key": "spent", "value": 500}])
    assert [e["key"] for e in s.recent_log(category="health")] == ["weight"]


def test_metric_series_and_numeric_keys_skip_non_numeric():
    s = store.get_store("u1")
    s.add_log([{"key": "weight", "value": 82}])
    s.add_log([{"key": "weight", "value": 75}])
    s.add_log([{"key": "mood_word", "value": "great"}])
    assert s.numeric_keys() == ["weight"]
    assert [v for _, v in s.metric_series("weight")] == [82.0, 75.0]


def test_trends_show_direction_arrows():
    s = store.get_store("u1")
    s.add_log([{"key": "weight", "value": 82}])
    s.add_log([{"key": "weight", "value": 75}])
    s.add_log([{"key": "reps", "value": 10}])
    s.add_log([{"key": "reps", "value": 15}])
    trends = {t.split(":")[0]: t for t in s.trends()}
    assert "▼" in trends["weight"]
    assert "▲" in trends["reps"]


# ── tasks ────────────────────────────────────────────────────────────────────
def test_add_tasks_dedupes_open_tasks_case_insensitively():
    s = store.get_store("u1")
    s.add_tasks([{"task": "Submit report"}])
    s.add_tasks([{"task": "submit report"}])
    assert len(s.open_tasks()) == 1


def test_complete_tasks_matches_by_substring_either_direction():
    s = store.get_store("u1")
    s.add_tasks([{"task": "Submit the quarterly report"}])
    done = s.complete_tasks(["quarterly report"])
    assert len(done) == 1 and done[0]["status"] == "done"
    assert s.open_tasks() == []


def test_overdue_and_due_within_partition_correctly():
    s = store.get_store("u1")
    tz = ZoneInfo("Asia/Kolkata")
    past = (datetime.now(tz) - timedelta(hours=1)).isoformat()
    soon = (datetime.now(tz) + timedelta(hours=2)).isoformat()
    far = (datetime.now(tz) + timedelta(days=5)).isoformat()
    s.add_tasks([{"task": "Overdue thing", "due": past}])
    s.add_tasks([{"task": "Due soon", "due": soon}])
    s.add_tasks([{"task": "Due later", "due": far}])
    assert [t["task"] for t in s.overdue_tasks(tz)] == ["Overdue thing"]
    assert [t["task"] for t in s.tasks_due_within(24, tz)] == ["Due soon"]


# ── habits ───────────────────────────────────────────────────────────────────
def test_habit_streak_transitions():
    s = store.get_store("u1")
    h1 = s.log_habit("Running")
    assert h1["_status"] == "started" and h1["streak"] == 1

    h2 = s.log_habit("Running")
    assert h2["_status"] == "already" and h2["streak"] == 1

    yesterday = date.today() - timedelta(days=1)
    h = s._find_habit("Running")
    s.conn.execute("UPDATE habits SET last_done=? WHERE id=?", (yesterday.isoformat(), h["id"]))
    s.conn.commit()
    h3 = s.log_habit("Running")
    assert h3["_status"] == "continued" and h3["streak"] == 2

    long_ago = date.today() - timedelta(days=5)
    s.conn.execute("UPDATE habits SET last_done=? WHERE id=?", (long_ago.isoformat(), h["id"]))
    s.conn.commit()
    h4 = s.log_habit("Running")
    assert h4["_status"] == "reset" and h4["streak"] == 1
    assert h4["best_streak"] == 2  # best streak survives a reset


def test_habits_at_risk_flags_yesterdays_streak():
    s = store.get_store("u1")
    tz = ZoneInfo("Asia/Kolkata")
    s.log_habit("Running")
    h = s._find_habit("Running")
    yesterday = (datetime.now(tz).date() - timedelta(days=1)).isoformat()
    s.conn.execute("UPDATE habits SET last_done=? WHERE id=?", (yesterday, h["id"]))
    s.conn.commit()
    at_risk = s.habits_at_risk(tz)
    assert len(at_risk) == 1 and at_risk[0]["name"] == "Running"


# ── journal ──────────────────────────────────────────────────────────────────
def test_recent_mood_average():
    s = store.get_store("u1")
    s.add_journal(8, "good day")
    s.add_journal(6, "okay day")
    mood = s.recent_mood(7)
    assert len(mood) == 2
    assert sum(m["mood"] for m in mood) / len(mood) == 7


# ── registry ─────────────────────────────────────────────────────────────────
def test_register_preserves_prefs_and_updates_chat_id():
    store.registry.register("u1", chat_id=1, name="Rohith")
    store.registry.register("u1", chat_id=2, name="")  # empty name must not overwrite
    u = store.registry.get("u1")
    assert u["chat_id"] == 2
    assert u["name"] == "Rohith"
    assert u["tz"] == store.DEFAULT_TZ


def test_tz_defaults_for_unknown_user():
    assert str(store.registry.tz("nobody")) == store.DEFAULT_TZ


def test_can_nudge_rate_limits_by_gap_and_daily_cap():
    store.registry.register("u1", chat_id=1)
    assert store.registry.can_nudge("u1", max_per_day=2, min_gap_h=4) is True

    store.registry.record_nudge("u1")
    assert store.registry.can_nudge("u1", max_per_day=2, min_gap_h=4) is False  # too soon

    tz = store.registry.tz("u1")
    old = (datetime.now(tz) - timedelta(hours=5)).isoformat()
    store.registry.conn.execute("UPDATE users SET last_nudge_at=? WHERE user_id=?", (old, "u1"))
    store.registry.conn.commit()
    assert store.registry.can_nudge("u1", max_per_day=2, min_gap_h=4) is True  # gap passed

    store.registry.record_nudge("u1")
    assert store.registry.get("u1")["nudges_today"] == 2
    assert store.registry.can_nudge("u1", max_per_day=2, min_gap_h=0) is False  # daily cap hit


def test_can_nudge_false_when_paused():
    store.registry.register("u1", chat_id=1)
    store.registry.set("u1", paused=True)
    assert store.registry.can_nudge("u1") is False


def test_record_nudge_resets_counter_on_new_day():
    store.registry.register("u1", chat_id=1)
    store.registry.record_nudge("u1")
    assert store.registry.get("u1")["nudges_today"] == 1

    tz = store.registry.tz("u1")
    yesterday = (datetime.now(tz).date() - timedelta(days=1)).isoformat()
    store.registry.conn.execute("UPDATE users SET nudge_day=? WHERE user_id=?", (yesterday, "u1"))
    store.registry.conn.commit()
    store.registry.record_nudge("u1")
    assert store.registry.get("u1")["nudges_today"] == 1  # reset, not accumulated to 2


# ── reminders ────────────────────────────────────────────────────────────────
def test_reminder_add_list_remove():
    fire_at = datetime.now().astimezone() + timedelta(hours=1)
    rid = store.reminder_store.add(555, "call mom", fire_at)
    pending = store.reminder_store.get_all_for_chat(555)
    assert len(pending) == 1 and pending[0]["task"] == "call mom"
    store.reminder_store.remove(rid)
    assert store.reminder_store.get_all_for_chat(555) == []


def test_get_pending_expires_past_reminders():
    past = datetime.now().astimezone() - timedelta(seconds=1)
    future = datetime.now().astimezone() + timedelta(hours=1)
    store.reminder_store.add(1, "expired", past)
    rid2 = store.reminder_store.add(1, "future", future)

    pending = store.reminder_store.get_pending()
    assert [p["task"] for p in pending] == ["future"]

    remaining = store.reminder_store.get_all_for_chat(1)
    assert len(remaining) == 1 and remaining[0]["id"] == rid2


def test_get_all_for_chat_sorted_by_fire_time():
    later = datetime.now().astimezone() + timedelta(hours=2)
    sooner = datetime.now().astimezone() + timedelta(hours=1)
    store.reminder_store.add(2, "later", later)
    store.reminder_store.add(2, "sooner", sooner)
    tasks = [r["task"] for r in store.reminder_store.get_all_for_chat(2)]
    assert tasks == ["sooner", "later"]


# ── forget ───────────────────────────────────────────────────────────────────
def test_forget_all_wipes_every_bucket():
    s = store.get_store("u1")
    s.add_facts(["fact one"])
    s.add_log([{"key": "weight", "value": 1}])
    s.add_tasks([{"task": "do thing"}])
    s.log_habit("Running")
    s.add_journal(5)

    s.forget_all()

    assert s.facts() == []
    assert s.recent_log(days=999) == []
    assert s.open_tasks() == []
    assert s.active_habits() == []
    assert s.recent_mood(999) == []
