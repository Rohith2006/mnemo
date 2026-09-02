# mnemo

A hyper-personalized AI assistant with **persistent long-term memory**. Unlike a
plain chatbot, mnemo automatically extracts, deduplicates, and stores what it
learns about you — profile, habits, tasks, mood, and any data point worth
tracking — and uses that memory to give personal replies and proactive insight.

The primary UI is a **mobile app** (`mobile/`, Expo/React Native), deliberately
**not chat-first**: its home screen is one-line quick-capture that returns a
structured receipt of what was understood, not a conversational reply. A
secondary Chat tab exists for open-ended conversation.

## What it does

- **Quick capture, not chat** — log anything in one line ("ran 5k, remind me to
  call mom at 6pm") and get back a structured receipt (facts/log/tasks/habits/
  mood/reminder) — no LLM chat reply on the primary path.
- **Automatic memory** — one structured LLM call per turn extracts into typed
  buckets. No "save" button.
- **Direct actions** — tap to complete a task or log a habit, no LLM involved.
- **On-device reminders** — the phone schedules a real local notification the
  moment a reminder is detected; no server push infrastructure required.
- **Proactive insight** — morning/evening/on-demand digests, streak/deadline
  alerts, computed live and shown in-app.
- **Push notifications** — an in-process scheduler ticks every few minutes and
  sends real Expo push notifications for overdue tasks and morning/evening
  digests, so proactive insight reaches the user without opening the app.
- **Multi-user** — email/password auth, JWT bearer tokens, per-user data.

## Architecture

| Path        | Role |
|-------------|------|
| `db.py`     | SQLite schema + connection layer (WAL mode) |
| `store.py`  | Persistence — `UserStore` / `UserRegistry` / `ReminderStore` on top of `db.py` |
| `brain.py`  | LLM client (Anthropic or Groq, via `LLM_PROVIDER`), extraction, reminder detection, reply + digest generation |
| `push.py`   | In-process APScheduler tick — sends real Expo push notifications for overdue tasks and morning/evening digests |
| `api/`      | FastAPI backend — auth, capture/chat (the core product split), tasks/habits, reminders, digests, push registration |
| `mobile/`   | Expo (React Native + TypeScript) app — the only frontend |
| `tests/`    | pytest suite — no network calls, LLM calls are mocked |

See `CLAUDE.md` for the full architecture writeup (layering rules, the
capture-vs-chat split, import-order gotchas, known limitations).

## Setup

```bash
# Backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # fill in an LLM key (Anthropic or Groq) + MNEMO_JWT_SECRET

# Mobile app
cd mobile && npm install
```

## Run

```bash
# Backend (LAN-reachable — the mobile app connects to this over wifi)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Mobile app
cd mobile && npx expo start        # scan the QR with Expo Go on your phone
npx expo start --web               # or preview in a browser at localhost:8081
```

In the app's login/signup screen, set Server URL to your machine's LAN IP
(e.g. `http://192.168.1.6:8000`) if connecting from a phone, or
`http://127.0.0.1:8000` if testing from the same machine's browser.

## Testing

```bash
pytest                              # backend, full suite
cd mobile && npx tsc --noEmit       # mobile, typecheck (no test suite yet)
```

The backend suite covers `store.py`, `brain.py`, and `api/` end-to-end against a
real (tmp-path) SQLite database, with the LLM client mocked — no network access
or API key required to run it.

## Configuration

All secrets/settings are read from environment variables (or a local `.env`) —
copy `.env.example` to `.env` and fill in your own values. `LLM_PROVIDER`
switches between `anthropic` (default) and `groq`.
