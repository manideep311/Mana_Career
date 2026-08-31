from sqlalchemy import select

from app.core.config import get_settings
from app.models.audit import AuditLog

BASE = "/api/v1/auth"
COOKIE = get_settings().refresh_cookie_name


async def _register(client, email="user@example.com", pw="correct-passphrase", name="User"):
    return await client.post(
        f"{BASE}/register", json={"email": email, "password": pw, "full_name": name}
    )


async def test_register_returns_201_token_and_cookie(client):
    r = await _register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["user"]["email"] == "user@example.com"
    assert r.cookies.get(COOKIE)


async def test_register_duplicate_is_409_email_taken(client):
    await _register(client)
    r = await _register(client, name="Again")
    assert r.status_code == 409 and r.json()["code"] == "email_taken"


async def test_register_short_password_is_422(client):
    r = await client.post(
        f"{BASE}/register",
        json={"email": "x@example.com", "password": "short", "full_name": "X"},
    )
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


async def test_login_ok_and_wrong_password(client):
    await _register(client, email="l@example.com")
    ok = await client.post(
        f"{BASE}/login", json={"email": "l@example.com", "password": "correct-passphrase"}
    )
    assert ok.status_code == 200 and ok.cookies.get(COOKIE)
    bad = await client.post(
        f"{BASE}/login", json={"email": "l@example.com", "password": "nope"}
    )
    assert bad.status_code == 401 and bad.json()["code"] == "invalid_credentials"


async def test_me_requires_bearer(client):
    reg = await _register(client, email="m@example.com")
    token = reg.json()["access_token"]
    anon = await client.get(f"{BASE}/me")
    assert anon.status_code == 401
    me = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "m@example.com"


async def test_refresh_rotates_cookie(client):
    await _register(client, email="r@example.com")
    first = await client.post(f"{BASE}/refresh")
    assert first.status_code == 200
    assert first.cookies.get(COOKIE)
    second = await client.post(f"{BASE}/refresh")  # jar now holds the rotated cookie
    assert second.status_code == 200


async def test_refresh_reuse_is_401_and_kills_family(client):
    reg = await _register(client, email="reuse@example.com")
    stolen = reg.cookies.get(COOKIE)
    await client.post(f"{BASE}/refresh")  # legitimate rotation
    replay = await client.post(f"{BASE}/refresh", cookies={COOKIE: stolen})
    assert replay.status_code == 401 and replay.json()["code"] == "refresh_reuse"
    # family is dead: neither the stolen token nor the jar's rotated token works
    assert (await client.post(f"{BASE}/refresh", cookies={COOKIE: stolen})).status_code == 401
    assert (await client.post(f"{BASE}/refresh")).status_code == 401


async def test_logout_is_204_and_clears_cookie(client):
    await _register(client, email="o@example.com")
    r = await client.post(f"{BASE}/logout")
    assert r.status_code == 204
    assert (await client.post(f"{BASE}/refresh")).status_code == 401


async def test_password_change_revokes_old_sessions(client):
    reg = await _register(client, email="pw@example.com")
    token = reg.json()["access_token"]
    old_cookie = reg.cookies.get(COOKIE)
    r = await client.post(
        f"{BASE}/password/change",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "correct-passphrase",
              "new_password": "a-brand-new-passphrase"},
    )
    assert r.status_code == 200
    stale = await client.post(f"{BASE}/refresh", cookies={COOKIE: old_cookie})
    assert stale.status_code == 401
    login = await client.post(
        f"{BASE}/login",
        json={"email": "pw@example.com", "password": "a-brand-new-passphrase"},
    )
    assert login.status_code == 200


async def test_auth_events_are_audited(client, db_session):
    await _register(client, email="audit@example.com")
    await client.post(
        f"{BASE}/login",
        json={"email": "audit@example.com", "password": "correct-passphrase"},
    )
    actions = set((await db_session.execute(select(AuditLog.action))).scalars().all())
    # Committed-path events. auth.login_failed is also written but on a request
    # that raises 401, so get_session rolls it back in production (durable
    # failed-attempt auditing is a Phase 13 concern).
    assert {"auth.register", "auth.login"}.issubset(actions)
