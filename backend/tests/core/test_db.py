import uuid

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Repository, TimestampMixin
from app.core.errors import NotFoundError


class _Widget(Base, TimestampMixin):
    __tablename__ = "_widget"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest.fixture(autouse=True)
async def _create_widget_table(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(_Widget.__table__.create, checkfirst=True)
    yield
    async with db_engine.begin() as conn:
        await conn.run_sync(_Widget.__table__.drop, checkfirst=True)


async def test_add_and_get_scoped_to_user(db_session):
    me = uuid.uuid4()
    repo = Repository(db_session, _Widget)
    w = await repo.add(_Widget(id=uuid.uuid4(), user_id=me, name="mine"))
    got = await repo.get(w.id, user_id=me)
    assert got.name == "mine"


async def test_get_rejects_other_users_row(db_session):
    me, other = uuid.uuid4(), uuid.uuid4()
    repo = Repository(db_session, _Widget)
    w = await repo.add(_Widget(id=uuid.uuid4(), user_id=other, name="theirs"))
    with pytest.raises(NotFoundError):
        await repo.get(w.id, user_id=me)


async def test_get_allows_shared_row(db_session):
    me = uuid.uuid4()
    repo = Repository(db_session, _Widget)
    w = await repo.add(_Widget(id=uuid.uuid4(), user_id=None, owner_id=None, name="seed"))
    got = await repo.get(w.id, user_id=me)
    assert got.name == "seed"


async def test_list_for_paginates_by_cursor(db_session):
    me = uuid.uuid4()
    repo = Repository(db_session, _Widget)
    for i in range(5):
        await repo.add(_Widget(id=uuid.uuid4(), user_id=me, name=f"w{i}"))
    page1, cursor = await repo.list_for(me, limit=2)
    assert len(page1) == 2 and cursor is not None
    page2, _ = await repo.list_for(me, limit=2, cursor=cursor)
    assert {w.id for w in page1}.isdisjoint({w.id for w in page2})
