"""Password hashing + JWT issuance/verification for the mobile API.

store.py's UserRegistry only persists whatever password hash it's given —
all hashing and token logic lives here so store.py stays free of crypto deps.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import store

_DEV_SECRET = "dev-secret-change-me-in-.env-as-MNEMO_JWT_SECRET-32-bytes-min"
JWT_SECRET = os.getenv("MNEMO_JWT_SECRET", _DEV_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the user_id encoded in the token, or raises HTTPException(401)."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return user_id


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """FastAPI dependency: decodes the bearer token and loads the account row."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    user_id = decode_access_token(creds.credentials)
    user = store.registry.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account no longer exists")
    return user
