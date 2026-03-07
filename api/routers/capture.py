"""Quick-capture: log something in one line, get back what was understood — not a
chat reply. This is mnemo's primary interaction, deliberately not conversational:
one LLM call to extract structured facts/log/tasks/habits/mood (brain.extract),
applied to the store, plus reminder detection. The response is a receipt."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

import brain
import store
from api.auth import get_current_user
from api.schemas import CaptureRequest, CaptureResponse, ReminderOut
from store import get_store

router = APIRouter(prefix="/api", tags=["capture"])


@router.post("/capture", response_model=CaptureResponse)
def capture(body: CaptureRequest, user: dict = Depends(get_current_user)):
    tz = store.registry.tz(user["user_id"])
    user_store = get_store(user["user_id"])

    reminder_hit = brain.detect_reminder(body.text, tz)
    changed = brain.apply_extraction(user_store, brain.extract(body.text, "", user_store, tz))

    reminder_out = None
    if reminder_hit:
        fire_at = datetime.now().astimezone() + timedelta(seconds=reminder_hit["seconds"])
        rid = store.reminder_store.add(user["user_id"], reminder_hit["task"], fire_at)
        reminder_out = ReminderOut(id=rid, task=reminder_hit["task"], fire_at=fire_at.isoformat())

    return CaptureResponse(
        facts=changed["facts"], facts_updated=changed["facts_updated"],
        facts_removed=changed["facts_removed"], log=changed["log"], tasks=changed["tasks"],
        done=changed["done"], habits=changed["habits"], mood=changed["mood"],
        reminder=reminder_out,
    )
