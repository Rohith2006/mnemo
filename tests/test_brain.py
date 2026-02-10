"""Tests for brain.py's pure/mockable core — no network calls."""

import brain


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
