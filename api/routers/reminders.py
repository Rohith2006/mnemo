from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import get_current_user
from api.schemas import ReminderOut
import store

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderOut])
def list_reminders(user: dict = Depends(get_current_user)):
    return [ReminderOut(id=r["id"], task=r["task"], fire_at=r["fire_at"])
            for r in store.reminder_store.get_all_for_user(user["user_id"])]


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_reminder(reminder_id: str, user: dict = Depends(get_current_user)):
    mine = {r["id"] for r in store.reminder_store.get_all_for_user(user["user_id"])}
    if reminder_id not in mine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no pending reminder with that id")
    store.reminder_store.remove(reminder_id)
