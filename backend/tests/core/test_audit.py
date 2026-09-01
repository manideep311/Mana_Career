import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.audit import audit
from app.models.audit import AuditLog


async def test_audit_writes_a_row(db_session):
    uid = uuid.uuid4()
    await audit(
        db_session,
        actor_type="user",
        action="auth.login",
        actor_user_id=uid,
        request_id="req-1",
        ip="127.0.0.1",
    )
    row = (await db_session.execute(select(AuditLog))).scalars().one()
    assert row.action == "auth.login"
    assert row.actor_user_id == uid
    assert row.result == "success"


async def test_audit_propagates_write_failure(db_session):
    # invalid actor_type violates the CHECK constraint. A failed audit write is a
    # real error: audit() must propagate it (not silently roll back the caller's
    # transaction and return as if nothing happened).
    with pytest.raises((IntegrityError, DBAPIError)):
        await audit(db_session, actor_type="not-a-valid-actor", action="x")
    await db_session.rollback()
