"""
The shared core of mnemo: config, LLM calls, extraction, reminder detection,
digests, and reply generation. No HTTP/frontend dependency — called from api/.
"""

import os
import re
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic
import groq

try:  # optional local .env
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Two supported LLM providers, switched via LLM_PROVIDER (default "anthropic"):
#   anthropic — the Messages API, either https://api.anthropic.com with a real key,
#               or a local proxy (e.g. opencode) fronting a Claude subscription.
#   groq      — Groq's OpenAI-compatible chat-completions API. Useful as a free/fast
#               placeholder while an Anthropic key isn't set up yet.
# Both clients are constructed unconditionally at import (cheap — no network call)
# so either can be exercised/mocked in tests regardless of which is active.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "x")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:3456")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "x")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
groq_client = groq.Groq(api_key=GROQ_API_KEY)

if LLM_PROVIDER == "groq":
    MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
else:
    MODEL = os.getenv("PA_MODEL", "claude-sonnet-5")


# ── LLM helpers ─────────────────────────────────────────────────────────────
def call_llm(messages: list[dict], temperature: float = 0.3, max_tokens: int = 512) -> str:
    """
    Accepts OpenAI-style messages (with optional leading system messages) and calls
    whichever provider LLM_PROVIDER selects.
    """
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    convo = [{"role": m["role"], "content": m["content"]}
             for m in messages if m.get("role") in ("user", "assistant")]
    if not convo:
        convo = [{"role": "user", "content": ""}]

    if LLM_PROVIDER == "groq":
        groq_messages = ([{"role": "system", "content": system}] if system else []) + convo
        # reasoning_effort=low: the default Groq model (openai/gpt-oss-120b) is a
        # reasoning model that otherwise burns a chunk of max_tokens on a hidden
        # `reasoning` field before ever emitting `content` — at this app's tight
        # per-call budgets that risks truncating to empty output entirely.
        resp = groq_client.chat.completions.create(
            model=MODEL, messages=groq_messages, max_tokens=max_tokens, temperature=temperature,
            reasoning_effort="low",
        )
        return (resp.choices[0].message.content or "").strip()

    # Anthropic: `system` is a separate top-level param, not a message. temperature
    # is accepted for call-site compatibility but NOT forwarded — Opus 4.8 (an
    # earlier default model here) rejected sampling params; kept as-is for Anthropic.
    kwargs = {"model": MODEL, "max_tokens": max_tokens, "messages": convo}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def parse_json(raw: str):
    raw = re.sub(r"```(?:json)?|```", "", raw).strip()
    m = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def _upcoming_dates_table(now: datetime, days: int = 14) -> str:
    """
    A weekday-name -> ISO-date lookup for the next `days` days. Handing the model
    this table instead of making it compute "next Friday" from a raw date itself
    avoids the day-of-week arithmetic mistakes small/fast models occasionally make
    under time pressure (e.g. resolving "by Friday" to a Tuesday) — it only has to
    read a row, not calculate one.
    """
    lines = []
    for i in range(days):
        d = (now + timedelta(days=i)).date()
        label = "today" if i == 0 else "tomorrow" if i == 1 else d.strftime("%A")
        lines.append(f"{d.isoformat()} = {label}")
    return "\n".join(lines)


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DUE_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(.*)$")


def _correct_weekday_due(user_msg: str, due: str, now: datetime) -> str:
    """
    Even with the lookup table above, a low-effort model occasionally still gets
    day-of-week arithmetic wrong (observed: "by Friday" resolved to a Tuesday).
    When the message names exactly one weekday, don't trust the model's arithmetic
    at all — deterministically overwrite the date portion with the nearest
    matching weekday (today counts, since "by Friday" said on a Friday means
    today). Skipped when the message names zero or multiple weekdays, since which
    one the due date refers to is then genuinely ambiguous.
    """
    if not due:
        return due
    m = _DUE_DATE_RE.match(due)
    if not m:
        return due
    found = [w for w in _WEEKDAYS if re.search(rf"\b{w}\b", user_msg, re.IGNORECASE)]
    if len(found) != 1:
        return due
    today = now.date()
    delta = (_WEEKDAYS.index(found[0]) - today.weekday()) % 7
    correct_date = today + timedelta(days=delta)
    if m.group(1) == correct_date.isoformat():
        return due
    return correct_date.isoformat() + m.group(2)


def human_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours, mins = divmod(minutes, 60)
    if mins == 0:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{hours}h {mins}m"


# ── Structured extraction (one call → every bucket) ─────────────────────────
def extract(user_msg: str, assistant_msg: str, store, tz: ZoneInfo) -> dict:
    now = datetime.now(tz)
    open_tasks = [t["task"] for t in store.open_tasks()]
    habit_names = [h["name"] for h in store.active_habits()]
    known_facts = store.facts()

    prompt = (
        f"Current time: {now.strftime('%A %Y-%m-%d %H:%M')} ({tz}).\n\n"
        "You are the memory engine of a personal assistant. From the user+assistant turn "
        "below, extract anything worth tracking long-term. Be liberal about LOGGING measurable "
        "things (any category is allowed — health, fitness, sleep, food, money, study, work, "
        "mood, anything) but conservative about PROFILE facts (only stable, identity-level info).\n\n"
        "Return ONLY valid JSON, no prose:\n"
        "{\n"
        '  "facts": ["stable third-person fact about the user"],\n'
        '  "log": [{"category":"...","key":"snake_case_metric","value":<number or string>,"unit":"...","note":"..."}],\n'
        '  "tasks_new": [{"task":"...","due":"ISO8601 or null"}],\n'
        '  "tasks_done": ["substring of an existing open task the user just finished"],\n'
        '  "habits_done": ["name of a recurring habit the user did today"],\n'
        '  "mood": {"score": <1-10>, "note": "..."} or null,\n'
        '  "facts_update": [{"old":"substring of an existing fact","new":"its corrected replacement"}],\n'
        '  "facts_remove": ["substring of an existing fact that is no longer true"]\n'
        "}\n"
        "Rules: omit empty arrays' contents rather than inventing. Resolve relative dates "
        "('tomorrow 6pm', 'by Friday', 'next Monday') to absolute ISO8601 in the user's timezone "
        "by LOOKING UP the weekday name in the UPCOMING DATES table below — do not compute the "
        "weekday yourself. A bare weekday name and 'next <weekday>' mean the SAME thing: the "
        "closest matching date in the table that is still in the future (never skip an extra week "
        "just because the user said 'next'). Use null for unknown due. "
        "habits = things done repeatedly (running, journaling, gym, meditation). "
        "Skip greetings/small talk.\n"
        f"UPCOMING DATES:\n{_upcoming_dates_table(now)}\n\n"
        "Reconcile against EXISTING FACTS instead of piling up duplicates and contradictions: "
        "if this turn supersedes a known fact (moved city, changed job, new diet), put it in "
        "\"facts_update\"; if a known fact is simply no longer true with nothing replacing it, "
        "put it in \"facts_remove\"; only put genuinely NEW information in \"facts\". Never "
        "restate an existing fact. When unsure, leave the existing fact alone.\n\n"
        f"EXISTING FACTS: {known_facts}\n"
        f"EXISTING OPEN TASKS: {open_tasks}\n"
        f"KNOWN HABITS: {habit_names}\n\n"
        f"User: {user_msg}\nAssistant: {assistant_msg}"
    )
    data = parse_json(call_llm([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=600))
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("tasks_new"), list):
        for t in data["tasks_new"]:
            if isinstance(t, dict) and isinstance(t.get("due"), str):
                t["due"] = _correct_weekday_due(user_msg, t["due"], now)
    return data


def apply_extraction(store, data: dict, tz: ZoneInfo | None = None) -> dict:
    changed = {"facts": [], "facts_updated": [], "facts_removed": [],
               "log": [], "tasks": [], "done": [], "habits": [], "mood": None}
    if not data:
        return changed
    # Reconcile before adding: an update inserts the corrected fact, so a redundant
    # entry in "facts" for the same thing is then caught by add_facts' dedup.
    if isinstance(data.get("facts_update"), list):
        for item in data["facts_update"]:
            if not isinstance(item, dict):
                continue
            old_match, new_fact = item.get("old"), item.get("new")
            if not isinstance(old_match, str) or not isinstance(new_fact, str):
                continue
            updated = store.update_fact(old_match, new_fact)
            if updated:
                changed["facts_updated"].append(updated)
    if isinstance(data.get("facts_remove"), list):
        changed["facts_removed"] = store.remove_facts(
            [m for m in data["facts_remove"] if isinstance(m, str)]
        )
    if isinstance(data.get("facts"), list):
        changed["facts"] = store.add_facts([f for f in data["facts"] if isinstance(f, str)])
    if isinstance(data.get("log"), list):
        changed["log"] = store.add_log([e for e in data["log"] if isinstance(e, dict)])
    if isinstance(data.get("tasks_new"), list):
        changed["tasks"] = store.add_tasks([e for e in data["tasks_new"] if isinstance(e, dict)])
    if isinstance(data.get("tasks_done"), list):
        changed["done"] = store.complete_tasks([m for m in data["tasks_done"] if isinstance(m, str)])
    if isinstance(data.get("habits_done"), list):
        # Streaks count consecutive *local* days, so date the habit on the user's
        # calendar day rather than the server's — they can be a day apart.
        today = datetime.now(tz).date() if tz else None
        for name in data["habits_done"]:
            if isinstance(name, str) and name.strip():
                changed["habits"].append(store.log_habit(name, on=today))
    mood = data.get("mood")
    if isinstance(mood, dict) and mood.get("score") is not None:
        try:
            changed["mood"] = store.add_journal(int(mood["score"]), mood.get("note", ""))
        except (TypeError, ValueError):
            pass
    if tz and any(changed.values()):
        store.invalidate_today_digests(tz)
    return changed


# ── Reminder detection ──────────────────────────────────────────────────────
def detect_reminder(user_msg: str, tz: ZoneInfo) -> dict | None:
    now = datetime.now(tz)
    prompt = (
        f"Current date and time: {now.strftime('%A, %Y-%m-%d %H:%M')} ({tz})\n\n"
        "Does the message ask to be reminded about something ('remind me', 'don't let me "
        "forget', 'alert me', 'ping me')?\n\n"
        f"Message: {user_msg}\n\n"
        'If YES, respond with JSON only: {"is_reminder": true, "task": "<what>", "seconds_from_now": <int>}\n'
        "Compute seconds precisely (30 min=1800, 2 h=7200, 'tomorrow 9am'=seconds until then). If the "
        "message names a weekday ('Friday', 'next Monday'), look up its date in this table instead of "
        "computing the weekday yourself — a bare weekday name and 'next <weekday>' mean the SAME "
        "thing: the closest matching date below that is still in the future — then work out "
        f"seconds_from_now from that date:\n{_upcoming_dates_table(now)}\n\n"
        'If NO: {"is_reminder": false}'
    )
    data = parse_json(call_llm([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=150))
    if not isinstance(data, dict) or not data.get("is_reminder") or not data.get("task"):
        return None
    # LLM JSON is untrusted: the delay comes back quoted often enough that
    # comparing it to 0 directly would raise TypeError on an otherwise fine turn.
    try:
        seconds = int(float(data.get("seconds_from_now", 0)))
    except (TypeError, ValueError):
        return None
    return {"task": data["task"], "seconds": seconds} if seconds > 0 else None


# ── Reply generation ────────────────────────────────────────────────────────
def build_reply(store, user_message, history, tz, pending_reminders=None, new_reminder=None) -> str:
    pending = pending_reminders or []
    if pending:
        r_lines = [
            f'  - "{r["task"]}" fires {r["fire_at_dt"].astimezone(tz).strftime("%H:%M on %a %d %b")}'
            for r in pending
        ]
        reminders_block = "PENDING REMINDERS (already scheduled):\n" + "\n".join(r_lines)
    else:
        reminders_block = "PENDING REMINDERS: none."

    system_prompt = (
        f"You are a warm, proactive personal assistant. It is "
        f"{datetime.now(tz).strftime('%A %H:%M')} for the user.\n"
        "You actively track the user's life and help them stay organized. Reminders and memory are "
        "handled automatically by the system behind the scenes — NEVER say you can't track time or "
        "set reminders, and never claim you've saved or scheduled anything yourself.\n"
        "IMPORTANT: Reply with plain conversational text ONLY. You do NOT have tools and you do NOT "
        "write files. Never output 'Tool use', file paths, code fences for memory, or any narration "
        "of actions — just talk to the user naturally.\n"
        "Use what you know to personalize, give concrete suggestions, and gently coach — but NEVER "
        "fabricate facts. When the user shares info, acknowledge it warmly. Reply in PLAIN TEXT only — "
        "no markdown (no **bold**, no tables, no headers), no HTML tags like <br>. The client renders "
        "this as raw text, not formatted output. Use line breaks and emoji for structure instead.\n\n"
        f"=== WHAT YOU KNOW ===\n{store.summary()}\n=====================\n\n"
        f"=== {reminders_block}\n====================="
    )
    if new_reminder:
        fire_local = (datetime.now().astimezone() + timedelta(seconds=new_reminder["seconds"])).astimezone(tz)
        system_prompt += (
            f"\n\nSYSTEM ACTION: reminder saved — \"{new_reminder['task']}\" fires in "
            f"{human_duration(new_reminder['seconds'])} at {fire_local.strftime('%H:%M')}. Confirm it."
        )

    messages = [{"role": "system", "content": system_prompt}] + (history or []) + [
        {"role": "user", "content": user_message}
    ]
    return call_llm(messages, temperature=0.7, max_tokens=1024)


# ── Digests / insights ──────────────────────────────────────────────────────
def build_digest(store, tz: ZoneInfo, kind: str) -> str:
    now = datetime.now(tz)
    facts = {
        "now": now.strftime("%A %Y-%m-%d %H:%M"),
        "snapshot": store.summary(),
        "trends": store.trends(),
        "overdue_tasks": [t["task"] for t in store.overdue_tasks(tz)],
        "due_next_24h": [f'{t["task"]} @ {t["due_dt"].strftime("%H:%M %a")}' for t in store.tasks_due_within(24, tz)],
        "streaks_at_risk": [f'{h["name"]} (day {h["streak"]})' for h in store.habits_at_risk(tz)],
    }
    if kind == "morning":
        ask = ("Write a SHORT morning briefing. One-line greeting, then what's on today (due tasks, "
               "reminders), any streaks to protect, and ONE concrete suggestion. Warm, scannable.")
    elif kind == "evening":
        ask = ("Write a SHORT evening review. Reflect on what was logged today, surface ONE genuine "
               "pattern/insight from the data, note anything unfinished for tomorrow, end with light "
               "encouragement. Honest, not flattering.")
    else:
        ask = ("Give a concise insights update: the most useful patterns in this data right now and "
               "1-2 concrete, specific suggestions to make life more organized. No fluff.")
    prompt = (
        "You are a proactive personal assistant messaging the user unprompted. Use ONLY the data "
        "below; never invent facts. If there's little to say, keep it to a line or two. Warm tone. "
        "Reply in PLAIN TEXT only — no markdown (no **bold**, no tables, no headers), no HTML tags "
        "like <br>. The client renders this as raw text, not formatted output. Emoji are fine.\n\n"
        f"{ask}\n\nDATA:\n{json.dumps(facts, indent=2, ensure_ascii=False)}"
    )
    return call_llm([{"role": "user", "content": prompt}], temperature=0.6, max_tokens=500)
