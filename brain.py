"""
Telegram-free core of the PA: config, LLM calls, extraction, reminder
detection, digests, and reply generation. Shared by pa.py (Telegram) and
web.py (local UI) — built incrementally across stages 5-7 of the rebuild.
"""

import os
import re
import json

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
