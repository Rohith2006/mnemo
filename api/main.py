"""
mnemo API server — backs the mobile app (mobile/). Replaces the old web.py
(local dev UI) and pa.py (Telegram bot); everything now goes through this one
authenticated, multi-user HTTP API on top of the unchanged brain.py/store.py.

Run:  uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""

try:  # must run before any module-level os.getenv() call below (api.auth reads MNEMO_JWT_SECRET
      # at import time) — don't rely on brain.py's own load_dotenv() call happening first, since
      # import order isn't guaranteed to route through brain before auth.
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic
import groq
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import push as push_module

from api import auth as auth_module
from api.routers import account, auth, capture, chat, conversations, dashboard, digests, habits, push, reminders, tasks

if auth_module.JWT_SECRET == auth_module._DEV_SECRET:
    print("[api] WARNING: MNEMO_JWT_SECRET not set — using an insecure default dev secret. "
          "Set it in .env before exposing this server beyond your own machine.")

app = FastAPI(title="mnemo API")


@app.on_event("startup")
def _start_push_scheduler():
    push_module.start_scheduler()

# LAN-only personal app — no browser cookie exposure, bearer tokens only, so a
# permissive CORS policy here doesn't create the risk it would for a cookie-auth app.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, account.router, dashboard.router, capture.router, chat.router,
               conversations.router, tasks.router, habits.router, reminders.router, digests.router,
               push.router):
    app.include_router(router)


def llm_error_handler(request, exc: Exception):
    # An unhandled exception here would be caught by Starlette's generic 500
    # handler, which — unlike a registered handler — doesn't get wrapped by
    # CORSMiddleware, so the browser sees a bare "blocked by CORS policy"
    # instead of the real error. Registering a handler keeps it inside the
    # normal response path so clients get a clean, readable failure instead.
    return JSONResponse(status_code=502, content={
        "detail": "Couldn't reach the LLM backend. Check LLM_PROVIDER and its API key/URL in .env.",
    })


# Registered for both providers' error hierarchies — LLM_PROVIDER picks which one
# is actually in play, but either can raise regardless of which client is unused.
app.add_exception_handler(anthropic.APIError, llm_error_handler)
app.add_exception_handler(groq.APIError, llm_error_handler)


@app.get("/api/health")
def health():
    return {"status": "ok"}
