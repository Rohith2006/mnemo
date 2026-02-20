from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import get_current_user
from api.schemas import HabitOut
from store import get_store

router = APIRouter(prefix="/api/habits", tags=["habits"])


@router.get("", response_model=list[HabitOut])
def list_habits(user: dict = Depends(get_current_user)):
    store = get_store(user["user_id"])
    return [HabitOut(name=h["name"], streak=h.get("streak", 0), best_streak=h.get("best_streak", 0),
                      last_done=h.get("last_done")) for h in store.active_habits()]


@router.post("/{name}/log", response_model=HabitOut)
def log_habit(name: str, user: dict = Depends(get_current_user)):
    store = get_store(user["user_id"])
    h = store.log_habit(name)
    if not h:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "habit name required")
    return HabitOut(name=h["name"], streak=h.get("streak", 0), best_streak=h.get("best_streak", 0),
                     last_done=h.get("last_done"))
