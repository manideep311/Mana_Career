"""ApplicationEvent model round-trip -- DB integration, CI-deferred."""
from __future__ import annotations

from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.job import Job
from app.models.user import User


async def test_application_event_round_trip(db_session):
    u = User(email="app-events@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    app_row = Application(user_id=u.id, job_id=j.id, status="saved", source="user")
    db_session.add(app_row)
    await db_session.flush()

    ev = ApplicationEvent(
        application_id=app_row.id, user_id=u.id, kind="status_change",
        from_status=None, to_status="saved",
    )
    db_session.add(ev)
    await db_session.flush()
    await db_session.refresh(ev)  # pull server defaults (meta, occurred_at, created_at)
    assert ev.meta == {}
    assert ev.occurred_at is not None
    assert ev.created_at is not None
