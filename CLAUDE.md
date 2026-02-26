# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

mnemo is a hyper-personalized AI assistant with persistent long-term memory. Unlike a stateless
chatbot, it automatically extracts, deduplicates, and stores what it learns about the user
(profile facts, measurable log entries, tasks, habits, mood) — no "save" button — and uses that
memory to give personal replies and proactive insight (streak/deadline alerts, natural-language
reminders, on-demand briefings).

The primary UI is a **mobile app** (`mobile/`, Expo/React Native), deliberately **not chat-first**:
its home screen is one-line quick-capture that returns a structured receipt of what was understood,
not a conversational reply. A secondary Chat tab exists for genuinely open-ended conversation. The
mobile app talks to a FastAPI backend (`api/`) which is the only frontend now — the original
`web.py` (stdlib HTTP server, single hardcoded local user) and `pa.py` (Telegram bot) have been
retired; both `db.py`/`store.py`/`brain.py` carried over almost unchanged underneath the new API.

## Commands

```bash
# Backend setup
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # fill in ANTHROPIC_*/MNEMO_JWT_SECRET

# Run the backend (LAN-reachable — mobile app connects to this over wifi)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Backend tests
pytest                                        # full suite
pytest tests/test_api.py                      # API layer only
pytest tests/test_api.py::test_capture_returns_receipt_not_a_chat_reply   # one test

# Mobile app
cd mobile && npm install
npx expo start              # prints a QR code / exp:// URL for Expo Go on a phone
npx expo start --web        # browser preview (react-native-web) — useful for quick UI iteration
npx tsc --noEmit            # typecheck (no separate mobile test suite yet)
```

The backend test suite makes no network calls — the LLM is mocked via `monkeypatch.setattr(brain,
"call_llm", ...)` and each test gets an isolated tmp-path SQLite DB via the autouse `isolated_db`
fixture in `tests/conftest.py`. No API key required to run tests.

## Architecture

**Layering is strict and one-directional:** `db.py` → `store.py` → `brain.py` → `api/` → `mobile/`.
`api/` must never touch `db.py` directly or duplicate LLM calls — always go through `brain.py`
functions and a `store.py` `UserStore`/`UserRegistry`/`ReminderStore` instance.

- **`db.py`** — SQLite connection + schema (WAL mode, one file at `data/mnemo.db` unless
  `MNEMO_DB_PATH` is set). Connections are cached per-path in a module-level dict; tests override
  the path and call `reset_connections()` between runs. Tables: `users` (accounts: email/password
  hash/tz), `facts`, `log_entries`, `tasks`, `habits`, `journal`, `reminders`, `digests` (per-user
  per-kind per-day cache). No migration framework — this is pre-production, schema changes are made
  directly.
- **`store.py`** — three repositories on top of `db.py`:
  - `UserStore` — per-user memory: `facts` (deduped, case-insensitive), `log_entries` (deliberately
    schema-free: `{category, key, value, unit, note}` — any metric type, no schema change needed to
    track a new kind of thing), `tasks` (dedup on open-task text; `complete_tasks` fuzzy-matches by
    substring for LLM-driven completion, `complete_task_by_id` is exact-id for a direct UI tap),
    `habits` (streak/best_streak keyed on consecutive daily `last_done`), `journal` (mood), and a
    digest cache (`get_cached_digest`/`save_digest`). `summary()` renders a compact snapshot for LLM
    system prompts; `trends()` computes first→last deltas per numeric log key.
  - `UserRegistry` — accounts: `create`/`get`/`get_by_email`/`set`/`tz`. Password hashing and JWT
    issuance live in `api/auth.py`, not here — this just persists whatever hash it's given.
  - `ReminderStore` — pending NLP-detected reminders, scoped by `user_id` (renamed from `chat_id`
    when Telegram was retired).
  - **Import discipline that matters:** `registry` and `reminder_store` are module-level singletons
    that `store.reset_state()` (used between tests) *rebinds* to fresh instances. Code that does
    `from store import registry` captures the old object and goes stale after a reset. Always
    `import store` and reference `store.registry` / `store.reminder_store` by attribute — every file
    under `api/` follows this; keep it that way. `get_store` is a plain function and safe to import
    directly either way.
- **`brain.py`** — the shared core, no HTTP/frontend dependency:
  - `call_llm` — Anthropic Messages API through a local proxy (`ANTHROPIC_BASE_URL`, default
    `http://127.0.0.1:3456`; e.g. an opencode proxy fronting a Claude subscription, or point it at
    `https://api.anthropic.com` with a real key). Splits OpenAI-style `messages` into a top-level
    `system` string + user/assistant turns. `temperature` is accepted for call-site compatibility
    but **not forwarded** — the configured model (`PA_MODEL`, default `claude-opus-4-8`) rejects
    sampling params.
  - `extract` — one structured LLM call per turn → JSON across all buckets (`facts`, `log`,
    `tasks_new`, `tasks_done`, `habits_done`, `mood`). Single-call-per-turn is intentional.
  - `apply_extraction` — writes `extract`'s output into a `UserStore`, validating types defensively
    (LLM JSON is untrusted input).
  - `detect_reminder` — separate LLM call, natural language → `{task, seconds}`.
  - `build_reply` / `build_digest` — conversational reply and morning/evening/on-demand digest
    generation, both driven by `store.summary()` + `store.trends()`.
  - `parse_json` — tolerant JSON extraction from LLM output; returns `None` on failure rather than
    raising. All call sites must handle `None`.
- **`api/`** — FastAPI backend, the only frontend surface now:
  - `auth.py` — bcrypt password hashing, PyJWT issuance/verification, `get_current_user` dependency
    (Bearer token → account dict). 30-day tokens, no refresh-token flow (YAGNI at this scale).
  - `schemas.py` — Pydantic request/response models mirrored by `mobile/src/api/types.ts` — keep
    both in sync when changing a shape.
  - `routers/capture.py` vs `routers/chat.py` — **this split is the product's core differentiator**.
    `/api/capture` runs `detect_reminder` + `extract`/`apply_extraction` only and returns a
    structured receipt (facts/log/tasks/habits/mood/reminder) — no `build_reply` call, no
    conversational text. `/api/chat` is the secondary, explicitly-conversational path that also
    calls `build_reply`. Don't blur this line — a new "smart" feature on the capture path should
    still return structured data, not prose.
  - `routers/tasks.py` / `habits.py` — direct-action endpoints (complete a task by id, log a habit
    by name) that bypass the LLM entirely, for tapping something that already exists in the UI.
  - `routers/digests.py` — cached per `(user, kind, date)` in the `digests` table; `?refresh=true`
    bypasses the cache. No scheduler/background jobs exist — digests are generated lazily on
    request, not pushed. There is deliberately no push-notification infrastructure: proactive
    surfaces (alerts, digests) are pull/in-app only, computed live in `routers/dashboard.py` from
    `overdue_tasks`/`habits_at_risk`/etc. Only reminders get real OS notifications, and those are
    scheduled **client-side** (see `mobile/src/notifications/`) — the server never pushes anything.
  - `main.py` registers a `fastapi.exception_handler` for `anthropic.APIError` that returns a clean
    502 JSON response. This matters beyond error messages: an *unhandled* exception is caught by
    Starlette's generic 500 handler, which does not flow back through `CORSMiddleware` the way a
    registered handler's response does — a browser client sees a bare "blocked by CORS policy" with
    no useful detail instead of the real error. Any new route that can throw from an LLM call should
    rely on this handler rather than adding its own try/except, unless it needs a different status.
- **`mobile/`** — Expo (React Native + TypeScript) app, Expo Router file-based navigation:
  - `app/(auth)/` — login/signup, each with a "Server URL" field (the backend is LAN-only, no fixed
    address) persisted alongside the JWT.
  - `app/(tabs)/` — `index.tsx` (Capture, the default tab), `track.tsx` (dashboard: habits/tasks/
    trends/mood/reminders, tap-to-complete and tap-to-log directly against the no-LLM endpoints),
    `chat.tsx` (secondary, explicitly labeled as such in its own UI copy), `settings.tsx`.
  - `src/auth/AuthGate.tsx` — redirects between `(auth)` and `(tabs)` based on token validity;
    validated once at launch via `GET /api/me`.
  - `src/notifications/` — schedules reminders as local, on-device notifications the moment the
    server confirms one (`expo-notifications`, `SchedulableTriggerInputTypes.DATE`). This is what
    makes reminders work despite the backend being LAN-only: the phone alarms itself, no push
    infrastructure involved. `reconcile()` re-schedules any pending server reminder not yet
    scheduled locally (covers reinstalls / a second device) — call it whenever dashboard data loads.
  - `src/storage.ts` — SecureStore on native, AsyncStorage on web (SecureStore has no web impl).
  - Known limitation, by design: a reminder scheduled locally on one device won't fire on another
    device signed into the same account. Solving that requires real push (Expo push tokens +
    server-triggered send), explicitly deferred — don't "fix" this without discussing the tradeoff.

## Working in this repo

- Adding a new kind of trackable data (e.g. a new metric) should not require a schema change — use
  the existing `log_entries` `{category, key, value, unit}` shape via `extract`'s prompt.
- Any new LLM-facing capability that mutates state belongs in `brain.py`, called from `api/` —
  never implemented only inside a router.
- Changing a Pydantic schema in `api/schemas.py` almost always means updating the mirrored TS type
  in `mobile/src/api/types.ts` too — there's no codegen keeping them in sync.
