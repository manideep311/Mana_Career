"""Forgot password + email verification over HTTP -- DB integration, CI-deferred."""
from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from app.api.v1.auth import FORGOT_SENT
from app.domain.email.types import EmailMessage
from app.models.auth import AuthToken

PASSWORD = "correct-passphrase"
NEW_PASSWORD = "an-even-better-passphrase"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[EmailMessage]:
    """Capture account emails instead of sending them."""
    sent: list[EmailMessage] = []

    async def _capture(message: EmailMessage, _settings: object) -> None:
        sent.append(message)

    monkeypatch.setattr("app.api.v1.auth.deliver", _capture)
    return sent


def _token(message: EmailMessage) -> str:
    match = re.search(r"#token=([\w-]+)", message.body)
    assert match, message.body
    return match.group(1)


async def _register(client, email: str):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Asha Rao"},
    )
    assert r.status_code == 201
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return headers, r.json()["user"], r.cookies.get("mana_refresh")


async def test_sign_up_sends_a_confirmation_link_that_verifies(client, outbox):
    headers, user, _cookie = await _register(client, "verify-flow@x.com")
    assert user["email_verified"] is False
    assert [m.subject for m in outbox] == ["Confirm your email for Mana Career"]
    assert outbox[0].to_email == "verify-flow@x.com"
    assert "/verify-email#token=" in outbox[0].body

    r = await client.post("/api/v1/auth/email/verify", json={"token": _token(outbox[0])})
    assert r.status_code == 204
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["email_verified"] is True

    again = await client.post("/api/v1/auth/email/verify", json={"token": _token(outbox[0])})
    assert again.status_code == 400 and again.json()["code"] == "invalid_link"


async def test_forgot_password_reveals_nothing_about_who_has_an_account(client, db_session, outbox):
    await _register(client, "forgot-known@x.com")
    outbox.clear()
    known = await client.post("/api/v1/auth/password/forgot", json={"email": "forgot-known@x.com"})
    unknown = await client.post("/api/v1/auth/password/forgot", json={"email": "nobody@x.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"detail": FORGOT_SENT}
    assert [m.to_email for m in outbox] == ["forgot-known@x.com"]


async def test_forgot_password_answers_take_the_same_minimum_time(client, monkeypatch, outbox):
    """The real path does extra work; both are padded to one floor, so response
    time doesn't reveal whether the address has an account."""
    import app.api.v1.auth as auth_routes

    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(auth_routes, "_sleep", fake_sleep)
    await _register(client, "forgot-timing@x.com")
    await client.post("/api/v1/auth/password/forgot", json={"email": "forgot-timing@x.com"})
    await client.post("/api/v1/auth/password/forgot", json={"email": "nobody-timing@x.com"})
    # Each answer topped itself up to the floor (minus the time it already took).
    assert len(waits) == 2
    assert all(0 < w <= auth_routes.FORGOT_MIN_SECONDS for w in waits)


async def test_reset_sets_the_password_signs_out_everywhere_and_confirms_the_email(
    client, db_session, outbox
):
    _headers, _user, old_cookie = await _register(client, "reset-flow@x.com")
    assert old_cookie
    outbox.clear()
    await client.post("/api/v1/auth/password/forgot", json={"email": "reset-flow@x.com"})
    token = _token(outbox[0])
    assert outbox[0].subject == "Reset your Mana Career password"

    r = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 204

    # The session from before the reset is over.
    stale = await client.post("/api/v1/auth/refresh", cookies={"mana_refresh": old_cookie})
    assert stale.status_code == 401

    old = await client.post(
        "/api/v1/auth/login", json={"email": "reset-flow@x.com", "password": PASSWORD}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"email": "reset-flow@x.com", "password": NEW_PASSWORD}
    )
    assert new.status_code == 200 and new.json()["user"]["email_verified"] is True

    reused = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert reused.status_code == 400 and reused.json()["code"] == "invalid_link"


async def test_reset_refuses_weak_passwords_and_bad_links(client, outbox):
    short = await client.post(
        "/api/v1/auth/password/reset", json={"token": "whatever", "new_password": "short"}
    )
    assert short.status_code == 422
    bogus = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": "not-a-real-token", "new_password": NEW_PASSWORD},
    )
    assert bogus.status_code == 400 and bogus.json()["code"] == "invalid_link"


async def test_resend_is_throttled_and_stops_once_confirmed(client, db_session, outbox):
    headers, _user, _cookie = await _register(client, "resend-flow@x.com")
    first = await client.post("/api/v1/auth/email/verify/resend", headers=headers)
    assert first.status_code == 202 and "sent a new link" in first.json()["detail"]
    await client.post("/api/v1/auth/email/verify/resend", headers=headers)
    limited = await client.post("/api/v1/auth/email/verify/resend", headers=headers)
    assert "several links recently" in limited.json()["detail"]
    tokens = (
        await db_session.execute(select(AuthToken).where(AuthToken.purpose == "email_verify"))
    ).scalars().all()
    assert len([t for t in tokens if t.used_at is None]) == 1  # only the newest works

    await client.post("/api/v1/auth/email/verify", json={"token": _token(outbox[-1])})
    done = await client.post("/api/v1/auth/email/verify/resend", headers=headers)
    assert done.json()["detail"] == "Your email address is already confirmed."


async def test_resend_requires_sign_in(client):
    assert (await client.post("/api/v1/auth/email/verify/resend")).status_code == 401
