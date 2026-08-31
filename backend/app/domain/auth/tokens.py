from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid

import jwt

from app.core.config import Settings
from app.core.errors import AuthError

ALGORITHM = "HS256"
ACCESS_TYPE = "access"


def create_access_token(user_id: uuid.UUID, *, settings: Settings) -> tuple[str, int]:
    ttl = settings.jwt_access_ttl_seconds
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM
    )
    return token, ttl


def decode_access_token(token: str, *, settings: Settings) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(detail="Your session has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(detail="Please sign in.", code="invalid_token") from exc
    if payload.get("type") != ACCESS_TYPE:
        raise AuthError(detail="Please sign in.", code="invalid_token")
    try:
        return uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthError(detail="Please sign in.", code="invalid_token") from exc


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)
