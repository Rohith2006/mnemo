from fastapi import APIRouter, Depends, status

from api.auth import get_current_user
from api.schemas import UpdateMeRequest, UserOut
import store
from store import get_store

router = APIRouter(prefix="/api", tags=["account"])


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return UserOut(user_id=user["user_id"], email=user["email"], name=user["name"], tz=user["tz"])


@router.patch("/me", response_model=UserOut)
def update_me(body: UpdateMeRequest, user: dict = Depends(get_current_user)):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if fields:
        store.registry.set(user["user_id"], **fields)
    updated = store.registry.get(user["user_id"])
    return UserOut(user_id=updated["user_id"], email=updated["email"], name=updated["name"], tz=updated["tz"])


@router.post("/forget", status_code=status.HTTP_204_NO_CONTENT)
def forget(user: dict = Depends(get_current_user)):
    get_store(user["user_id"]).forget_all()
