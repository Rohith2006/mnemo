from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import get_current_user
from api.schemas import HabitOut
import store
from store import get_store

router = APIRouter(prefix="/api/habits", tags=["habits"])


@router.get("", response_model=list[HabitOut])
def list_habits(user: dict = Depends(get_current_user)):
    user_store = get_store(user["user_id"])
    return [HabitOut(name=h["name"], streak=h.get("streak", 0), best_streak=h.get("best_streak", 0),
                      last_done=h.get("last_done")) for h in user_store.active_habits()]


@router.post("/{name}/log", response_model=HabitOut)
def log_habit(name: str, user: dict = Depends(get_current_user)):
    user_store = get_store(user["user_id"])
    # The user's calendar day, not the server's — streaks are counted in local days.
    tz = store.registry.tz(user["user_id"])
    h = user_store.log_habit(name, on=datetime.now(tz).date())
    if not h:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "habit name required")
    user_store.invalidate_today_digests(tz)
    return HabitOut(name=h["name"], streak=h.get("streak", 0), best_streak=h.get("best_streak", 0),
                     last_done=h.get("last_done"))
