from datetime import datetime

from fastapi import APIRouter, Depends

from api.auth import get_current_user
from api.schemas import DashboardOut, HabitOut, LogEntryOut, MoodOut, ReminderOut, TaskOut
import store
from store import get_store

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: dict = Depends(get_current_user)):
    tz = store.registry.tz(user["user_id"])
    user_store = get_store(user["user_id"])

    mood = user_store.recent_mood(7)
    pending = store.reminder_store.get_all_for_user(user["user_id"])
    overdue = user_store.overdue_tasks(tz)
    at_risk = user_store.habits_at_risk(tz)

    def _due_label(t: dict) -> str:
        # A date-only due has no real time-of-day to report — "was due 00:00" would
        # misleadingly imply one.
        return t["due_dt"].strftime("%H:%M %a") if "T" in t["due"] else t["due_dt"].strftime("%a")

    alerts = [f'"{t["task"]}" was due {_due_label(t)}' for t in overdue]
    for h in at_risk:
        if h.get("streak", 0) >= 2 and datetime.now(tz).hour >= 12:
            alerts.append(f'{h["name"]} streak (day {h["streak"]}) — not done today yet')

    return DashboardOut(
        profile=user_store.facts(),
        habits=[
            HabitOut(name=h["name"], streak=h.get("streak", 0), best_streak=h.get("best_streak", 0),
                      last_done=h.get("last_done"))
            for h in user_store.active_habits()
        ],
        tasks=[TaskOut(id=t["id"], task=t["task"], due=t.get("due"), status=t["status"])
               for t in user_store.open_tasks()],
        completed=[TaskOut(id=t["id"], task=t["task"], due=t.get("due"), status=t["status"],
                            done_at=t.get("done_at"))
                   for t in user_store.completed_tasks()],
        trends=user_store.trends(),
        log=[LogEntryOut(category=e["category"], key=e["key"], value=e.get("value"), unit=e.get("unit", ""))
             for e in user_store.recent_log(7)[-10:]],
        mood=(MoodOut(avg=round(sum(m["mood"] for m in mood) / len(mood), 1), count=len(mood))
              if mood else None),
        reminders=[ReminderOut(id=r["id"], task=r["task"], fire_at=r["fire_at"]) for r in pending],
        alerts=alerts,
    )
