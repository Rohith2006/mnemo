"""Tests for api/ — the FastAPI backend behind the mobile app. No network calls;
the LLM is mocked via brain.call_llm exactly like test_brain.py does, and every
test gets an isolated tmp-path SQLite DB via conftest's autouse `isolated_db`."""

import json
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import groq
import httpx
import pytest
from fastapi.testclient import TestClient

import brain
import store
from api.main import app

client = TestClient(app)


class FakeLLM:
    """Dispatches brain.call_llm based on which prompt shape it's given, so one
    monkeypatch can serve extract/detect_reminder/build_reply/build_digest."""

    def __init__(self):
        self.extraction = {}
        self.reminder = {"is_reminder": False}
        self.reply = "Got it."
        self.digest = "Nothing much going on."
        self.calls = 0
        self.history: list[str] = []  # every prompt text seen, for assertions on what was sent

    def __call__(self, messages, **kwargs):
        self.calls += 1
        text = " ".join(m.get("content", "") for m in messages)
        self.history.append(text)
        if "memory engine of a personal assistant" in text:
            return json.dumps(self.extraction)
        if "ask to be reminded" in text:
            return json.dumps(self.reminder)
        if "messaging the user unprompted" in text:
            return self.digest
        return self.reply


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(brain, "call_llm", fake)
    return fake


@pytest.fixture
def auth_headers(fake_llm):
    r = client.post("/auth/signup", json={"email": "a@example.com", "password": "password123", "name": "A"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── auth ──────────────────────────────────────────────────────────────────────
def test_signup_then_login():
    r = client.post("/auth/signup", json={"email": "u@example.com", "password": "password123"})
    assert r.status_code == 201
    signup_user = r.json()["user"]
    assert signup_user["email"] == "u@example.com"

    r2 = client.post("/auth/login", json={"email": "u@example.com", "password": "password123"})
    assert r2.status_code == 200
    assert r2.json()["user"]["user_id"] == signup_user["user_id"]


def test_signup_duplicate_email_rejected():
    client.post("/auth/signup", json={"email": "dup@example.com", "password": "password123"})
    r = client.post("/auth/signup", json={"email": "dup@example.com", "password": "password123"})
    assert r.status_code == 409


def test_login_wrong_password_rejected():
    client.post("/auth/signup", json={"email": "wp@example.com", "password": "password123"})
    r = client.post("/auth/login", json={"email": "wp@example.com", "password": "nope"})
    assert r.status_code == 401


def test_login_unknown_email_rejected():
    r = client.post("/auth/login", json={"email": "nope@example.com", "password": "whatever1"})
    assert r.status_code == 401


def test_protected_endpoint_requires_token():
    assert client.get("/api/dashboard").status_code == 401


def test_protected_endpoint_rejects_garbage_token():
    r = client.get("/api/dashboard", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


# ── capture (the non-chatbot path) ───────────────────────────────────────────
def test_capture_returns_receipt_not_a_chat_reply(auth_headers, fake_llm):
    fake_llm.extraction = {"facts": ["Lives in Bengaluru"], "log": [{"key": "run_km", "value": 5}]}
    r = client.post("/api/capture", json={"text": "ran 5k, live in Bengaluru"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["facts"] == ["Lives in Bengaluru"]
    assert body["log"][0]["key"] == "run_km"
    assert body["reminder"] is None
    assert "reply" not in body  # capture is a receipt, not a conversation


def test_capture_receipt_reports_updated_and_removed_facts(auth_headers, fake_llm):
    fake_llm.extraction = {"facts": ["Lives in Bengaluru", "Vegetarian"]}
    client.post("/api/capture", json={"text": "i live in bengaluru, im vegetarian"}, headers=auth_headers)

    fake_llm.extraction = {
        "facts_update": [{"old": "bengaluru", "new": "Lives in Dubai"}],
        "facts_remove": ["vegetarian"],
    }
    r = client.post("/api/capture", json={"text": "moved to dubai, eating meat now"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["facts_updated"] == ["Lives in Dubai"]
    assert body["facts_removed"] == ["Vegetarian"]
    assert body["facts"] == []


def test_capture_detects_and_schedules_reminder(auth_headers, fake_llm):
    fake_llm.reminder = {"is_reminder": True, "task": "call mom", "seconds_from_now": 1800}
    r = client.post("/api/capture", json={"text": "remind me to call mom in 30 min"}, headers=auth_headers)
    assert r.status_code == 200
    reminder = r.json()["reminder"]
    assert reminder["task"] == "call mom"

    listed = client.get("/api/reminders", headers=auth_headers).json()
    assert len(listed) == 1 and listed[0]["id"] == reminder["id"]


def test_capture_persists_into_dashboard(auth_headers, fake_llm):
    fake_llm.extraction = {"tasks_new": [{"task": "Submit report", "due": None}]}
    client.post("/api/capture", json={"text": "need to submit report"}, headers=auth_headers)
    dash = client.get("/api/dashboard", headers=auth_headers).json()
    assert [t["task"] for t in dash["tasks"]] == ["Submit report"]


def test_capture_requires_auth():
    r = client.post("/api/capture", json={"text": "hi"})
    assert r.status_code == 401


def test_llm_unreachable_returns_clean_502_not_a_raw_500(auth_headers, monkeypatch):
    """A dropped connection to the LLM backend must produce a clean, CORS-safe
    JSON error rather than an unhandled exception (which browsers report as a
    bare CORS failure, masking the real cause)."""
    def boom(*a, **k):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "http://127.0.0.1:3456/v1/messages"))
    monkeypatch.setattr(brain, "call_llm", boom)

    r = client.post("/api/capture", json={"text": "hi"}, headers=auth_headers)
    assert r.status_code == 502
    assert "detail" in r.json()


def test_groq_unreachable_also_returns_clean_502(auth_headers, monkeypatch):
    """Same as above but for the Groq provider's own exception hierarchy — both
    are registered on the app since LLM_PROVIDER picks which is actually in use."""
    def boom(*a, **k):
        raise groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
    monkeypatch.setattr(brain, "call_llm", boom)

    r = client.post("/api/capture", json={"text": "hi"}, headers=auth_headers)
    assert r.status_code == 502
    assert "detail" in r.json()


# ── chat (secondary, conversational) ─────────────────────────────────────────
def test_chat_without_conversation_id_creates_one(auth_headers, fake_llm):
    fake_llm.reply = "Nice, keep it up!"
    r = client.post("/api/chat", json={"message": "ran 5k today"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Nice, keep it up!"
    assert body["conversation_id"]


def test_chat_with_conversation_id_continues_it(auth_headers, fake_llm):
    fake_llm.reply = "First reply"
    first = client.post("/api/chat", json={"message": "First message"}, headers=auth_headers)
    conversation_id = first.json()["conversation_id"]

    fake_llm.reply = "Second reply"
    second = client.post(
        "/api/chat",
        json={"message": "Second message", "conversation_id": conversation_id},
        headers=auth_headers,
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    messages = client.get(f"/api/conversations/{conversation_id}/messages", headers=auth_headers).json()
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "First message"),
        ("assistant", "First reply"),
        ("user", "Second message"),
        ("assistant", "Second reply"),
    ]


def test_chat_with_unknown_conversation_id_404s(auth_headers, fake_llm):
    r = client.post(
        "/api/chat", json={"message": "hi", "conversation_id": "no-such-id"}, headers=auth_headers
    )
    assert r.status_code == 404


def test_chat_with_empty_string_conversation_id_404s_rather_than_creating_new(auth_headers, fake_llm):
    # An empty string is falsy but not None — a plain `if body.conversation_id:`
    # check would treat it the same as "omitted" and silently start a new
    # conversation instead of 404ing, which is exactly the "silent fallback"
    # the global constraints rule out.
    r = client.post(
        "/api/chat", json={"message": "hi", "conversation_id": ""}, headers=auth_headers
    )
    assert r.status_code == 404


def test_chat_caps_llm_history_to_last_20_messages(auth_headers, fake_llm):
    fake_llm.reply = "ok"
    conversation_id = client.post(
        "/api/chat", json={"message": "message 0"}, headers=auth_headers
    ).json()["conversation_id"]
    for i in range(1, 12):
        client.post(
            "/api/chat", json={"message": f"message {i}", "conversation_id": conversation_id},
            headers=auth_headers,
        )
    # By the 12th call (i=11), 22 prior messages exist (11 turns * 2). Capped
    # to the last 20, the oldest turn ("message 0" and its reply) must have
    # dropped out of what's sent to the LLM, while a recent one is still in.
    last_prompt = [c for c in fake_llm.history if "warm, proactive personal assistant" in c][-1]
    assert "message 0" not in last_prompt
    assert "message 10" in last_prompt


def test_chat_drops_orphaned_trailing_user_message_from_llm_history(auth_headers, fake_llm, monkeypatch):
    """If a prior turn's LLM call failed after the user message was committed
    but before the assistant reply got written, the conversation's stored
    history ends in an unanswered "user" turn. The next turn must drop that
    orphaned entry before appending its own user message, rather than sending
    the LLM two consecutive "user"-role entries."""
    fake_llm.reply = "First reply"
    first = client.post("/api/chat", json={"message": "First message"}, headers=auth_headers)
    conversation_id = first.json()["conversation_id"]

    user_id = client.get("/api/me", headers=auth_headers).json()["user_id"]
    store.get_store(user_id).add_message(
        conversation_id, "user", "some later message that never got a reply"
    )

    captured_messages = []
    underlying = fake_llm

    def spying_llm(messages, **kwargs):
        captured_messages.append(messages)
        return underlying(messages, **kwargs)

    monkeypatch.setattr(brain, "call_llm", spying_llm)
    fake_llm.reply = "Second reply"

    r = client.post(
        "/api/chat",
        json={"message": "Second message", "conversation_id": conversation_id},
        headers=auth_headers,
    )
    assert r.status_code == 200

    reply_calls = [
        m for m in captured_messages
        if any("warm, proactive personal assistant" in msg.get("content", "") for msg in m)
    ]
    assert reply_calls, "expected build_reply's LLM call to have been captured"
    roles = [msg["role"] for msg in reply_calls[-1]]
    consecutive_user_pairs = [
        (a, b) for a, b in zip(roles, roles[1:]) if a == "user" and b == "user"
    ]
    assert not consecutive_user_pairs, f"found consecutive user-role entries in {roles}"


# ── conversations ─────────────────────────────────────────────────────────────
def _second_user_headers(fake_llm):
    r = client.post("/auth/signup", json={"email": "b@example.com", "password": "password123", "name": "B"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_conversations_empty_when_none_exist(auth_headers):
    r = client.get("/api/conversations", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_conversation_lifecycle_via_chat_then_list_then_messages(auth_headers, fake_llm):
    fake_llm.reply = "Sure thing!"
    r = client.post("/api/chat", json={"message": "Help me plan my day"}, headers=auth_headers)
    conversation_id = r.json()["conversation_id"]

    listed = client.get("/api/conversations", headers=auth_headers).json()
    assert len(listed) == 1
    assert listed[0]["id"] == conversation_id
    assert listed[0]["title"] == "Help me plan my day"

    messages = client.get(f"/api/conversations/{conversation_id}/messages", headers=auth_headers).json()
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Help me plan my day"),
        ("assistant", "Sure thing!"),
    ]


def test_get_messages_404s_for_unknown_conversation(auth_headers):
    r = client.get("/api/conversations/no-such-id/messages", headers=auth_headers)
    assert r.status_code == 404


def test_get_messages_404s_for_another_users_conversation(auth_headers, fake_llm):
    other_headers = _second_user_headers(fake_llm)
    r = client.post("/api/chat", json={"message": "My private chat"}, headers=other_headers)
    conversation_id = r.json()["conversation_id"]

    r2 = client.get(f"/api/conversations/{conversation_id}/messages", headers=auth_headers)
    assert r2.status_code == 404


def test_rename_conversation(auth_headers, fake_llm):
    r = client.post("/api/chat", json={"message": "First title"}, headers=auth_headers)
    conversation_id = r.json()["conversation_id"]

    renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": "Better title"},
                            headers=auth_headers)
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Better title"


def test_rename_unknown_conversation_404s(auth_headers):
    r = client.patch("/api/conversations/no-such-id", json={"title": "New title"}, headers=auth_headers)
    assert r.status_code == 404


def test_delete_conversation(auth_headers, fake_llm):
    r = client.post("/api/chat", json={"message": "Delete me"}, headers=auth_headers)
    conversation_id = r.json()["conversation_id"]

    deleted = client.delete(f"/api/conversations/{conversation_id}", headers=auth_headers)
    assert deleted.status_code == 204
    assert client.get("/api/conversations", headers=auth_headers).json() == []


def test_delete_unknown_conversation_404s(auth_headers):
    r = client.delete("/api/conversations/no-such-id", headers=auth_headers)
    assert r.status_code == 404


# ── tasks / habits direct actions (no LLM involved) ──────────────────────────
def test_add_and_complete_task_without_llm(auth_headers):
    r = client.post("/api/tasks", json={"task": "Buy milk"}, headers=auth_headers)
    assert r.status_code == 201
    task_id = r.json()[0]["id"]

    done = client.post(f"/api/tasks/{task_id}/complete", headers=auth_headers)
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert client.get("/api/tasks", headers=auth_headers).json() == []


def test_complete_unknown_task_404s(auth_headers):
    r = client.post("/api/tasks/does-not-exist/complete", headers=auth_headers)
    assert r.status_code == 404


def test_completed_task_appears_in_dashboard_completed_log(auth_headers):
    r = client.post("/api/tasks", json={"task": "Buy milk"}, headers=auth_headers)
    task_id = r.json()[0]["id"]
    client.post(f"/api/tasks/{task_id}/complete", headers=auth_headers)

    dash = client.get("/api/dashboard", headers=auth_headers).json()
    assert dash["tasks"] == []
    assert [t["task"] for t in dash["completed"]] == ["Buy milk"]
    assert dash["completed"][0]["status"] == "done"
    assert dash["completed"][0]["done_at"] is not None


def test_reopen_task_moves_it_back_to_open(auth_headers):
    r = client.post("/api/tasks", json={"task": "Buy milk"}, headers=auth_headers)
    task_id = r.json()[0]["id"]
    client.post(f"/api/tasks/{task_id}/complete", headers=auth_headers)

    reopened = client.post(f"/api/tasks/{task_id}/reopen", headers=auth_headers)
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"

    dash = client.get("/api/dashboard", headers=auth_headers).json()
    assert [t["task"] for t in dash["tasks"]] == ["Buy milk"]
    assert dash["completed"] == []


def test_reopen_unknown_task_404s(auth_headers):
    r = client.post("/api/tasks/does-not-exist/reopen", headers=auth_headers)
    assert r.status_code == 404


def test_reopen_still_open_task_404s(auth_headers):
    r = client.post("/api/tasks", json={"task": "Buy milk"}, headers=auth_headers)
    task_id = r.json()[0]["id"]
    r = client.post(f"/api/tasks/{task_id}/reopen", headers=auth_headers)
    assert r.status_code == 404


def test_log_habit_direct_action(auth_headers):
    r = client.post("/api/habits/Running/log", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Running"
    assert r.json()["streak"] == 1


# ── digests (cached per user/kind/day) ───────────────────────────────────────
def test_digest_is_cached_within_same_day(auth_headers, fake_llm):
    fake_llm.digest = "Solid day."
    r1 = client.get("/api/digests/morning", headers=auth_headers)
    calls_after_first = fake_llm.calls
    r2 = client.get("/api/digests/morning", headers=auth_headers)
    assert r1.json()["text"] == r2.json()["text"] == "Solid day."
    assert fake_llm.calls == calls_after_first  # served from cache, no second LLM call


def test_digest_refresh_bypasses_cache(auth_headers, fake_llm):
    fake_llm.digest = "first"
    client.get("/api/digests/morning", headers=auth_headers)
    fake_llm.digest = "second"
    r = client.get("/api/digests/morning?refresh=true", headers=auth_headers)
    assert r.json()["text"] == "second"


def test_unknown_digest_kind_404s(auth_headers):
    r = client.get("/api/digests/nonsense", headers=auth_headers)
    assert r.status_code == 404


def test_capturing_new_data_invalidates_cached_digest(auth_headers, fake_llm):
    """Regression test: a digest fetched before any real data existed must not
    keep showing that same stale text once something has actually been
    captured — the mobile client never passes refresh=true on its own, so
    this has to happen automatically or the digest looks permanently broken."""
    fake_llm.digest = "stale, nothing going on"
    client.get("/api/digests/morning", headers=auth_headers)

    fake_llm.extraction = {"facts": ["Lives in Bengaluru"]}
    client.post("/api/capture", json={"text": "I live in Bengaluru"}, headers=auth_headers)

    fake_llm.digest = "fresh, reflects the new fact"
    r = client.get("/api/digests/morning", headers=auth_headers)
    assert r.json()["text"] == "fresh, reflects the new fact"


def test_completing_a_task_invalidates_cached_digest(auth_headers, fake_llm):
    """Same regression, but through the no-LLM direct-action path (Track tab's
    tap-to-complete) rather than through capture/chat's extraction."""
    r = client.post("/api/tasks", json={"task": "Buy milk"}, headers=auth_headers)
    task_id = r.json()[0]["id"]

    fake_llm.digest = "stale, milk still on the list"
    client.get("/api/digests/morning", headers=auth_headers)

    client.post(f"/api/tasks/{task_id}/complete", headers=auth_headers)

    fake_llm.digest = "fresh, milk is done"
    r = client.get("/api/digests/morning", headers=auth_headers)
    assert r.json()["text"] == "fresh, milk is done"


# ── account ───────────────────────────────────────────────────────────────────
def test_forget_wipes_data(auth_headers, fake_llm):
    fake_llm.extraction = {"facts": ["some fact"]}
    client.post("/api/capture", json={"text": "hi"}, headers=auth_headers)
    assert client.get("/api/dashboard", headers=auth_headers).json()["profile"] == ["some fact"]

    r = client.post("/api/forget", headers=auth_headers)
    assert r.status_code == 204
    assert client.get("/api/dashboard", headers=auth_headers).json()["profile"] == []


def test_dotenv_is_loaded_before_jwt_secret_is_read():
    """Regression: api.auth reads MNEMO_JWT_SECRET at import time and doesn't import brain
    (the only other place load_dotenv() runs), so api/main.py must call load_dotenv() itself
    before importing api.auth — otherwise the real .env value is silently ignored and the
    JWT secret falls back to the insecure default. Verified in a subprocess since Python
    caches module imports within one interpreter."""
    import os
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env"
    original = env_path.read_text() if env_path.exists() else None
    sentinel = "test-sentinel-secret-from-dotenv-file"
    try:
        env_path.write_text(f"MNEMO_JWT_SECRET={sentinel}\n")
        result = subprocess.run(
            [sys.executable, "-c", "import api.main as m; print(m.auth_module.JWT_SECRET)"],
            cwd=repo_root, env={k: v for k, v in os.environ.items() if k != "MNEMO_JWT_SECRET"},
            capture_output=True, text=True, timeout=15,
        )
    finally:
        if original is not None:
            env_path.write_text(original)
        else:
            env_path.unlink(missing_ok=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == sentinel


def test_update_me_changes_name_and_tz(auth_headers):
    r = client.patch("/api/me", json={"name": "New Name", "tz": "America/New_York"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
    assert r.json()["tz"] == "America/New_York"


def test_update_me_rejects_an_unknown_timezone(auth_headers):
    """An unusable tz is persisted-then-exploded everywhere downstream, since
    every authenticated route resolves ZoneInfo(user.tz) — reject it at the door
    rather than leaving the account unable to load anything."""
    r = client.patch("/api/me", json={"tz": "Mars/Olympus"}, headers=auth_headers)
    assert r.status_code == 422
    assert client.get("/api/dashboard", headers=auth_headers).status_code == 200


def test_forget_also_clears_reminders(auth_headers, fake_llm):
    """Settings promises "every ... reminder" is erased — so the pending
    reminders must go with the rest of the data, not outlive the wipe."""
    fake_llm.reminder = {"is_reminder": True, "task": "call mom", "seconds_from_now": 1800}
    client.post("/api/capture", json={"text": "remind me to call mom"}, headers=auth_headers)
    assert len(client.get("/api/reminders", headers=auth_headers).json()) == 1

    client.post("/api/forget", headers=auth_headers)

    assert client.get("/api/reminders", headers=auth_headers).json() == []


def test_capture_survives_seconds_quoted_as_a_string(auth_headers, fake_llm):
    fake_llm.reminder = {"is_reminder": True, "task": "call mom", "seconds_from_now": "1800"}
    r = client.post("/api/capture", json={"text": "remind me to call mom"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["reminder"]["task"] == "call mom"


def test_habit_captured_is_dated_in_the_users_timezone(auth_headers, fake_llm, foreign_tz):
    client.patch("/api/me", json={"tz": foreign_tz}, headers=auth_headers)
    fake_llm.extraction = {"habits_done": ["Running"]}
    client.post("/api/capture", json={"text": "went for a run"}, headers=auth_headers)

    habits = client.get("/api/habits", headers=auth_headers).json()
    assert habits[0]["last_done"] == datetime.now(ZoneInfo(foreign_tz)).date().isoformat()


def test_habit_logged_by_tap_is_dated_in_the_users_timezone(auth_headers, foreign_tz):
    client.patch("/api/me", json={"tz": foreign_tz}, headers=auth_headers)
    client.post("/api/habits/Running/log", headers=auth_headers)

    habits = client.get("/api/habits", headers=auth_headers).json()
    assert habits[0]["last_done"] == datetime.now(ZoneInfo(foreign_tz)).date().isoformat()


# ── push notifications ───────────────────────────────────────────────────────
def test_register_push_token(auth_headers):
    r = client.post(
        "/api/push/register",
        json={"token": "ExponentPushToken[abc]", "platform": "ios"},
        headers=auth_headers,
    )
    assert r.status_code == 204


def test_register_push_token_requires_auth():
    r = client.post(
        "/api/push/register",
        json={"token": "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]", "platform": "ios"},
    )
    assert r.status_code == 401


def test_me_includes_push_enabled_default_true(auth_headers):
    r = client.get("/api/me", headers=auth_headers)
    assert r.json()["push_enabled"] is True


def test_update_me_can_disable_push(auth_headers):
    r = client.patch("/api/me", json={"push_enabled": False}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["push_enabled"] is False
    assert client.get("/api/me", headers=auth_headers).json()["push_enabled"] is False
