"""Authentication + authorization gates. DB integration, CI-deferred.

``get_current_user`` (``app/api/deps.py``) rejects a request with **401** when the
``Authorization`` header is missing or not a ``bearer`` token, or when the JWT is
signed with the wrong secret, is expired, is missing a required claim, carries the
wrong ``type``, or names a user row that does not exist. ``get_current_admin``
then rejects a signature-valid non-admin user with **403**.

This module drives each of those paths against a real route: ``GET
/api/v1/profile`` (a ``CurrentUser`` route) for the 401 cases and ``GET
/api/v1/eval/runs`` (``list_eval_runs`` -- a ``CurrentAdmin`` route with no side
effects) for both sides of the admin gate.

DB-gated: the module ERRORs at the session-scoped ``_migrated`` fixture without a
Postgres instance (CI-only) but must collect clean.
"""
from __future__ import annotations

import datetime as dt

import jwt

from app.core.config import get_settings
from app.domain.auth.tokens import create_access_token
from app.models.user import User

_PROFILE = "/api/v1/profile"
_ADMIN_ROUTE = "/api/v1/eval/runs"


async def _register(client, email):
    """Register a normal (non-admin) user."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "U"},
    )


def _forge(payload_overrides, *, secret=None):
    """Sign an access-token-shaped JWT, letting the caller override any claim."""
    s = get_settings()
    now = int(dt.datetime.now(dt.UTC).timestamp())
    payload = {"sub": "00000000-0000-0000-0000-000000000001", "type": "access",
               "iat": now, "exp": now + 3600, **payload_overrides}
    secret = secret or s.jwt_secret.get_secret_value()
    return jwt.encode(payload, secret, algorithm="HS256")


async def test_no_auth_header_is_401(client, db_session):
    r = await client.get(_PROFILE)
    assert r.status_code == 401


async def test_garbage_bearer_is_401(client, db_session):
    r = await client.get(_PROFILE, headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


async def test_wrong_secret_is_401(client, db_session):
    tok = _forge({}, secret="wrong-secret")
    r = await client.get(_PROFILE, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


async def test_expired_token_is_401(client, db_session):
    now = int(dt.datetime.now(dt.UTC).timestamp())
    tok = _forge({"exp": now - 3600})
    r = await client.get(_PROFILE, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


async def test_wrong_type_claim_is_401(client, db_session):
    tok = _forge({"type": "refresh"})
    r = await client.get(_PROFILE, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


async def test_nonexistent_user_is_401(client, db_session):
    # Signature-valid, but ``sub`` names a user row that was never created:
    # ``db.get(User, uid)`` is None -> AuthError -> 401.
    tok = _forge({})
    r = await client.get(_PROFILE, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


async def test_non_admin_is_403_on_admin_route(client, db_session):
    await _register(client, "authz-user@x.com")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "authz-user@x.com", "password": "correct-passphrase"},
    )
    tok = login.json()["access_token"]
    r = await client.get(_ADMIN_ROUTE, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


async def test_admin_passes_the_gate(client, db_session):
    admin = User(
        email="authz-admin@x.com",
        password_hash="x",
        full_name="A",
        is_admin=True,
        status="active",
    )
    db_session.add(admin)
    await db_session.flush()
    tok, _ = create_access_token(admin.id, settings=get_settings())
    r = await client.get(_ADMIN_ROUTE, headers={"Authorization": f"Bearer {tok}"})
    # The admin gate opened: not 401 (auth passed) and not 403 (is_admin True).
    assert r.status_code not in (401, 403)
    assert r.status_code == 200
