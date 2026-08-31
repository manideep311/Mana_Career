import datetime as dt
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.auth import RefreshToken
from app.models.user import User


async def _mk_user(db_session, email="A.Person@Example.com") -> User:
    u = User(email=email, password_hash="x", full_name="A Person")
    db_session.add(u)
    await db_session.flush()
    return u


async def test_user_round_trip_and_defaults(db_session):
    u = await _mk_user(db_session)
    got = (await db_session.execute(select(User).where(User.id == u.id))).scalar_one()
    assert got.status == "active"
    assert got.is_admin is False
    assert got.created_at is not None


async def test_email_is_case_insensitive_unique(db_session):
    await _mk_user(db_session, "dup@example.com")
    with pytest.raises(IntegrityError):
        await _mk_user(db_session, "DUP@example.com")


async def test_status_check_constraint(db_session):
    u = await _mk_user(db_session, "s@example.com")
    u.status = "banana"
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_updated_at_trigger_bumps_on_update(db_session):
    u = await _mk_user(db_session, "t@example.com")
    first = (await db_session.execute(
        text("SELECT updated_at FROM users WHERE id = :i"), {"i": u.id}
    )).scalar_one()
    u.full_name = "Renamed"
    await db_session.flush()
    await db_session.execute(
        text("UPDATE users SET full_name = full_name WHERE id = :i"), {"i": u.id}
    )
    second = (await db_session.execute(
        text("SELECT updated_at FROM users WHERE id = :i"), {"i": u.id}
    )).scalar_one()
    assert second >= first


async def test_refresh_token_fk_cascade_on_user_delete(db_session):
    u = await _mk_user(db_session, "c@example.com")
    rt = RefreshToken(
        user_id=u.id, token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        family_id=uuid.uuid4(),
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
    )
    db_session.add(rt)
    await db_session.flush()
    await db_session.delete(u)
    await db_session.flush()
    remaining = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.id == rt.id))
    ).first()
    assert remaining is None


async def test_token_hash_unique(db_session):
    u = await _mk_user(db_session, "h@example.com")
    h = uuid.uuid4().hex + uuid.uuid4().hex
    for _ in range(2):
        db_session.add(RefreshToken(
            user_id=u.id, token_hash=h, family_id=uuid.uuid4(),
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
        ))
    with pytest.raises(IntegrityError):
        await db_session.flush()
