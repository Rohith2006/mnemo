from fastapi import APIRouter, HTTPException, status

from api.auth import create_access_token, hash_password, verify_password
from api.schemas import LoginRequest, SignupRequest, TokenResponse, UserOut
import store

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: dict) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user["user_id"]),
        user=UserOut(user_id=user["user_id"], email=user["email"], name=user["name"], tz=user["tz"]),
    )


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest):
    try:
        user = store.registry.create(str(body.email), hash_password(body.password), name=body.name)
    except ValueError:
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with that email already exists")
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = store.registry.get_by_email(str(body.email))
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect email or password")
    return _token_response(user)
