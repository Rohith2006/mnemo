from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

import brain
import store
from api.auth import get_current_user
from api.schemas import DigestOut
from store import get_store

router = APIRouter(prefix="/api/digests", tags=["digests"])

_KINDS = {"morning", "evening", "ondemand"}


@router.get("/{kind}", response_model=DigestOut)
def get_digest(kind: str, refresh: bool = False, user: dict = Depends(get_current_user)):
    if kind not in _KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown digest kind: {kind}")

    tz = store.registry.tz(user["user_id"])
    user_store = get_store(user["user_id"])
    today = datetime.now(tz).date().isoformat()

    if not refresh:
        cached = user_store.get_cached_digest(kind, today)
        if cached is not None:
            return DigestOut(kind=kind, text=cached, date=today)

    text = brain.build_digest(user_store, tz, kind)
    user_store.save_digest(kind, today, text)
    return DigestOut(kind=kind, text=text, date=today)
