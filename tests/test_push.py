"""Tests for push.py — the push-notification send + tick logic. The Expo HTTP
call is mocked via monkeypatch, exactly like brain.call_llm is mocked
elsewhere in this suite — no real network calls."""

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import brain
import push
import store

TZ = ZoneInfo("Asia/Kolkata")


class FakeExpoResponse:
    def __init__(self, ok: bool):
        self._ok = ok

    def json(self):
        if self._ok:
            return {"data": {"status": "ok"}}
        return {"data": {"status": "error", "details": {"error": "DeviceNotRegistered"}}}


@pytest.fixture
def fake_expo(monkeypatch):
    calls = []
    result = {"ok": True}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs.get("json")))
        return FakeExpoResponse(result["ok"])

    monkeypatch.setattr(push.httpx, "post", fake_post)
    return calls, result


def _freeze(monkeypatch, dt: datetime) -> None:
    """Pin push's notion of "now" to a fixed instant, so run_tick's
    morning/evening hour checks never depend on the real wall-clock time the
    suite happens to run at — without this, a test with an overdue task but
    no digest expectations could non-deterministically also exercise the
    (unmocked) digest path and attempt a real LLM call whenever the suite
    happened to run at or after 8am local."""
    class _FrozenDatetime:
        @staticmethod
        def now(tz):
            return dt.replace(tzinfo=tz)

    monkeypatch.setattr(push, "datetime", _FrozenDatetime)


def test_send_push_posts_to_expo_and_returns_true_on_success(fake_expo):
    calls, _ = fake_expo
    ok = push.send_push("ExponentPushToken[x]", "Title", "Body")
    assert ok is True
    assert len(calls) == 1
    url, payload = calls[0]
    assert "exp.host" in url
    assert payload["to"] == "ExponentPushToken[x]"
    assert payload["title"] == "Title"
    assert payload["body"] == "Body"


def test_send_push_returns_false_on_expo_error(fake_expo):
    _, result = fake_expo
    result["ok"] = False
    assert push.send_push("ExponentPushToken[x]", "Title", "Body") is False


def _make_user(email="tick@example.com", tz="Asia/Kolkata", push_enabled=True):
    u = store.registry.create(email, "hashed", tz=tz)
    if not push_enabled:
        store.registry.set(u["user_id"], push_enabled=0)
    return u


def test_run_tick_sends_nothing_for_a_user_with_no_push_token(fake_expo):
    calls, _ = fake_expo
    _make_user()
    push.run_tick()
    assert calls == []


def test_run_tick_skips_a_push_disabled_user_even_with_a_token(fake_expo):
    calls, _ = fake_expo
    u = _make_user(push_enabled=False)
    store.get_store(u["user_id"]).add_push_token("ExponentPushToken[x]", "ios")
    push.run_tick()
    assert calls == []


def test_run_tick_sends_overdue_task_once_and_never_again(fake_expo, monkeypatch):
    calls, _ = fake_expo
    u = _make_user()
    s = store.get_store(u["user_id"])
    s.add_push_token("ExponentPushToken[x]", "ios")
    s.add_tasks([{"task": "Overdue thing", "due": "2020-01-01"}])
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 0))  # before both digest thresholds

    push.run_tick()
    assert len(calls) == 1
    assert "Overdue thing" in calls[0][1]["body"]

    push.run_tick()  # a second tick must not re-send the same task
    assert len(calls) == 1


def test_run_tick_sends_morning_digest_once_after_8am_local(fake_expo, monkeypatch):
    calls, _ = fake_expo
    u = _make_user()
    store.get_store(u["user_id"]).add_push_token("ExponentPushToken[x]", "ios")
    monkeypatch.setattr(brain, "call_llm", lambda *a, **k: "Your morning digest text.")
    _freeze(monkeypatch, datetime(2026, 8, 31, 8, 5))

    push.run_tick()
    assert len(calls) == 1
    assert calls[0][1]["body"] == "Your morning digest text."

    push.run_tick()  # same simulated time again -> already sent today, no repeat
    assert len(calls) == 1


def test_run_tick_before_8am_sends_no_morning_digest(fake_expo, monkeypatch):
    calls, _ = fake_expo
    u = _make_user()
    store.get_store(u["user_id"]).add_push_token("ExponentPushToken[x]", "ios")
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 59))

    push.run_tick()
    assert calls == []


def test_run_tick_evening_digest_includes_at_risk_habit_line(fake_expo, monkeypatch):
    calls, _ = fake_expo
    u = _make_user()
    s = store.get_store(u["user_id"])
    s.add_push_token("ExponentPushToken[x]", "ios")
    # habits_at_risk(tz) computes "today"/"yesterday" from store.py's own
    # (unmocked) datetime.now(tz) — only push.datetime is frozen below, for
    # run_tick's own hour-threshold gate. So the habit's last_done has to be
    # anchored to the REAL date the suite runs on (date.today() - 1 day), not
    # a hardcoded date, for this test to be deterministic on any run date.
    s.log_habit("Running", on=date.today() - timedelta(days=1))
    monkeypatch.setattr(brain, "build_digest", lambda store, tz, kind: "Evening summary.")
    _freeze(monkeypatch, datetime.now().replace(hour=20, minute=1, second=0, microsecond=0))

    push.run_tick()

    assert len(calls) == 1
    body = calls[0][1]["body"]
    assert "Evening summary." in body
    assert "Running" in body


def test_run_tick_one_users_failure_does_not_block_another(fake_expo, monkeypatch):
    calls, result = fake_expo
    u1 = _make_user("fail@example.com")
    u2 = _make_user("ok@example.com")
    store.get_store(u1["user_id"]).add_push_token("ExponentPushToken[fail]", "ios")
    store.get_store(u1["user_id"]).add_tasks([{"task": "Task A", "due": "2020-01-01"}])
    store.get_store(u2["user_id"]).add_push_token("ExponentPushToken[ok]", "ios")
    store.get_store(u2["user_id"]).add_tasks([{"task": "Task B", "due": "2020-01-01"}])
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 0))

    real_post = push.httpx.post
    def flaky_post(url, **kwargs):
        if kwargs["json"]["to"] == "ExponentPushToken[fail]":
            raise RuntimeError("simulated network failure")
        return real_post(url, **kwargs)
    monkeypatch.setattr(push.httpx, "post", flaky_post)

    push.run_tick()

    bodies = [c[1]["body"] for c in calls]
    assert any("Task B" in b for b in bodies)


def test_run_tick_prunes_a_token_that_fails_to_send(fake_expo, monkeypatch):
    _, result = fake_expo
    result["ok"] = False
    u = _make_user()
    s = store.get_store(u["user_id"])
    s.add_push_token("ExponentPushToken[dead]", "ios")
    s.add_tasks([{"task": "Overdue thing", "due": "2020-01-01"}])
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 0))

    push.run_tick()

    assert s.push_tokens() == []


def test_start_scheduler_is_a_no_op_under_pytest():
    """PYTEST_CURRENT_TEST is always set while pytest is running a test — this
    must prevent a real background thread from starting, or every test run
    would leak a live scheduler ticking every 5 minutes."""
    assert os.environ.get("PYTEST_CURRENT_TEST")  # sanity: confirms the guard's premise holds here
    push.start_scheduler()  # must not raise, must not start a real thread
    assert push._scheduler is None
