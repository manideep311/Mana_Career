import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import CurrentAdmin, CurrentUser
from app.core.db import get_session
from app.core.errors import install_error_handlers
from app.domain.auth.service import AuthService


@pytest.fixture
async def probe_client(db_session):
    app = FastAPI()
    install_error_handlers(app)
    app.dependency_overrides[get_session] = lambda: db_session

    @app.get("/whoami")
    async def whoami(user: CurrentUser) -> dict:
        return {"email": user.email}

    @app.get("/admin-only")
    async def admin_only(user: CurrentAdmin) -> dict:
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c, db_session


async def test_missing_bearer_is_401_missing_token(probe_client):
    c, _ = probe_client
    r = await c.get("/whoami")
    assert r.status_code == 401
    assert r.json()["code"] == "missing_token"


async def test_valid_bearer_resolves_user(probe_client):
    c, db = probe_client
    reg = await AuthService(db).register("me@example.com", "correct-passphrase", "Me",
                                         ip=None, user_agent=None)
    r = await c.get("/whoami", headers={"Authorization": f"Bearer {reg.access_token}"})
    assert r.status_code == 200 and r.json() == {"email": "me@example.com"}


async def test_garbage_bearer_is_401_invalid_token(probe_client):
    c, _ = probe_client
    r = await c.get("/whoami", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_token"


async def test_admin_dep_forbids_non_admin(probe_client):
    c, db = probe_client
    reg = await AuthService(db).register("u@example.com", "correct-passphrase", "U",
                                         ip=None, user_agent=None)
    r = await c.get("/admin-only", headers={"Authorization": f"Bearer {reg.access_token}"})
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
