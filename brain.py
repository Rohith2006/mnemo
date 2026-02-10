"""
Telegram-free core of the PA: config, LLM calls, extraction, reminder
detection, digests, and reply generation. Shared by pa.py (Telegram) and
web.py (local UI) — built incrementally across stages 5-7 of the rebuild.
"""

import os
import re
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic

try:  # optional local .env
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Anthropic-native: a local proxy (opencode) fronting the user's Claude subscription.
# The SDK also reads ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL from the env automatically.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "x")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:3456")
MODEL = os.getenv("PA_MODEL", "claude-opus-4-8")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)


# ── LLM helpers ─────────────────────────────────────────────────────────────
def call_llm(messages: list[dict], temperature: float = 0.3, max_tokens: int = 512) -> str:
    """
    Accepts OpenAI-style messages (with optional leading system messages) and calls
    the Anthropic Messages API. `system` is a separate top-level param; only user/
    assistant turns go in `messages`. temperature is accepted for call-site
    compatibility but NOT forwarded — Opus 4.8 rejects sampling params.
    """
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    convo = [{"role": m["role"], "content": m["content"]}
             for m in messages if m.get("role") in ("user", "assistant")]
    if not convo:
        convo = [{"role": "user", "content": ""}]
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
        '  "mood": {"score": <1-10>, "note": "..."} or null\n'
        "}\n"
        "Rules: omit empty arrays' contents rather than inventing. Resolve relative dates "
        "('tomorrow 6pm') to absolute ISO8601 in the user's timezone. Use null for unknown due. "
        "habits = things done repeatedly (running, journaling, gym, meditation). "
        "Skip greetings/small talk.\n\n"
        f"EXISTING OPEN TASKS: {open_tasks}\n"
        f"KNOWN HABITS: {habit_names}\n\n"
        f"User: {user_msg}\nAssistant: {assistant_msg}"
    )
    data = parse_json(call_llm([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=600))
    return data if isinstance(data, dict) else {}


def apply_extraction(store, data: dict) -> dict:
    changed = {"facts": [], "log": [], "tasks": [], "done": [], "habits": [], "mood": None}
    if not data:
        return changed
    if isinstance(data.get("facts"), list):
        changed["facts"] = store.add_facts([f for f in data["facts"] if isinstance(f, str)])
    if isinstance(data.get("log"), list):
        changed["log"] = store.add_log([e for e in data["log"] if isinstance(e, dict)])
    if isinstance(data.get("tasks_new"), list):
        changed["tasks"] = store.add_tasks([e for e in data["tasks_new"] if isinstance(e, dict)])
    if isinstance(data.get("tasks_done"), list):
        changed["done"] = store.complete_tasks([m for m in data["tasks_done"] if isinstance(m, str)])
    if isinstance(data.get("habits_done"), list):
        for name in data["habits_done"]:
            if isinstance(name, str) and name.strip():
                changed["habits"].append(store.log_habit(name))
    mood = data.get("mood")
    if isinstance(mood, dict) and mood.get("score") is not None:
        try:
            changed["mood"] = store.add_journal(int(mood["score"]), mood.get("note", ""))
        except (TypeError, ValueError):
            pass
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
        "Compute seconds precisely (30 min=1800, 2 h=7200, 'tomorrow 9am'=seconds until then).\n"
        'If NO: {"is_reminder": false}'
    )
    data = parse_json(call_llm([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=150))
    if isinstance(data, dict) and data.get("is_reminder") and data.get("task") and data.get("seconds_from_now", 0) > 0:
        return {"task": data["task"], "seconds": int(data["seconds_from_now"])}
    return None


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
        "fabricate facts. When the user shares info, acknowledge it warmly. Light markdown is fine.\n\n"
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
        "below; never invent facts. If there's little to say, keep it to a line or two. Warm tone, "
        "light markdown and emoji.\n\n"
        f"{ask}\n\nDATA:\n{json.dumps(facts, indent=2, ensure_ascii=False)}"
    )
    return call_llm([{"role": "user", "content": prompt}], temperature=0.6, max_tokens=500)
