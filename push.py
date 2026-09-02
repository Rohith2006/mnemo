"""Push notifications — proactive overdue-task and digest alerts. Additive to
the reminder system in mobile/src/notifications/index.ts (which stays
client-side-scheduled and untouched); this is the server-initiated half.

Three trigger kinds, evaluated once per scheduler tick against every
push-eligible user:
  - overdue_task   — fires once ever per task, the first tick it's overdue.
                      More than 2 overdue-and-unpushed tasks in one tick are
                      coalesced into a single combined notification instead
                      of one push each, to avoid a notification burst (e.g.
                      the first tick after this feature deploys against a
                      database that already has several overdue tasks).
  - morning_digest — fires once daily, the first tick in [08:00, 20:00) local.
                      Bounded above by EVENING_HOUR: a stale "Good morning"
                      push landing after 8pm would be worse than not sending
                      one at all — the evening digest already covers the same
                      day, so a day that never gets a tick in this window
                      simply has its morning digest skipped, not queued up.
  - evening_digest — fires once daily, the first tick at/after 20:00 local,
                      with an at-risk-habit line folded into the same
                      notification body rather than sent separately.
"""

import logging
import os
from datetime import datetime

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

import brain
import store

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

MORNING_HOUR = 8
EVENING_HOUR = 20

# Coalesce overdue-task pushes into one combined notification once there are
# more than this many pending in a single tick, rather than sending one push
# per task — see the module docstring's overdue_task entry.
OVERDUE_COALESCE_THRESHOLD = 2

# send_push's three possible outcomes. A genuinely bad token (Expo told us so)
# is the only case that should ever prune a registration — anything else
# (network blip, timeout, non-2xx, malformed JSON, any other Expo error code)
# is transient and must be left alone so the token gets tried again next tick.
SEND_OK = "ok"
SEND_INVALID_TOKEN = "invalid_token"
SEND_TRANSIENT = "transient"

# Expo error codes that mean the token itself is dead and should be dropped.
# https://docs.expo.dev/push-notifications/sending-notifications/#individual-errors
_INVALID_TOKEN_ERRORS = {"DeviceNotRegistered", "MismatchSenderId"}


def send_push(token: str, title: str, body: str) -> str:
    """POST one notification to Expo's push service. Never raises. Returns one
    of SEND_OK / SEND_INVALID_TOKEN / SEND_TRANSIENT — see the module-level
    constants' docstring for what distinguishes them."""
    try:
        resp = httpx.post(
            _EXPO_PUSH_URL,
            json={"to": token, "title": title, "body": body},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code < 200 or resp.status_code >= 300:
            logger.warning("push send got HTTP %s from Expo for token ...%s", resp.status_code, token[-8:])
            return SEND_TRANSIENT
        data = resp.json().get("data", {})
        if data.get("status") == "ok":
            return SEND_OK
        error = (data.get("details") or {}).get("error")
        if error in _INVALID_TOKEN_ERRORS:
            return SEND_INVALID_TOKEN
        logger.warning("push send got Expo error %r for token ...%s", error, token[-8:])
        return SEND_TRANSIENT
    except Exception as e:
        logger.warning("push send raised for token ...%s: %s", token[-8:], e)
        return SEND_TRANSIENT


def _overdue_pushes(user_store, tz):
    """Yield one (ref_ids, title, body) push per pending overdue task, unless
    more than OVERDUE_COALESCE_THRESHOLD are pending at once — in which case
    yield a single combined push covering all of them, to avoid a notification
    burst. ref_ids is always a list, even for the single-task case, so the
    caller can log every covered task to push_log uniformly."""
    pending = [t for t in user_store.overdue_tasks(tz) if not user_store.has_pushed("overdue_task", t["id"])]
    if not pending:
        return
    if len(pending) > OVERDUE_COALESCE_THRESHOLD:
        oldest = pending[0]["task"]
        body = f'{len(pending)} tasks are overdue, including "{oldest}".'
        yield [t["id"] for t in pending], "Overdue", body
        return
    for t in pending:
        yield [t["id"]], "Overdue", f'"{t["task"]}" is overdue.'


def _digest_pushes(user_store, tz, now):
    """Yield (kind, ref_id, title, body) for any digest not yet pushed today.
    Reuses the same digest cache /api/digests already reads/writes
    (get_cached_digest/save_digest, keyed "morning"/"evening" — no "_digest"
    suffix, unlike push_log's dedup kind strings below) so a push sent at
    08:05 and an in-app "Briefing" tap at 09:00 the same day show identical
    text instead of two independent LLM calls potentially disagreeing. This
    means a digest the user already pulled earlier in the day gets pushed
    as-is rather than regenerated — deliberately the more coherent behavior,
    and invalidate_today_digests() already expires the cache on any new
    capture, so it doesn't go stale."""
    today = now.date().isoformat()
    # Bounded above by EVENING_HOUR: a stale "Good morning" push after 8pm
    # would be worse than not sending one — the evening digest covers the
    # same day. If no tick lands in this window on a given day, that day's
    # morning digest is simply skipped, not queued.
    if MORNING_HOUR <= now.hour < EVENING_HOUR and not user_store.has_pushed("morning_digest", today):
        text = user_store.get_cached_digest("morning", today)
        if text is None:
            text = brain.build_digest(user_store, tz, "morning")
            user_store.save_digest("morning", today, text)
        yield "morning_digest", today, "Good morning", text
    if now.hour >= EVENING_HOUR and not user_store.has_pushed("evening_digest", today):
        text = user_store.get_cached_digest("evening", today)
        if text is None:
            text = brain.build_digest(user_store, tz, "evening")
            user_store.save_digest("evening", today, text)
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
        try:
            user_store = store.get_store(user_id)
            tokens = user_store.push_tokens()
            if not tokens:
                continue

            tz = store.registry.tz(user_id)
            now = datetime.now(tz)

            for ref_ids, title, body in _overdue_pushes(user_store, tz):
                _send_and_log(user_store, tokens, "overdue_task", ref_ids, title, body)

            for kind, ref_id, title, body in _digest_pushes(user_store, tz, now):
                _send_and_log(user_store, tokens, kind, [ref_id], title, body)
        except Exception:
            logger.exception("push tick failed for user %s", user_id)
            continue  # this user's tick failed; the rest of the loop still runs


def _send_and_log(user_store, tokens: list[str], kind: str, ref_ids: list[str], title: str, body: str) -> None:
    # send_push never raises — a transient failure just means "try again next
    # tick"; only a genuine Expo-reported invalid-token result prunes anything.
    sent_any = False
    for token in tokens:
        result = send_push(token, title, body)
        if result == SEND_OK:
            sent_any = True
        elif result == SEND_INVALID_TOKEN:
            user_store.remove_push_token(token)
    if sent_any:
        for ref_id in ref_ids:
            user_store.log_push_sent(kind, ref_id)


_scheduler = None


def start_scheduler() -> None:
    """Called once from api/main.py's startup. Never starts a real background
    thread under pytest (PYTEST_CURRENT_TEST is set by pytest itself for the
    duration of every test) — tests call run_tick() directly instead, so the
    suite stays deterministic and no thread leaks past the test process."""
    global _scheduler
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.info("push scheduler skipped: running under pytest")
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(run_tick, "interval", minutes=5, id="push_tick")
    _scheduler.start()
    logger.info("push scheduler started: ticking every 5 minutes")


def shutdown_scheduler() -> None:
    """Called once from api/main.py's lifespan teardown. No-op if the
    scheduler was never started (e.g. under pytest)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
