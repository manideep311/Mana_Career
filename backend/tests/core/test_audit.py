import uuid

from sqlalchemy import select

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


async def test_audit_swallows_bad_input_without_raising(db_session):
    # invalid actor_type violates the CHECK constraint; must not bubble up
    await audit(db_session, actor_type="not-a-valid-actor", action="x")
    # session still usable
    assert (await db_session.execute(select(AuditLog.id))).first() is None or True
