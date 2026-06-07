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


def test_update_fact_replaces_the_superseded_one():
    s = store.get_store("u1")
    s.add_facts(["Lives in Bengaluru", "CS student"])
    assert s.update_fact("bengaluru", "Lives in Dubai") == "Lives in Dubai"
    assert s.facts() == ["CS student", "Lives in Dubai"]


def test_update_fact_returns_none_when_nothing_matches():
    s = store.get_store("u1")
    s.add_facts(["CS student"])
    assert s.update_fact("lives in paris", "Lives in Dubai") is None
    assert s.facts() == ["CS student"]


def test_remove_facts_hides_them_from_facts():
    s = store.get_store("u1")
    s.add_facts(["Lives in Bengaluru", "CS student"])
    assert s.remove_facts(["bengaluru"]) == ["Lives in Bengaluru"]
    assert s.facts() == ["CS student"]


def test_removed_fact_can_be_added_again():
    s = store.get_store("u1")
    s.add_facts(["Lives in Bengaluru"])
    s.remove_facts(["bengaluru"])
    assert s.add_facts(["Lives in Bengaluru"]) == ["Lives in Bengaluru"]
    assert s.facts() == ["Lives in Bengaluru"]


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


def test_complete_task_by_id_marks_done_and_ignores_unknown_id():
    s = store.get_store("u1")
    added = s.add_tasks([{"task": "Submit report"}])
    done = s.complete_task_by_id(added[0]["id"])
    assert done["status"] == "done"
    assert s.open_tasks() == []
    assert s.complete_task_by_id("no-such-id") is None


def test_completed_tasks_lists_done_most_recent_first():
    s = store.get_store("u1")
    added = s.add_tasks([{"task": "First"}, {"task": "Second"}])
    s.complete_task_by_id(added[0]["id"])
    s.complete_task_by_id(added[1]["id"])
    assert [t["task"] for t in s.completed_tasks()] == ["Second", "First"]
    assert all(t["status"] == "done" and t["done_at"] for t in s.completed_tasks())


def test_reopen_task_moves_done_back_to_open():
    s = store.get_store("u1")
    added = s.add_tasks([{"task": "Submit report"}])
    s.complete_task_by_id(added[0]["id"])

    reopened = s.reopen_task(added[0]["id"])
    assert reopened["status"] == "open"
    assert reopened["done_at"] is None
    assert [t["task"] for t in s.open_tasks()] == ["Submit report"]
    assert s.completed_tasks() == []


def test_reopen_task_ignores_unknown_or_still_open_id():
    s = store.get_store("u1")
    added = s.add_tasks([{"task": "Submit report"}])
    assert s.reopen_task("no-such-id") is None
    assert s.reopen_task(added[0]["id"]) is None  # still open, not done


# ── conversations / chat messages ───────────────────────────────────────────
def test_create_conversation_derives_title_and_timestamps():
    s = store.get_store("u1")
    conv = s.create_conversation("What should I focus on today?")
    assert conv["title"] == "What should I focus on today?"
    assert conv["created_at"] == conv["updated_at"]
    assert conv["id"]


def test_create_conversation_truncates_long_title_on_word_boundary():
    s = store.get_store("u1")
    message = "This is a very long first message that definitely exceeds fifty characters in length"
    conv = s.create_conversation(message)
    assert len(conv["title"]) <= 51  # 50 chars + ellipsis
    assert conv["title"].endswith("…")
    assert not message.startswith(conv["title"][:-1] + "x")  # sanity: it's a real prefix
    assert message.startswith(conv["title"][:-1])


def test_create_conversation_hard_truncates_single_long_word():
    s = store.get_store("u1")
    message = "x" * 80
    conv = s.create_conversation(message)
    assert conv["title"] == "x" * 50 + "…"


def test_list_conversations_orders_most_recently_updated_first():
    s = store.get_store("u1")
    first = s.create_conversation("First chat")
    second = s.create_conversation("Second chat")
    listed = s.list_conversations()
    assert [c["id"] for c in listed] == [second["id"], first["id"]]

    # Touching the older one (via add_message) should move it back to the front.
    s.add_message(first["id"], "user", "another message")
    listed_again = s.list_conversations()
    assert [c["id"] for c in listed_again] == [first["id"], second["id"]]


def test_add_message_appends_and_bumps_updated_at():
    s = store.get_store("u1")
    conv = s.create_conversation("Hello")
    s.add_message(conv["id"], "user", "Hello")
    s.add_message(conv["id"], "assistant", "Hi there!")
    messages = s.conversation_messages(conv["id"])
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Hello"),
        ("assistant", "Hi there!"),
    ]
    updated = [c for c in s.list_conversations() if c["id"] == conv["id"]][0]
    assert updated["updated_at"] >= conv["updated_at"]


def test_add_message_silently_noops_for_unknown_or_foreign_conversation():
    owner = store.get_store("u1")
    other = store.get_store("u2")
    conv = owner.create_conversation("Chat")
    other.add_message(conv["id"], "user", "Hijack attempt")
    owner.add_message("no-such-id", "user", "Also ignored")
    assert [m["content"] for m in owner.conversation_messages(conv["id"])] == []


def test_conversation_messages_returns_none_for_unknown_id():
    s = store.get_store("u1")
    assert s.conversation_messages("no-such-id") is None


def test_conversation_messages_returns_none_for_another_users_conversation():
    owner = store.get_store("u1")
    other = store.get_store("u2")
    conv = owner.create_conversation("Private chat")
    assert other.conversation_messages(conv["id"]) is None


def test_rename_conversation_updates_title_without_touching_updated_at():
    s = store.get_store("u1")
    conv = s.create_conversation("Original title")
    renamed = s.rename_conversation(conv["id"], "New title")
    assert renamed["title"] == "New title"
    assert renamed["updated_at"] == conv["updated_at"]


def test_rename_conversation_returns_none_for_unknown_or_foreign_id():
    owner = store.get_store("u1")
    other = store.get_store("u2")
    conv = owner.create_conversation("Chat")
    assert owner.rename_conversation("no-such-id", "New title") is None
    assert other.rename_conversation(conv["id"], "Hijacked title") is None


def test_delete_conversation_removes_conversation_and_its_messages():
    s = store.get_store("u1")
    conv = s.create_conversation("Chat")
    s.add_message(conv["id"], "user", "Chat")
    assert s.delete_conversation(conv["id"]) is True
    assert s.conversation_messages(conv["id"]) is None
    assert conv["id"] not in [c["id"] for c in s.list_conversations()]


def test_delete_conversation_returns_false_for_unknown_or_foreign_id():
    owner = store.get_store("u1")
    other = store.get_store("u2")
    conv = owner.create_conversation("Chat")
    assert owner.delete_conversation("no-such-id") is False
    assert other.delete_conversation(conv["id"]) is False


def test_forget_all_wipes_conversations_and_messages():
    s = store.get_store("u1")
    conv = s.create_conversation("Chat")
    s.add_message(conv["id"], "user", "Chat")
    s.forget_all()
    assert s.list_conversations() == []
    assert s.conversation_messages(conv["id"]) is None


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


def test_overdue_tasks_date_only_due_today_is_not_overdue():
    # A date-only due ("no time mentioned") for today must not be overdue no
    # matter how late in the day it already is — there's no time to have missed.
    s = store.get_store("u1")
    tz = ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date().isoformat()
    s.add_tasks([{"task": "Due today, no time", "due": today}])
    assert s.overdue_tasks(tz) == []


def test_overdue_tasks_date_only_due_yesterday_is_overdue():
    s = store.get_store("u1")
    tz = ZoneInfo("Asia/Kolkata")
    yesterday = (datetime.now(tz).date() - timedelta(days=1)).isoformat()
    s.add_tasks([{"task": "Due yesterday, no time", "due": yesterday}])
    assert [t["task"] for t in s.overdue_tasks(tz)] == ["Due yesterday, no time"]


def test_overdue_tasks_with_explicit_past_time_today_is_overdue():
    # A due date WITH a time is still judged against the exact instant, even
    # when that instant falls earlier today.
    s = store.get_store("u1")
    tz = ZoneInfo("Asia/Kolkata")
    earlier_today = (datetime.now(tz) - timedelta(hours=1)).isoformat()
    s.add_tasks([{"task": "Due earlier today, with time", "due": earlier_today}])
    assert [t["task"] for t in s.overdue_tasks(tz)] == ["Due earlier today, with time"]


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
def test_create_account_and_lookup_by_email():
    u = store.registry.create("Rohith@Example.com", "hashed-pw", name="Rohith")
    assert u["email"] == "rohith@example.com"  # normalized to lowercase
    assert u["name"] == "Rohith"
    assert u["tz"] == store.DEFAULT_TZ
    assert store.registry.get(u["user_id"])["email"] == "rohith@example.com"
    assert store.registry.get_by_email("rohith@example.com")["user_id"] == u["user_id"]


def test_create_account_rejects_duplicate_email():
    store.registry.create("dup@example.com", "hash1")
    try:
        store.registry.create("dup@example.com", "hash2")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_set_updates_fields():
    u = store.registry.create("set@example.com", "hash")
    store.registry.set(u["user_id"], name="New Name", tz="America/New_York")
    updated = store.registry.get(u["user_id"])
    assert updated["name"] == "New Name"
    assert updated["tz"] == "America/New_York"


def test_tz_defaults_for_unknown_user():
    assert str(store.registry.tz("nobody")) == store.DEFAULT_TZ


# ── reminders ────────────────────────────────────────────────────────────────
def test_reminder_add_list_remove():
    fire_at = datetime.now().astimezone() + timedelta(hours=1)
    rid = store.reminder_store.add("u555", "call mom", fire_at)
    pending = store.reminder_store.get_all_for_user("u555")
    assert len(pending) == 1 and pending[0]["task"] == "call mom"
    store.reminder_store.remove(rid)
    assert store.reminder_store.get_all_for_user("u555") == []


def test_get_pending_expires_past_reminders():
    past = datetime.now().astimezone() - timedelta(seconds=1)
    future = datetime.now().astimezone() + timedelta(hours=1)
    store.reminder_store.add("u1", "expired", past)
    rid2 = store.reminder_store.add("u1", "future", future)

    pending = store.reminder_store.get_pending()
    assert [p["task"] for p in pending] == ["future"]

    remaining = store.reminder_store.get_all_for_user("u1")
    assert len(remaining) == 1 and remaining[0]["id"] == rid2


def test_remove_for_user_drops_only_that_users_reminders():
    fire_at = datetime.now().astimezone() + timedelta(hours=1)
    store.reminder_store.add("mine", "call mom", fire_at)
    store.reminder_store.add("theirs", "not mine", fire_at)

    store.reminder_store.remove_for_user("mine")

    assert store.reminder_store.get_all_for_user("mine") == []
    assert len(store.reminder_store.get_all_for_user("theirs")) == 1


def test_get_all_for_user_sorted_by_fire_time():
    later = datetime.now().astimezone() + timedelta(hours=2)
    sooner = datetime.now().astimezone() + timedelta(hours=1)
    store.reminder_store.add("u2", "later", later)
    store.reminder_store.add("u2", "sooner", sooner)
    tasks = [r["task"] for r in store.reminder_store.get_all_for_user("u2")]
    assert tasks == ["sooner", "later"]


# ── digest cache ─────────────────────────────────────────────────────────────
def test_digest_cache_roundtrip_and_overwrite():
    s = store.get_store("u1")
    assert s.get_cached_digest("morning", "2026-08-17") is None
    s.save_digest("morning", "2026-08-17", "first version")
    assert s.get_cached_digest("morning", "2026-08-17") == "first version"
    s.save_digest("morning", "2026-08-17", "regenerated")
    assert s.get_cached_digest("morning", "2026-08-17") == "regenerated"
    assert s.get_cached_digest("evening", "2026-08-17") is None  # different kind, no bleed


def test_invalidate_today_digests_drops_only_todays_cache():
    s = store.get_store("u1")
    tz = ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date().isoformat()
    yesterday = (datetime.now(tz).date() - timedelta(days=1)).isoformat()
    s.save_digest("morning", today, "stale morning text")
    s.save_digest("ondemand", today, "stale ondemand text")
    s.save_digest("evening", yesterday, "yesterday's digest should survive")

    s.invalidate_today_digests(tz)

    assert s.get_cached_digest("morning", today) is None
    assert s.get_cached_digest("ondemand", today) is None
    assert s.get_cached_digest("evening", yesterday) == "yesterday's digest should survive"


# ── forget ───────────────────────────────────────────────────────────────────
def test_forget_all_wipes_every_bucket():
    s = store.get_store("u1")
    s.add_facts(["fact one"])
    s.add_log([{"key": "weight", "value": 1}])
    s.add_tasks([{"task": "do thing"}])
    s.log_habit("Running")
    s.add_journal(5)
    s.save_digest("morning", "2026-08-17", "text")

    s.forget_all()

    assert s.facts() == []
    assert s.recent_log(days=999) == []
    assert s.open_tasks() == []
    assert s.active_habits() == []
    assert s.recent_mood(999) == []
    assert s.get_cached_digest("morning", "2026-08-17") is None
