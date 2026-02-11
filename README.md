# mnemo

A hyper-personalized AI assistant with **persistent long-term memory**. Unlike a
plain chatbot that forgets you the moment the tab closes, mnemo automatically
extracts, deduplicates, and stores what it learns about you across conversations —
your profile, habits, tasks, mood, and any data point worth tracking — and uses
that memory to give genuinely personal replies.

## What it does

- **Automatic memory** — after every turn, a structured LLM call extracts personal
  facts into typed buckets (profile / log / tasks / habits / mood). No "save" button.
- **Smart updates** — new information *updates* existing memories instead of piling
  up duplicates (e.g. a weight change overwrites the old value).
- **Proactive behavior** — morning briefing and evening review per user, streak-at-risk
  and overdue-task nudges, and natural-language reminders ("remind me at 3pm").
- **Persistent** — SQLite-backed (WAL mode), so memory survives restarts and supports
  real queries instead of rewriting a JSON blob on every change.
- **Two frontends, one brain** — a Telegram bot and a local web UI share the same
  core logic (`brain.py`) and storage (`store.py`); neither has its own copy of the
  LLM/extraction logic.

## Architecture

| File           | Role |
|----------------|------|
| `db.py`        | SQLite schema + connection layer (WAL mode, one file per install) |
| `store.py`     | Persistence layer — `UserStore` / `UserRegistry` / `ReminderStore` on top of `db.py` |
| `brain.py`     | Core logic — LLM client, fact extraction, reminder detection, reply + digest generation |
| `web.py`       | Local web UI — chat + live "what I'm tracking" dashboard |
| `pa.py`        | Telegram frontend — proactive PA with briefings, nudges, reminders |
| `tests/`       | pytest suite for `store.py` and `brain.py` — no network calls, LLM calls are mocked |

The LLM is called through the Anthropic Messages API via a local proxy
(`ANTHROPIC_BASE_URL`, configurable) — see `.env.example`.

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

cp .env.example .env    # then fill in your keys
```

## Run

```bash
# Local web UI (recommended) — then open http://127.0.0.1:8000
python web.py

# Telegram bot (needs TELEGRAM_BOT_TOKEN in .env)
python pa.py
```

## Testing

```bash
pytest
```

The suite covers `store.py`'s persistence logic and `brain.py`'s extraction/reply/
digest logic end-to-end against a real (tmp-path) SQLite database, with the LLM
client mocked — no network access or API key required to run it.

## Configuration

All secrets/settings are read from environment variables (or a local `.env`) —
copy `.env.example` to `.env` and fill in your own values. Nothing is hardcoded.
