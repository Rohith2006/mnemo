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
    """A fake httpx.Response stand-in for Expo's push API. `mode` controls
    what Expo (pretend) reported:
      - "ok"            — a genuine successful send.
      - "invalid_token" — Expo explicitly reports the token as bad (the only
                           mode send_push should treat as SEND_INVALID_TOKEN).
      - "other_error"   — some other Expo-reported error code — must be
                           treated as SEND_TRANSIENT, not pruned.
      - "http_error"     — a non-2xx HTTP status from Expo itself — also
                            SEND_TRANSIENT.
    """

    def __init__(self, mode: str = "ok"):
        self._mode = mode
        self.status_code = 500 if mode == "http_error" else 200

    def json(self):
        if self._mode == "ok":
            return {"data": {"status": "ok"}}
        if self._mode == "invalid_token":
            return {"data": {"status": "error", "details": {"error": "DeviceNotRegistered"}}}
        return {"data": {"status": "error", "details": {"error": "SomeOtherExpoError"}}}


@pytest.fixture
def fake_expo(monkeypatch):
    calls = []
    state = {"mode": "ok"}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs.get("json")))
        return FakeExpoResponse(state["mode"])

    monkeypatch.setattr(push.httpx, "post", fake_post)
    return calls, state


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


def test_send_push_posts_to_expo_and_returns_ok_on_success(fake_expo):
    calls, _ = fake_expo
    result = push.send_push("ExponentPushToken[x]", "Title", "Body")
    assert result == push.SEND_OK
    assert len(calls) == 1
    url, payload = calls[0]
    assert "exp.host" in url
    assert payload["to"] == "ExponentPushToken[x]"
    assert payload["title"] == "Title"
    assert payload["body"] == "Body"


def test_send_push_returns_invalid_token_on_device_not_registered(fake_expo):
    _, state = fake_expo
    state["mode"] = "invalid_token"
    assert push.send_push("ExponentPushToken[x]", "Title", "Body") == push.SEND_INVALID_TOKEN


def test_send_push_returns_transient_on_other_expo_error(fake_expo):
    """An Expo-reported error that isn't a recognized invalid-token code must
    not be treated the same as a genuinely dead token."""
    _, state = fake_expo
    state["mode"] = "other_error"
    assert push.send_push("ExponentPushToken[x]", "Title", "Body") == push.SEND_TRANSIENT


def test_send_push_returns_transient_on_non_2xx_http(fake_expo):
    _, state = fake_expo
    state["mode"] = "http_error"
    assert push.send_push("ExponentPushToken[x]", "Title", "Body") == push.SEND_TRANSIENT


def test_send_push_returns_transient_on_network_exception(monkeypatch):
    def raising_post(url, **kwargs):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(push.httpx, "post", raising_post)
    assert push.send_push("ExponentPushToken[x]", "Title", "Body") == push.SEND_TRANSIENT


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


def test_run_tick_coalesces_more_than_two_overdue_tasks_into_one_push(fake_expo, monkeypatch):
    """First-run-against-an-existing-database scenario: several tasks already
    overdue at once must produce one combined push, not a burst of one push
    per task."""
    calls, _ = fake_expo
    u = _make_user()
    s = store.get_store(u["user_id"])
    s.add_push_token("ExponentPushToken[x]", "ios")
    s.add_tasks([
        {"task": "Task 1", "due": "2020-01-01"},
        {"task": "Task 2", "due": "2020-01-02"},
        {"task": "Task 3", "due": "2020-01-03"},
    ])
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 0))

    push.run_tick()

    assert len(calls) == 1
    body = calls[0][1]["body"]
    assert "3 tasks are overdue" in body
    assert "Task 1" in body  # the oldest (earliest-due) task named specifically

    push.run_tick()  # every task already logged — must not fire again, combined or individually
    assert len(calls) == 1


def test_run_tick_two_overdue_tasks_still_send_individually(fake_expo, monkeypatch):
    """At-or-below the coalesce threshold, behavior is unchanged: one push
    per task."""
    calls, _ = fake_expo
    u = _make_user()
    s = store.get_store(u["user_id"])
    s.add_push_token("ExponentPushToken[x]", "ios")
    s.add_tasks([
        {"task": "Task 1", "due": "2020-01-01"},
        {"task": "Task 2", "due": "2020-01-02"},
    ])
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 0))

    push.run_tick()

    assert len(calls) == 2
    bodies = [c[1]["body"] for c in calls]
    assert any("Task 1" in b and "is overdue" in b for b in bodies)
    assert any("Task 2" in b and "is overdue" in b for b in bodies)


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


def test_run_tick_cold_catchup_after_8pm_sends_evening_only_not_morning(fake_expo, monkeypatch):
    """The exact scenario the morning window's upper bound exists for: a
    user's very first tick of the day lands at/after 20:00 (e.g. the server
    was down all day) — must send the evening digest and must NOT also fire
    a "Good morning" push hours late. Regression test for a real defect
    caught during Task 2's review: the unbounded morning check this plan
    originally specified would have fired both simultaneously here."""
    calls, _ = fake_expo
    u = _make_user()
    store.get_store(u["user_id"]).add_push_token("ExponentPushToken[x]", "ios")
    monkeypatch.setattr(brain, "build_digest", lambda store, tz, kind: f"{kind} digest.")
    _freeze(monkeypatch, datetime(2026, 8, 31, 21, 0))

    push.run_tick()

    assert len(calls) == 1
    assert calls[0][1]["body"] == "evening digest."


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


def test_run_tick_digest_push_reuses_the_in_app_digest_cache(fake_expo, monkeypatch):
    """A digest already generated (and cached) by an /api/digests fetch earlier
    in the day must be reused as-is by the push tick, not regenerated by a
    second LLM call — so the pushed text and the in-app text always agree."""
    calls, _ = fake_expo
    u = _make_user()
    s = store.get_store(u["user_id"])
    s.add_push_token("ExponentPushToken[x]", "ios")
    _freeze(monkeypatch, datetime(2026, 8, 31, 8, 5))
    today = "2026-08-31"
    s.save_digest("morning", today, "Cached morning text from an earlier /api/digests call.")

    def explode(*a, **k):
        raise AssertionError("build_digest should not be called when a cached digest exists")

    monkeypatch.setattr(brain, "build_digest", explode)

    push.run_tick()

    assert len(calls) == 1
    assert calls[0][1]["body"] == "Cached morning text from an earlier /api/digests call."


def test_run_tick_one_users_failure_does_not_block_another(fake_expo, monkeypatch):
    calls, state = fake_expo
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


def test_run_tick_a_store_exception_for_one_user_does_not_block_the_next(fake_expo, monkeypatch):
    """Regression test for the fix that moved store.get_store/push_tokens
    inside run_tick's per-user try block: before that fix, an exception raised
    there (e.g. a locked/corrupt SQLite file) happened OUTSIDE the try and
    aborted the whole tick, so a later user in the loop (u2 here) would never
    be reached at all."""
    calls, _ = fake_expo
    u1 = _make_user("broken@example.com")
    u2 = _make_user("healthy@example.com")
    store.get_store(u2["user_id"]).add_push_token("ExponentPushToken[ok2]", "ios")
    store.get_store(u2["user_id"]).add_tasks([{"task": "Task C", "due": "2020-01-01"}])
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 0))

    real_get_store = store.get_store
    def flaky_get_store(user_id):
        if user_id == u1["user_id"]:
            raise RuntimeError("simulated store failure")
        return real_get_store(user_id)
    monkeypatch.setattr(store, "get_store", flaky_get_store)

    push.run_tick()

    bodies = [c[1]["body"] for c in calls]
    assert any("Task C" in b for b in bodies)


def test_run_tick_prunes_a_token_on_genuine_invalid_token_error(fake_expo, monkeypatch):
    _, state = fake_expo
    state["mode"] = "invalid_token"
    u = _make_user()
    s = store.get_store(u["user_id"])
    s.add_push_token("ExponentPushToken[dead]", "ios")
    s.add_tasks([{"task": "Overdue thing", "due": "2020-01-01"}])
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 0))

    push.run_tick()

    assert s.push_tokens() == []


def test_run_tick_does_not_prune_a_token_on_transient_failure(fake_expo, monkeypatch):
    """A network blip or generic Expo error must not permanently delete a
    still-valid registration — only a genuine invalid-token response should."""
    _, state = fake_expo
    state["mode"] = "other_error"
    u = _make_user()
    s = store.get_store(u["user_id"])
    s.add_push_token("ExponentPushToken[flaky]", "ios")
    s.add_tasks([{"task": "Overdue thing", "due": "2020-01-01"}])
    _freeze(monkeypatch, datetime(2026, 8, 31, 7, 0))

    push.run_tick()

    assert s.push_tokens() == ["ExponentPushToken[flaky]"]
    # not logged as sent either, so it's retried (not silently dropped) next tick
    assert s.has_pushed("overdue_task", s.open_tasks()[0]["id"]) is False


def test_start_scheduler_is_a_no_op_under_pytest():
    """PYTEST_CURRENT_TEST is always set while pytest is running a test — this
    must prevent a real background thread from starting, or every test run
    would leak a live scheduler ticking every 5 minutes."""
    assert os.environ.get("PYTEST_CURRENT_TEST")  # sanity: confirms the guard's premise holds here
    push.start_scheduler()  # must not raise, must not start a real thread
    assert push._scheduler is None


def test_shutdown_scheduler_is_a_no_op_when_never_started():
    push._scheduler = None
    push.shutdown_scheduler()  # must not raise
    assert push._scheduler is None
