"""Pydantic request/response models for the mobile API."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── auth ──────────────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    user_id: str
    email: str
    name: str
    tz: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UpdateMeRequest(BaseModel):
    name: str | None = None
    tz: str | None = None

    @field_validator("tz")
    @classmethod
    def _known_timezone(cls, v: str | None) -> str | None:
        # Every authenticated route resolves ZoneInfo(user.tz); storing a name
        # ZoneInfo can't load would 500 the whole account from then on.
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown timezone: {v}")
        return v


# ── capture / chat ────────────────────────────────────────────────────────────
class ReminderOut(BaseModel):
    id: str
    task: str
    fire_at: str  # ISO8601, for the client to schedule a local notification


class CaptureRequest(BaseModel):
    text: str = Field(min_length=1)


class CaptureResponse(BaseModel):
    facts: list[str]
    facts_updated: list[str] = []   # facts this turn corrected (new text)
    facts_removed: list[str] = []   # facts this turn retired (old text)
    log: list[dict]
    tasks: list[dict]
    done: list[dict]
    habits: list[dict]
    mood: dict | None
    reminder: ReminderOut | None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    reminder: ReminderOut | None


# ── tasks / habits ────────────────────────────────────────────────────────────
class TaskOut(BaseModel):
    id: str
    task: str
    due: str | None
    status: str
    done_at: str | None = None


class TaskCreate(BaseModel):
    task: str = Field(min_length=1)
    due: str | None = None


class HabitOut(BaseModel):
    name: str
    streak: int
    best_streak: int
    last_done: str | None


# ── dashboard ─────────────────────────────────────────────────────────────────
class MoodOut(BaseModel):
    avg: float
    count: int


class LogEntryOut(BaseModel):
    category: str
    key: str
    value: str | None
    unit: str


class DashboardOut(BaseModel):
    profile: list[str]
    habits: list[HabitOut]
    tasks: list[TaskOut]
    completed: list[TaskOut]
    trends: list[str]
    log: list[LogEntryOut]
    mood: MoodOut | None
    reminders: list[ReminderOut]
    alerts: list[str]


# ── digests ───────────────────────────────────────────────────────────────────
class DigestOut(BaseModel):
    kind: str
    text: str
    date: str
