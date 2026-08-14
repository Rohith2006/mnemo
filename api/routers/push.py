from fastapi import APIRouter, Depends, status

from api.auth import get_current_user
from api.schemas import PushTokenRegister
from store import get_store

router = APIRouter(prefix="/api/push", tags=["push"])


@router.post("/register", status_code=status.HTTP_204_NO_CONTENT)
def register(body: PushTokenRegister, user: dict = Depends(get_current_user)):
    get_store(user["user_id"]).add_push_token(body.token, body.platform)
