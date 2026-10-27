"""Demo retention: accounts past DEMO_RETENTION_DAYS are deleted in full."""
from __future__ import annotations

import contextlib
import datetime as dt
import functools

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.domain.account.deletion import AccountDeleter
from app.infra.storage.local import LocalFileStore
from app.models.audit import AuditLog
from app.models.resume import Resume
from app.models.user import User
from app.worker.tasks import retention
from app.worker.tasks.retention import expire_demo_accounts

NOW = dt.datetime.now(dt.UTC)


@contextlib.asynccontextmanager
async def _ctx(session):
    yield session


@pytest.fixture
def wired(db_session, monkeypatch, tmp_path):
    store = LocalFileStore(str(tmp_path))
    deleted_runs: list[str] = []

    class Saver:
        async def adelete_thread(self, thread_id: str) -> None:
            deleted_runs.append(thread_id)

    async def checkpointer(_settings):
        return Saver()

    def use(days: int) -> None:
        settings = get_settings().model_copy(update={"demo_retention_days": days})
        monkeypatch.setattr(retention, "get_settings", lambda: settings)

    monkeypatch.setattr(retention, "_session_for", lambda: _ctx(db_session))
    monkeypatch.setattr(retention, "get_file_store", lambda _s: store)
    monkeypatch.setattr(
        retention, "AccountDeleter", functools.partial(AccountDeleter, checkpointer=checkpointer)
    )
    return store, deleted_runs, use


async def _age(db_session, user: User, days: int) -> None:
    await db_session.execute(
        update(User).where(User.id == user.id).values(created_at=NOW - dt.timedelta(days=days))
    )


async def test_accounts_past_retention_go_with_their_files(db_session, seed_person, wired):
    store, deleted_runs, use = wired
    use(7)
    old = await seed_person("expire-old@x.com", store=store)
    new = await seed_person("expire-new@x.com", store=store)
    await _age(db_session, old.user, 8)
    await _age(db_session, new.user, 2)
    old_id = old.user.id

    result = await expire_demo_accounts({}, now=NOW)

    assert result["accounts"] >= 1
    assert await db_session.get(User, old_id) is None
    assert (
        await db_session.execute(select(Resume).where(Resume.user_id == old_id))
    ).first() is None
    with pytest.raises(NotFoundError):
        await store.get(old.file_ref)
    assert old.run_id in deleted_runs
    # The younger account and its file are untouched.
    assert await db_session.get(User, new.user.id) is not None
    assert await store.get(new.file_ref)
    # The audit trail says the system expired it, with nothing personal.
    record = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.actor_user_id == old_id, AuditLog.action == "account.expired"
            )
        )
    ).scalar_one()
    assert record.actor_type == "system" and record.ip is None


async def test_no_retention_keeps_everyone(db_session, seed_person, wired):
    store, _, use = wired
    use(0)
    old = await seed_person("expire-never@x.com", store=store)
    await _age(db_session, old.user, 400)
    assert await expire_demo_accounts({}, now=NOW) == {"accounts": 0}
    assert await db_session.get(User, old.user.id) is not None
