"""Secondary conversational surface — for when you actually want to talk to it,
as opposed to quick-capture. Still runs the same extraction as every other turn."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

import brain
import store
from api.auth import get_current_user
from api.schemas import ChatRequest, ChatResponse, ReminderOut
from store import get_store

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    tz = store.registry.tz(user["user_id"])
    user_store = get_store(user["user_id"])

    pending = store.reminder_store.get_all_for_user(user["user_id"])
    reminder_hit = brain.detect_reminder(body.message, tz)
    new_reminder = {"task": reminder_hit["task"], "seconds": reminder_hit["seconds"]} if reminder_hit else None

    history = [m.model_dump() for m in body.history]
    reply = brain.build_reply(user_store, body.message, history, tz,
                               pending_reminders=pending, new_reminder=new_reminder)

    reminder_out = None
    if reminder_hit:
        fire_at = datetime.now().astimezone() + timedelta(seconds=reminder_hit["seconds"])
        rid = store.reminder_store.add(user["user_id"], reminder_hit["task"], fire_at)
        reminder_out = ReminderOut(id=rid, task=reminder_hit["task"], fire_at=fire_at.isoformat())

    brain.apply_extraction(user_store, brain.extract(body.message, reply, user_store, tz))
    return ChatResponse(reply=reply, reminder=reminder_out)
