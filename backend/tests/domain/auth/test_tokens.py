import datetime as dt
import uuid
from typing import Any

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import AuthError
from app.domain.auth.tokens import (
    ACCESS_TYPE,
    ALGORITHM,
    AUDIENCE,
    ISSUER,
    AccessClaims,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k, v in {
        "DATABASE_URL": "x", "DATABASE_URL_TEST": "x", "REDIS_URL": "x",
        "JWT_SECRET": "unit-secret",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()


def _signed(settings: Settings, **over: Any) -> str:
    now = dt.datetime.now(dt.UTC)
    claims: dict[str, Any] = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()),
        "type": ACCESS_TYPE, "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(hours=1)).timestamp()), "jti": str(uuid.uuid4()),
    }
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def _code(settings: Settings, token: str) -> str:
    with pytest.raises(AuthError) as ei:
        decode_access_token(token, settings=settings)
    return ei.value.code


def test_access_token_round_trips_with_session(settings: Settings):
    uid, sid = uuid.uuid4(), uuid.uuid4()
    token, expires_in = create_access_token(uid, session_id=sid, settings=settings)
    assert expires_in == settings.jwt_access_ttl_seconds
    assert decode_access_token(token, settings=settings) == AccessClaims(uid, sid)
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == ISSUER and claims["aud"] == AUDIENCE and claims["jti"]


def test_expired_token_raises_token_expired(settings: Settings):
    past = int((dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)).timestamp())
    assert _code(settings, _signed(settings, iat=past, exp=past)) == "token_expired"


def test_wrong_signature_raises_invalid_token(settings: Settings):
    token, _ = create_access_token(uuid.uuid4(), session_id=uuid.uuid4(), settings=settings)
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    assert _code(settings, tampered) == "invalid_token"


def test_non_access_token_type_rejected(settings: Settings):
    assert _code(settings, _signed(settings, type="refresh")) == "invalid_token"


@pytest.mark.parametrize(
    "over",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example"},
        {"aud": None},
        {"iss": None},
        {"sid": None},
        {"jti": None},
        {"sid": "not-a-uuid"},
    ],
    ids=["wrong-aud", "wrong-iss", "no-aud", "no-iss", "no-sid", "no-jti", "bad-sid"],
)
def test_tokens_without_our_issuer_audience_or_session_are_rejected(
    settings: Settings, over: dict[str, Any]
):
    assert _code(settings, _signed(settings, **over)) == "invalid_token"


def test_refresh_token_is_opaque_and_hash_is_stable():
    raw, digest = new_refresh_token()
    assert len(raw) >= 32 and raw.isascii()
    assert digest == hash_refresh_token(raw)
    assert len(digest) == 64  # sha256 hex
