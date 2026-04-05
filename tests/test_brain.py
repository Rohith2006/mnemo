"""Tests for brain.py's pure/mockable core — no network calls."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import brain
import store

TZ = ZoneInfo("Asia/Kolkata")


# ── parse_json ───────────────────────────────────────────────────────────────
def test_parse_json_plain_object():
    assert brain.parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_plain_array():
    assert brain.parse_json("[1, 2, 3]") == [1, 2, 3]


def test_parse_json_fenced_with_json_tag():
    assert brain.parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_fenced_without_tag():
    assert brain.parse_json('```\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_surrounding_prose():
    raw = 'Sure, here you go:\n{"a": 1}\nHope that helps!'
    assert brain.parse_json(raw) == {"a": 1}


def test_parse_json_invalid_returns_none():
    assert brain.parse_json("not json at all") is None


def test_parse_json_malformed_braces_returns_none():
    assert brain.parse_json('{"a": }') is None


# ── human_duration ───────────────────────────────────────────────────────────
def test_human_duration_seconds():
    assert brain.human_duration(0) == "0 seconds"
    assert brain.human_duration(1) == "1 second"
    assert brain.human_duration(59) == "59 seconds"


def test_human_duration_minutes():
    assert brain.human_duration(60) == "1 minute"
    assert brain.human_duration(3599) == "59 minutes"


def test_human_duration_hours():
    assert brain.human_duration(3600) == "1 hour"
    assert brain.human_duration(3661) == "1h 1m"


# ── call_llm (mocked client — no network) ────────────────────────────────────
class _FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


def test_call_llm_splits_system_from_conversation(monkeypatch):
    # LLM_PROVIDER is pinned per-test (not left to whatever the developer's local
    # .env happens to have) so this exercises the Anthropic branch deterministically.
    monkeypatch.setattr(brain, "LLM_PROVIDER", "anthropic")
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResponse("hi there")

    monkeypatch.setattr(brain.client.messages, "create", fake_create)

    reply = brain.call_llm([
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ])

    assert reply == "hi there"
    assert captured["system"] == "You are helpful."
    assert captured["messages"] == [{"role": "user", "content": "Hello"}]


def test_call_llm_defaults_to_empty_user_turn_when_no_conversation(monkeypatch):
    monkeypatch.setattr(brain, "LLM_PROVIDER", "anthropic")
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResponse("ok")

    monkeypatch.setattr(brain.client.messages, "create", fake_create)

    brain.call_llm([{"role": "system", "content": "sys only"}])
    assert captured["messages"] == [{"role": "user", "content": ""}]


class _FakeGroqMessage:
    def __init__(self, text):
        self.content = text


class _FakeGroqChoice:
    def __init__(self, text):
        self.message = _FakeGroqMessage(text)


class _FakeGroqResponse:
    def __init__(self, text):
        self.choices = [_FakeGroqChoice(text)]


def test_call_llm_groq_branch_sends_system_as_a_message(monkeypatch):
    # Groq's (OpenAI-shaped) API has no separate top-level `system` param — it's
    # just another message, unlike Anthropic's.
    monkeypatch.setattr(brain, "LLM_PROVIDER", "groq")
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeGroqResponse("hi from groq")

    monkeypatch.setattr(brain.groq_client.chat.completions, "create", fake_create)

    reply = brain.call_llm([
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ], temperature=0.5)

    assert reply == "hi from groq"
    assert captured["messages"] == [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    assert captured["temperature"] == 0.5  # unlike Anthropic, Groq forwards it


# ── apply_extraction (real store, no mocking needed) ─────────────────────────
def test_apply_extraction_persists_all_buckets():
    s = store.get_store("u1")
    data = {
        "facts": ["Lives in Bengaluru", 123],  # non-str entries filtered out
        "log": [{"category": "health", "key": "weight", "value": 80, "unit": "kg"}, "not-a-dict"],
        "tasks_new": [{"task": "Submit report", "due": None}],
        "tasks_done": [],
        "habits_done": ["Running"],
        "mood": {"score": 8, "note": "good day"},
    }
    changed = brain.apply_extraction(s, data)

    assert changed["facts"] == ["Lives in Bengaluru"]
    assert len(changed["log"]) == 1 and changed["log"][0]["key"] == "weight"
    assert len(changed["tasks"]) == 1 and changed["tasks"][0]["task"] == "Submit report"
    assert changed["done"] == []
    assert len(changed["habits"]) == 1 and changed["habits"][0]["name"] == "Running"
    assert changed["mood"]["mood"] == 8

    assert s.facts() == ["Lives in Bengaluru"]
    assert len(s.open_tasks()) == 1
    assert len(s.active_habits()) == 1


def test_apply_extraction_dates_a_habit_by_the_users_timezone(foreign_tz):
    """Streaks are counted in consecutive local days, so a habit has to be dated
    on the user's calendar day — not on whatever day it is where the server runs."""
    s = store.get_store("u1")
    tz = ZoneInfo(foreign_tz)

    brain.apply_extraction(s, {"habits_done": ["Running"]}, tz=tz)

    assert s.active_habits()[0]["last_done"] == datetime.now(tz).date().isoformat()


def test_apply_extraction_updates_a_superseded_fact():
    s = store.get_store("u1")
    s.add_facts(["Lives in Bengaluru"])
    changed = brain.apply_extraction(
        s, {"facts_update": [{"old": "bengaluru", "new": "Lives in Dubai"}]}
    )
    assert changed["facts_updated"] == ["Lives in Dubai"]
    assert s.facts() == ["Lives in Dubai"]


def test_apply_extraction_removes_contradicted_facts():
    s = store.get_store("u1")
    s.add_facts(["Vegetarian", "CS student"])
    changed = brain.apply_extraction(s, {"facts_remove": ["vegetarian"]})
    assert changed["facts_removed"] == ["Vegetarian"]
    assert s.facts() == ["CS student"]


def test_apply_extraction_ignores_malformed_fact_reconciliation():
    s = store.get_store("u1")
    s.add_facts(["Lives in Bengaluru"])
    changed = brain.apply_extraction(
        s,
        {
            "facts_update": ["not-a-dict", {"old": "bengaluru"}, {"new": "no old key"}],
            "facts_remove": [123, None],
        },
    )
    assert changed["facts_updated"] == []
    assert changed["facts_removed"] == []
    assert s.facts() == ["Lives in Bengaluru"]


def test_extract_prompt_includes_existing_facts(monkeypatch):
    s = store.get_store("u1")
    s.add_facts(["Lives in Bengaluru"])

    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "{}"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    brain.extract("i moved to dubai", "Nice!", s, TZ)

    assert "Lives in Bengaluru" in captured["prompt"]


def test_apply_extraction_completes_tasks():
    s = store.get_store("u1")
    s.add_tasks([{"task": "Submit the quarterly report"}])
    changed = brain.apply_extraction(s, {"tasks_done": ["quarterly report"]})
    assert len(changed["done"]) == 1
    assert s.open_tasks() == []


def test_apply_extraction_handles_empty_data():
    s = store.get_store("u1")
    empty = {"facts": [], "facts_updated": [], "facts_removed": [],
             "log": [], "tasks": [], "done": [], "habits": [], "mood": None}
    assert brain.apply_extraction(s, {}) == empty
    assert brain.apply_extraction(s, None) == empty


def test_apply_extraction_ignores_invalid_mood_score():
    s = store.get_store("u1")
    changed = brain.apply_extraction(s, {"mood": {"score": "not-a-number"}})
    assert changed["mood"] is None
    assert s.recent_mood(999) == []


# ── extract (mocked LLM) ──────────────────────────────────────────────────────
def test_extract_returns_parsed_dict(monkeypatch):
    s = store.get_store("u1")
    monkeypatch.setattr(brain, "call_llm", lambda *a, **k: '{"facts": ["CS student"]}')
    assert brain.extract("I study CS", "Nice!", s, TZ) == {"facts": ["CS student"]}


def test_extract_returns_empty_dict_for_non_dict_llm_output(monkeypatch):
    s = store.get_store("u1")
    monkeypatch.setattr(brain, "call_llm", lambda *a, **k: "[1, 2, 3]")
    assert brain.extract("hi", "hello", s, TZ) == {}


def test_extract_prompt_includes_open_tasks_and_habits(monkeypatch):
    s = store.get_store("u1")
    s.add_tasks([{"task": "Submit report"}])
    s.log_habit("Running")

    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "{}"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    brain.extract("did my run", "Nice!", s, TZ)

    assert "Submit report" in captured["prompt"]
    assert "Running" in captured["prompt"]


# ── _correct_weekday_due ──────────────────────────────────────────────────────
# Regression coverage for a real bug: the extraction model (a low-effort fast
# model) resolved "by Friday" to a Tuesday. Rather than trust model arithmetic,
# extract() deterministically overrides the date when exactly one weekday is named.
_SAT = datetime(2026, 8, 29, 10, 0, tzinfo=TZ)  # a known Saturday


def test_correct_weekday_due_fixes_wrong_weekday():
    assert brain._correct_weekday_due("finish report by Friday", "2026-09-01", _SAT) == "2026-09-04"


def test_correct_weekday_due_leaves_correct_date_alone():
    assert brain._correct_weekday_due("finish report by Friday", "2026-09-04", _SAT) == "2026-09-04"


def test_correct_weekday_due_preserves_time_component():
    due = "2026-09-01T15:00:00+05:30"
    assert brain._correct_weekday_due("call at 3pm on Wednesday", due, _SAT) == "2026-09-02T15:00:00+05:30"


def test_correct_weekday_due_today_is_named_weekday():
    assert brain._correct_weekday_due("finish it by Saturday", "2026-09-05", _SAT) == "2026-08-29"


def test_correct_weekday_due_skips_when_no_weekday_named():
    assert brain._correct_weekday_due("finish it tomorrow", "2026-09-10", _SAT) == "2026-09-10"


def test_correct_weekday_due_skips_when_multiple_weekdays_named():
    assert brain._correct_weekday_due("either Monday or Friday works", "2026-09-01", _SAT) == "2026-09-01"


def test_correct_weekday_due_skips_falsy_due():
    assert brain._correct_weekday_due("finish by Friday", None, _SAT) is None
    assert brain._correct_weekday_due("finish by Friday", "", _SAT) == ""


def test_extract_corrects_wrong_weekday_due(monkeypatch):
    s = store.get_store("u1")
    monkeypatch.setattr(
        brain, "call_llm",
        lambda *a, **k: '{"tasks_new": [{"task": "finish report", "due": "2099-01-01"}]}',
    )
    result = brain.extract("finish report by Friday", "Sure!", s, TZ)
    due = result["tasks_new"][0]["due"]
    assert due != "2099-01-01"
    assert datetime.fromisoformat(due).strftime("%A") == "Friday"


# ── detect_reminder (mocked LLM) ──────────────────────────────────────────────
def test_detect_reminder_returns_none_when_not_a_reminder(monkeypatch):
    monkeypatch.setattr(brain, "call_llm", lambda *a, **k: '{"is_reminder": false}')
    assert brain.detect_reminder("just chatting", TZ) is None


def test_detect_reminder_returns_task_and_seconds(monkeypatch):
    monkeypatch.setattr(
        brain, "call_llm",
        lambda *a, **k: '{"is_reminder": true, "task": "call mom", "seconds_from_now": 1800}',
    )
    result = brain.detect_reminder("remind me to call mom in 30 min", TZ)
    assert result == {"task": "call mom", "seconds": 1800}


def test_detect_reminder_returns_none_when_seconds_not_positive(monkeypatch):
    monkeypatch.setattr(
        brain, "call_llm",
        lambda *a, **k: '{"is_reminder": true, "task": "call mom", "seconds_from_now": 0}',
    )
    assert brain.detect_reminder("call mom", TZ) is None


def test_detect_reminder_returns_none_when_task_missing(monkeypatch):
    monkeypatch.setattr(
        brain, "call_llm",
        lambda *a, **k: '{"is_reminder": true, "seconds_from_now": 1800}',
    )
    assert brain.detect_reminder("remind me", TZ) is None


def test_detect_reminder_accepts_seconds_returned_as_a_string(monkeypatch):
    """LLM JSON is untrusted input: a model that quotes the number must not crash
    the whole capture request on a str-vs-int comparison."""
    monkeypatch.setattr(
        brain, "call_llm",
        lambda *a, **k: '{"is_reminder": true, "task": "call mom", "seconds_from_now": "1800"}',
    )
    assert brain.detect_reminder("remind me to call mom", TZ) == {"task": "call mom", "seconds": 1800}


def test_detect_reminder_returns_none_when_seconds_is_not_a_number(monkeypatch):
    monkeypatch.setattr(
        brain, "call_llm",
        lambda *a, **k: '{"is_reminder": true, "task": "call mom", "seconds_from_now": "soon"}',
    )
    assert brain.detect_reminder("remind me to call mom", TZ) is None


# ── build_reply (mocked LLM) ───────────────────────────────────────────────────
def test_build_reply_includes_summary_and_pending_reminders(monkeypatch):
    s = store.get_store("u1")
    s.add_facts(["Lives in Bengaluru"])

    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["messages"] = messages
        return "Hey there!"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)

    pending = [{"task": "call mom", "fire_at_dt": datetime.now(TZ) + timedelta(hours=1)}]
    reply = brain.build_reply(s, "hello", [], TZ, pending_reminders=pending)

    assert reply == "Hey there!"
    system_prompt = captured["messages"][0]["content"]
    assert "Lives in Bengaluru" in system_prompt
    assert "call mom" in system_prompt
    assert captured["messages"][-1] == {"role": "user", "content": "hello"}


def test_build_reply_says_none_when_no_pending_reminders(monkeypatch):
    s = store.get_store("u1")
    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    brain.build_reply(s, "hi", [], TZ)
    assert "PENDING REMINDERS: none." in captured["messages"][0]["content"]


def test_build_reply_includes_system_action_for_new_reminder(monkeypatch):
    s = store.get_store("u1")
    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["messages"] = messages
        return "Got it!"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    brain.build_reply(s, "remind me to call mom in 30 min", [], TZ,
                       new_reminder={"task": "call mom", "seconds": 1800})

    system_prompt = captured["messages"][0]["content"]
    assert "SYSTEM ACTION" in system_prompt
    assert "call mom" in system_prompt
    assert "30 minutes" in system_prompt


def test_build_reply_places_history_between_system_and_user_message(monkeypatch):
    s = store.get_store("u1")
    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    history = [{"role": "user", "content": "earlier msg"}, {"role": "assistant", "content": "earlier reply"}]
    brain.build_reply(s, "now what", history, TZ)

    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1:3] == history
    assert messages[3] == {"role": "user", "content": "now what"}


# ── build_digest (mocked LLM) ──────────────────────────────────────────────────
def test_build_digest_morning_uses_briefing_instruction(monkeypatch):
    s = store.get_store("u1")
    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "Good morning!"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    assert brain.build_digest(s, TZ, "morning") == "Good morning!"
    assert "morning briefing" in captured["prompt"].lower()


def test_build_digest_evening_uses_review_instruction(monkeypatch):
    s = store.get_store("u1")
    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "Evening!"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    brain.build_digest(s, TZ, "evening")
    assert "evening review" in captured["prompt"].lower()


def test_build_digest_ondemand_uses_insights_instruction(monkeypatch):
    s = store.get_store("u1")
    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "Insights!"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    brain.build_digest(s, TZ, "ondemand")
    assert "insights update" in captured["prompt"].lower()


def test_build_digest_embeds_trends_overdue_due_soon_and_at_risk_streaks(monkeypatch):
    s = store.get_store("u1")
    s.add_log([{"key": "weight", "value": 82}])
    s.add_log([{"key": "weight", "value": 75}])

    past = (datetime.now(TZ) - timedelta(hours=1)).isoformat()
    soon = (datetime.now(TZ) + timedelta(hours=2)).isoformat()
    s.add_tasks([{"task": "Overdue thing", "due": past}])
    s.add_tasks([{"task": "Due soon thing", "due": soon}])

    s.log_habit("Running")
    h = s._find_habit("Running")
    yesterday = (datetime.now(TZ).date() - timedelta(days=1)).isoformat()
    s.conn.execute("UPDATE habits SET last_done=? WHERE id=?", (yesterday, h["id"]))
    s.conn.commit()

    captured = {}

    def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "Update!"

    monkeypatch.setattr(brain, "call_llm", fake_call_llm)
    brain.build_digest(s, TZ, "ondemand")

    prompt = captured["prompt"]
    assert "Overdue thing" in prompt
    assert "Due soon thing" in prompt
    assert "Running" in prompt
    assert "weight" in prompt
