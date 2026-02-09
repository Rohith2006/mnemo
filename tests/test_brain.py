"""Tests for brain.py's pure/mockable core — no network calls."""

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
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResponse("ok")

    monkeypatch.setattr(brain.client.messages, "create", fake_create)

    brain.call_llm([{"role": "system", "content": "sys only"}])
    assert captured["messages"] == [{"role": "user", "content": ""}]


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


def test_apply_extraction_completes_tasks():
    s = store.get_store("u1")
    s.add_tasks([{"task": "Submit the quarterly report"}])
    changed = brain.apply_extraction(s, {"tasks_done": ["quarterly report"]})
    assert len(changed["done"]) == 1
    assert s.open_tasks() == []


def test_apply_extraction_handles_empty_data():
    s = store.get_store("u1")
    empty = {"facts": [], "log": [], "tasks": [], "done": [], "habits": [], "mood": None}
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
