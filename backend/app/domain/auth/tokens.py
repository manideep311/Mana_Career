from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass

import jwt

from app.core.config import Settings
from app.core.errors import AuthError

ALGORITHM = "HS256"
ACCESS_TYPE = "access"
ISSUER = "mana-career"
AUDIENCE = "mana-career-web"
_REQUIRED_CLAIMS = ["exp", "iat", "sub", "sid", "type", "iss", "aud", "jti"]


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    # The refresh-token family: one per sign-in. Revoking the family (logout,
    # password change, token reuse) ends every access token minted for it.
    session_id: uuid.UUID


def create_access_token(
    user_id: uuid.UUID, *, session_id: uuid.UUID, settings: Settings
) -> tuple[str, int]:
    ttl = settings.jwt_access_ttl_seconds
    now = dt.datetime.now(dt.UTC)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "sid": str(session_id),
        "type": ACCESS_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return token, ttl


def decode_access_token(token: str, *, settings: Settings) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(detail="Your session has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(detail="Please sign in.", code="invalid_token") from exc
    if payload.get("type") != ACCESS_TYPE:
        raise AuthError(detail="Please sign in.", code="invalid_token")
    try:
        return AccessClaims(
            user_id=uuid.UUID(str(payload["sub"])),
            session_id=uuid.UUID(str(payload["sid"])),
        )
    except (KeyError, ValueError) as exc:
        raise AuthError(detail="Please sign in.", code="invalid_token") from exc


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def new_link_token() -> tuple[str, str]:
    """A token for an emailed link: (raw for the URL, sha256 for the database)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_link_token(raw)


def hash_link_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
