"""Push notifications — proactive overdue-task and digest alerts. Additive to
the reminder system in mobile/src/notifications/index.ts (which stays
client-side-scheduled and untouched); this is the server-initiated half.

Three trigger kinds, evaluated once per scheduler tick against every
push-eligible user:
  - overdue_task   — fires once ever per task, the first tick it's overdue.
  - morning_digest — fires once daily, the first tick at/after 08:00 local.
  - evening_digest — fires once daily, the first tick at/after 20:00 local,
                      with an at-risk-habit line folded into the same
                      notification body rather than sent separately.
"""

import os
from datetime import datetime

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

import brain
import store

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

MORNING_HOUR = 8
EVENING_HOUR = 20


def send_push(token: str, title: str, body: str) -> bool:
    """POST one notification to Expo's push service. Never raises — a
    network error or a malformed Expo response both just mean "not sent"."""
    try:
        resp = httpx.post(
            _EXPO_PUSH_URL,
            json={"to": token, "title": title, "body": body},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = resp.json().get("data", {})
        return data.get("status") == "ok"
    except Exception:
        return False


def _overdue_pushes(user_store, tz):
    for t in user_store.overdue_tasks(tz):
        if not user_store.has_pushed("overdue_task", t["id"]):
            yield t["id"], "Overdue", f'"{t["task"]}" is overdue.'


def _digest_pushes(user_store, tz, now):
    today = now.date().isoformat()
    if now.hour >= MORNING_HOUR and now.hour < EVENING_HOUR and not user_store.has_pushed("morning_digest", today):
        yield "morning_digest", today, "Good morning", brain.build_digest(user_store, tz, "morning")
    if now.hour >= EVENING_HOUR and not user_store.has_pushed("evening_digest", today):
        text = brain.build_digest(user_store, tz, "evening")
        at_risk = user_store.habits_at_risk(tz)
        if at_risk:
            names = ", ".join(h["name"] for h in at_risk)
            text = f"{text}\n\nStill at risk today: {names}."
        yield "evening_digest", today, "Good evening", text


def run_tick() -> None:
    """One scheduler tick: evaluate every push-eligible user against all three
    trigger kinds and send+log anything new. One user's exception, or one
    token's failed send, must never stop the tick for anyone else."""
    for user_id, user in store.registry.all().items():
        if not user.get("push_enabled"):
            continue
        user_store = store.get_store(user_id)
        tokens = user_store.push_tokens()
        if not tokens:
            continue
        try:
            tz = store.registry.tz(user_id)
            now = datetime.now(tz)

            for ref_id, title, body in _overdue_pushes(user_store, tz):
                _send_and_log(user_store, tokens, "overdue_task", ref_id, title, body)

            for kind, ref_id, title, body in _digest_pushes(user_store, tz, now):
                _send_and_log(user_store, tokens, kind, ref_id, title, body)
        except Exception:
            continue  # this user's tick failed; the rest of the loop still runs


def _send_and_log(user_store, tokens: list[str], kind: str, ref_id: str, title: str, body: str) -> None:
    # send_push already catches everything internally and returns False on
    # any failure, so nothing here can raise — no try/except needed.
    sent_any = False
    for token in tokens:
        if send_push(token, title, body):
            sent_any = True
        else:
            user_store.remove_push_token(token)
    if sent_any:
        user_store.log_push_sent(kind, ref_id)


_scheduler = None


def start_scheduler() -> None:
    """Called once from api/main.py's startup. Never starts a real background
    thread under pytest (PYTEST_CURRENT_TEST is set by pytest itself for the
    duration of every test) — tests call run_tick() directly instead, so the
    suite stays deterministic and no thread leaks past the test process."""
    global _scheduler
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(run_tick, "interval", minutes=5, id="push_tick")
    _scheduler.start()
