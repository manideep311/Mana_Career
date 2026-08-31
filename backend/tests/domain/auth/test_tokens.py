import datetime as dt
import uuid

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import AuthError
from app.domain.auth.tokens import (
    ACCESS_TYPE,
    ALGORITHM,
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


def test_access_token_round_trips(settings: Settings):
    uid = uuid.uuid4()
    token, expires_in = create_access_token(uid, settings=settings)
    assert expires_in == settings.jwt_access_ttl_seconds
    assert decode_access_token(token, settings=settings) == uid


def test_expired_token_raises_token_expired(settings: Settings):
    uid = uuid.uuid4()
    past = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
    token = jwt.encode(
        {"sub": str(uid), "type": ACCESS_TYPE, "iat": int(past.timestamp()),
         "exp": int(past.timestamp())},
        settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM,
    )
    with pytest.raises(AuthError) as ei:
        decode_access_token(token, settings=settings)
    assert ei.value.code == "token_expired"


def test_wrong_signature_raises_invalid_token(settings: Settings):
    uid = uuid.uuid4()
    token, _ = create_access_token(uid, settings=settings)
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    with pytest.raises(AuthError) as ei:
        decode_access_token(tampered, settings=settings)
    assert ei.value.code == "invalid_token"


def test_non_access_token_type_rejected(settings: Settings):
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "refresh",
         "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).timestamp())},
        settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM,
    )
    with pytest.raises(AuthError) as ei:
        decode_access_token(token, settings=settings)
    assert ei.value.code == "invalid_token"


def test_refresh_token_is_opaque_and_hash_is_stable():
    raw, digest = new_refresh_token()
    assert len(raw) >= 32 and raw.isascii()
    assert digest == hash_refresh_token(raw)
    assert len(digest) == 64  # sha256 hex
