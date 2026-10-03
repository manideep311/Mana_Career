"""AccountEmailService -- DB integration, CI-deferred."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.domain.auth.account_emails import MAX_PER_HOUR, AccountEmailService, InvalidLinkError
from app.domain.auth.tokens import hash_link_token
from app.models.auth import AuthToken
from app.models.user import User


async def _user(db_session, email: str, status: str = "active") -> User:
    u = User(email=email, password_hash="x", full_name="Asha Rao", status=status)
    db_session.add(u)
    await db_session.flush()
    return u


def _svc(db_session) -> AccountEmailService:
    return AccountEmailService(db_session, get_settings())


async def test_a_link_works_once(db_session):
    u = await _user(db_session, "link-once@x.com")
    raw = await _svc(db_session).issue(u, "password_reset")
    assert raw is not None
    stored = (await db_session.execute(select(AuthToken))).scalars().all()
    assert all(raw not in t.token_hash for t in stored)  # only the hash is kept
    assert (await _svc(db_session).consume(raw, "password_reset")).id == u.id
    with pytest.raises(InvalidLinkError):
        await _svc(db_session).consume(raw, "password_reset")


async def test_a_newer_link_retires_the_older_one(db_session):
    u = await _user(db_session, "link-newer@x.com")
    old = await _svc(db_session).issue(u, "password_reset")
    new = await _svc(db_session).issue(u, "password_reset")
    assert old and new
    with pytest.raises(InvalidLinkError):
        await _svc(db_session).consume(old, "password_reset")
    assert (await _svc(db_session).consume(new, "password_reset")).id == u.id


async def test_links_of_the_other_kind_are_unaffected_and_not_interchangeable(db_session):
    u = await _user(db_session, "link-kinds@x.com")
    verify = await _svc(db_session).issue(u, "email_verify")
    reset = await _svc(db_session).issue(u, "password_reset")
    assert verify and reset
    with pytest.raises(InvalidLinkError):
        await _svc(db_session).consume(verify, "password_reset")
    assert (await _svc(db_session).consume(verify, "email_verify")).id == u.id


async def test_expired_links_are_refused(db_session):
    u = await _user(db_session, "link-expired@x.com")
    raw = await _svc(db_session).issue(u, "password_reset")
    assert raw
    row = (
        await db_session.execute(
            select(AuthToken).where(AuthToken.token_hash == hash_link_token(raw))
        )
    ).scalar_one()
    row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    await db_session.flush()
    with pytest.raises(InvalidLinkError):
        await _svc(db_session).consume(raw, "password_reset")


async def test_disabled_accounts_cannot_use_links(db_session):
    u = await _user(db_session, "link-disabled@x.com")
    raw = await _svc(db_session).issue(u, "password_reset")
    u.status = "disabled"
    await db_session.flush()
    with pytest.raises(InvalidLinkError):
        await _svc(db_session).consume(raw or "", "password_reset")


async def test_requests_are_limited_per_hour(db_session):
    u = await _user(db_session, "link-throttle@x.com")
    issued = [await _svc(db_session).issue(u, "password_reset") for _ in range(MAX_PER_HOUR)]
    assert all(issued)
    assert await _svc(db_session).issue(u, "password_reset") is None
    # The other kind has its own allowance.
    assert await _svc(db_session).issue(u, "email_verify") is not None


async def test_garbage_tokens_are_refused_cheaply(db_session):
    for raw in ("", "x" * 500, "not-a-real-token"):
        with pytest.raises(InvalidLinkError):
            await _svc(db_session).consume(raw, "email_verify")
