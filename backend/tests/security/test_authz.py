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
from app.domain.auth.service import AuthService
from app.domain.auth.tokens import AUDIENCE, ISSUER
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
    payload = {"iss": ISSUER, "aud": AUDIENCE,
               "sub": "00000000-0000-0000-0000-000000000001",
               "sid": "00000000-0000-0000-0000-00000000000a", "type": "access",
               "jti": "forged", "iat": now, "exp": now + 3600, **payload_overrides}
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
    # A real sign-in session for the admin (the password hash is unusable).
    tok, _, _, _ = await AuthService(db_session)._issue(admin, ip=None, user_agent=None)
    r = await client.get(_ADMIN_ROUTE, headers={"Authorization": f"Bearer {tok}"})
    # The admin gate opened: not 401 (auth passed) and not 403 (is_admin True).
    assert r.status_code not in (401, 403)
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# Session revocation: access tokens die with their sign-in session
# --------------------------------------------------------------------------- #
async def _login(client, email):
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


async def test_logout_revokes_the_access_token_immediately(client, db_session):
    await _register(client, "authz-logout@x.com")
    tok = await _login(client, "authz-logout@x.com")
    assert (await client.get(_PROFILE, headers=_bearer(tok))).status_code == 200

    assert (await client.post("/api/v1/auth/logout")).status_code == 204

    r = await client.get(_PROFILE, headers=_bearer(tok))
    assert r.status_code == 401
    assert r.json()["code"] == "session_revoked"


async def test_token_for_an_unknown_session_is_rejected(client, db_session):
    await _register(client, "authz-sid@x.com")
    tok = await _login(client, "authz-sid@x.com")
    me = await client.get("/api/v1/auth/me", headers=_bearer(tok))
    forged = _forge({"sub": me.json()["id"]})  # right user and secret, invented session
    r = await client.get(_PROFILE, headers=_bearer(forged))
    assert r.status_code == 401
    assert r.json()["code"] == "session_revoked"


async def test_password_change_ends_other_sessions(client, db_session):
    await _register(client, "authz-pw@x.com")
    other_device = await _login(client, "authz-pw@x.com")
    this_device = await _login(client, "authz-pw@x.com")

    r = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "correct-passphrase", "new_password": "a-new-passphrase-1"},
        headers=_bearer(this_device),
    )
    assert r.status_code == 200, r.text
    fresh = r.json()["access_token"]

    assert (await client.get(_PROFILE, headers=_bearer(other_device))).status_code == 401
    assert (await client.get(_PROFILE, headers=_bearer(fresh))).status_code == 200
