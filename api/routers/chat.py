"""Secondary conversational surface — for when you actually want to talk to it,
as opposed to quick-capture. Still runs the same extraction as every other turn.

A conversation is created lazily: passing no conversation_id starts a new one,
titled from this message. History lives entirely server-side from here on —
the client only ever sends the new message and (optionally) which conversation
it belongs to."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

import brain
import store
from api.auth import get_current_user
from api.schemas import ChatRequest, ChatResponse, ReminderOut
from store import get_store

router = APIRouter(prefix="/api", tags=["chat"])

MAX_HISTORY_MESSAGES = 20


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    tz = store.registry.tz(user["user_id"])
    user_store = get_store(user["user_id"])

    if body.conversation_id is not None:
        prior_messages = user_store.conversation_messages(body.conversation_id)
        if prior_messages is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no conversation with that id")
        conversation_id = body.conversation_id
    else:
        conversation_id = user_store.create_conversation(body.message)["id"]
        prior_messages = []

    user_store.add_message(conversation_id, "user", body.message)

    pending = store.reminder_store.get_all_for_user(user["user_id"])
    reminder_hit = brain.detect_reminder(body.message, tz)
    new_reminder = {"task": reminder_hit["task"], "seconds": reminder_hit["seconds"]} if reminder_hit else None

    if prior_messages and prior_messages[-1]["role"] == "user":
        prior_messages = prior_messages[:-1]  # a previous turn's LLM call failed after this was committed — drop it so it isn't immediately followed by this turn's own user message

    llm_history = [
        {"role": m["role"], "content": m["content"]} for m in prior_messages[-MAX_HISTORY_MESSAGES:]
    ]
    reply = brain.build_reply(user_store, body.message, llm_history, tz,
                               pending_reminders=pending, new_reminder=new_reminder)

    user_store.add_message(conversation_id, "assistant", reply)

    reminder_out = None
    if reminder_hit:
        fire_at = datetime.now().astimezone() + timedelta(seconds=reminder_hit["seconds"])
        rid = store.reminder_store.add(user["user_id"], reminder_hit["task"], fire_at)
        reminder_out = ReminderOut(id=rid, task=reminder_hit["task"], fire_at=fire_at.isoformat())

    brain.apply_extraction(user_store, brain.extract(body.message, reply, user_store, tz), tz)
    return ChatResponse(reply=reply, conversation_id=conversation_id, reminder=reminder_out)
