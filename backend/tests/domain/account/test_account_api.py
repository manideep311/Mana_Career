"""/account export + delete over HTTP -- DB integration, CI-deferred."""
from __future__ import annotations

import io
import json
import zipfile

from app.models.user import User

from .conftest import PASSWORD


async def _login(client, email: str) -> dict[str, str]:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_export_downloads_a_zip_of_only_their_data(client, db_session, seed_person):
    await seed_person("api-export@x.com")
    await seed_person("api-export-other@x.com")
    h = await _login(client, "api-export@x.com")
    r = await client.get("/api/v1/account/export", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"].startswith('attachment; filename="mana-career-export-')
    assert r.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        data = json.loads(z.read("mana-career-data.json"))
    assert data["account"]["email"] == "api-export@x.com"
    assert "api-export-other@x.com" not in json.dumps(data)


async def test_delete_needs_the_password_and_the_word(client, db_session, seed_person):
    me = await seed_person("api-delete@x.com")
    h = await _login(client, "api-delete@x.com")

    missing_word = await client.request(
        "DELETE", "/api/v1/account", headers=h, json={"password": PASSWORD, "confirm": "yes"}
    )
    assert missing_word.status_code == 422

    typo = await client.request(
        "DELETE", "/api/v1/account", headers=h, json={"password": "nope", "confirm": "DELETE"}
    )
    # 403, not 401: a typo mustn't look like an expired session.
    assert typo.status_code == 403 and typo.json()["code"] == "invalid_password"
    assert await db_session.get(User, me.user.id) is not None

    ok = await client.request(
        "DELETE", "/api/v1/account", headers=h, json={"password": PASSWORD, "confirm": "DELETE"}
    )
    assert ok.status_code == 204
    assert "mana_refresh" in ok.headers.get("set-cookie", "")
    db_session.expire_all()
    assert await db_session.get(User, me.user.id) is None

    # The access token they still hold no longer works.
    assert (await client.get("/api/v1/auth/me", headers=h)).status_code == 401


async def test_account_endpoints_need_sign_in(client):
    assert (await client.get("/api/v1/account/export")).status_code == 401
    r = await client.request(
        "DELETE", "/api/v1/account", json={"password": PASSWORD, "confirm": "DELETE"}
    )
    assert r.status_code == 401
