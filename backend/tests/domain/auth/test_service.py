import datetime as dt

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import AuthError, ConflictError, ForbiddenError
from app.domain.auth.service import REFRESH_REUSE_GRACE, AuthService
from app.domain.auth.tokens import decode_access_token, hash_refresh_token
from app.models.audit import AuditLog
from app.models.auth import RefreshToken


def _svc(db_session) -> AuthService:
    return AuthService(db_session)


async def test_register_creates_user_and_tokens(db_session):
    svc = _svc(db_session)
    res = await svc.register("New@Example.com", "a-strong-passphrase", "New User",
                             ip="1.2.3.4", user_agent="pytest")
    assert res.user.email == "New@Example.com"
    assert decode_access_token(res.access_token, settings=get_settings()).user_id == res.user.id
    stored = (await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(res.refresh_token)
        )
    )).scalar_one()
    assert stored.revoked_at is None


async def test_register_duplicate_email_raises_conflict(db_session):
    svc = _svc(db_session)
    await svc.register("dup@example.com", "a-strong-passphrase", "A", ip=None, user_agent=None)
    with pytest.raises(ConflictError) as ei:
        await svc.register("DUP@example.com", "another-passphrase", "B", ip=None, user_agent=None)
    assert ei.value.code == "email_taken"


async def test_authenticate_ok_and_bad_password(db_session):
    svc = _svc(db_session)
    await svc.register("log@example.com", "correct-passphrase", "L", ip=None, user_agent=None)
    ok = await svc.authenticate("log@example.com", "correct-passphrase", ip=None, user_agent=None)
    assert ok.access_token
    with pytest.raises(AuthError) as ei:
        await svc.authenticate("log@example.com", "wrong", ip=None, user_agent=None)
    assert ei.value.code == "invalid_credentials"


async def test_authenticate_unknown_email_is_invalid_credentials_not_404(db_session):
    svc = _svc(db_session)
    with pytest.raises(AuthError) as ei:
        await svc.authenticate("nobody@example.com", "x", ip=None, user_agent=None)
    assert ei.value.code == "invalid_credentials"


async def test_authenticate_disabled_account(db_session):
    svc = _svc(db_session)
    res = await svc.register("dis@example.com", "correct-passphrase", "D", ip=None, user_agent=None)
    res.user.status = "disabled"
    await db_session.flush()
    with pytest.raises(ForbiddenError) as ei:
        await svc.authenticate("dis@example.com", "correct-passphrase", ip=None, user_agent=None)
    assert ei.value.code == "account_disabled"


async def test_rotate_issues_new_and_revokes_old(db_session):
    svc = _svc(db_session)
    reg = await svc.register("rot@example.com", "correct-passphrase", "R", ip=None, user_agent=None)
    rotated = await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    assert rotated.refresh_token != reg.refresh_token
    old = (await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(reg.refresh_token)
        )
    )).scalar_one()
    assert old.revoked_at is not None and old.replaced_by_id is not None


async def test_rotate_reuse_detection_revokes_family(db_session):
    svc = _svc(db_session)
    reg = await svc.register("reuse@example.com", "correct-passphrase", "R",
                             ip=None, user_agent=None)
    await svc.rotate(reg.refresh_token, ip=None, user_agent=None)          # first rotation OK
    await _age_rotation(db_session, reg.refresh_token)                      # past the grace window
    with pytest.raises(AuthError) as ei:
        await svc.rotate(reg.refresh_token, ip=None, user_agent=None)      # replay the old one
    assert ei.value.code == "refresh_reuse"
    live = (await db_session.execute(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    )).scalar_one()
    assert live == 0  # whole family killed
    assert (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "auth.refresh_reuse_detected")
    )).first() is not None


async def test_rotate_expired_refresh(db_session):
    svc = _svc(db_session)
    reg = await svc.register("exp@example.com", "correct-passphrase", "E", ip=None, user_agent=None)
    row = (await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(reg.refresh_token)
        )
    )).scalar_one()
    row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    await db_session.flush()
    with pytest.raises(AuthError) as ei:
        await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    assert ei.value.code == "expired_refresh"


async def test_logout_revokes_family_and_is_silent_on_unknown(db_session):
    svc = _svc(db_session)
    reg = await svc.register("out@example.com", "correct-passphrase", "O", ip=None, user_agent=None)
    await svc.logout(reg.refresh_token)
    await svc.logout("never-issued")  # no raise
    live = (await db_session.execute(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    )).scalar_one()
    assert live == 0


async def test_change_password_rotates_all_and_sets_new_hash(db_session):
    svc = _svc(db_session)
    reg = await svc.register("pw@example.com", "old-passphrase", "P", ip=None, user_agent=None)
    await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    fresh = await svc.change_password(reg.user, "old-passphrase", "new-passphrase",
                                     ip=None, user_agent=None)
    assert fresh.refresh_token
    with pytest.raises(AuthError):
        await svc.authenticate("pw@example.com", "old-passphrase", ip=None, user_agent=None)
    ok = await svc.authenticate("pw@example.com", "new-passphrase", ip=None, user_agent=None)
    assert ok.access_token


async def _age_rotation(db_session, raw: str) -> None:
    """Pretend the token was rotated long enough ago to be outside the grace window."""
    row = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
    )).scalar_one()
    row.revoked_at = dt.datetime.now(dt.UTC) - REFRESH_REUSE_GRACE - dt.timedelta(seconds=1)
    await db_session.flush()


async def _live_count(db_session, family_id) -> int:
    return (await db_session.execute(
        select(func.count()).select_from(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
        )
    )).scalar_one()


async def test_parallel_refresh_within_grace_keeps_the_session(db_session):
    """Two tabs refreshing at once present the same cookie: not theft."""
    svc = _svc(db_session)
    reg = await svc.register("parallel@example.com", "correct-passphrase", "P",
                             ip=None, user_agent=None)
    first = await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    second = await svc.rotate(reg.refresh_token, ip=None, user_agent=None)  # same cookie
    assert second.refresh_token not in (reg.refresh_token, first.refresh_token)

    family = decode_access_token(first.access_token, settings=get_settings()).session_id
    assert decode_access_token(second.access_token, settings=get_settings()).session_id == family
    assert await _live_count(db_session, family) == 2  # both tabs keep working
    assert await svc.is_session_live(reg.user.id, family)
    audit_actions = set((await db_session.execute(select(AuditLog.action))).scalars())
    assert "auth.refresh_parallel" in audit_actions
    assert "auth.refresh_reuse_detected" not in audit_actions


async def test_logged_out_token_gets_no_grace(db_session):
    svc = _svc(db_session)
    reg = await svc.register("nograce@example.com", "correct-passphrase", "N",
                             ip=None, user_agent=None)
    await svc.logout(reg.refresh_token)
    with pytest.raises(AuthError):
        await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    family = decode_access_token(reg.access_token, settings=get_settings()).session_id
    assert not await svc.is_session_live(reg.user.id, family)


async def test_rotate_locks_the_presented_token(db_session):
    """The SELECT in rotate() must be FOR UPDATE so concurrent refreshes serialize."""
    from sqlalchemy import event

    statements: list[str] = []
    engine = db_session.bind.engine if hasattr(db_session.bind, "engine") else db_session.bind
    sync_engine = engine.sync_engine

    def _capture(conn, cursor, statement, *args):
        statements.append(statement)

    svc = _svc(db_session)
    reg = await svc.register("lock@example.com", "correct-passphrase", "L",
                             ip=None, user_agent=None)
    event.listen(sync_engine, "before_cursor_execute", _capture)
    try:
        await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _capture)
    assert any(
        "FROM refresh_tokens" in s and "FOR UPDATE" in s for s in statements
    ), statements
