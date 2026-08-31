from __future__ import annotations

import base64
import datetime as dt
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models.base import Base, TimestampMixin

__all__ = [
    "AsyncSessionLocal",
    "Base",
    "Repository",
    "TimestampMixin",
    "engine",
    "get_session",
    "make_engine",
    "make_session_factory",
]


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, future=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


_settings = get_settings()
engine: AsyncEngine = make_engine(_settings.database_url)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = make_session_factory(engine)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _encode_cursor(created_at: dt.datetime, id_: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{id_}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, id_ = raw.split("|")
    return dt.datetime.fromisoformat(ts), uuid.UUID(id_)


class Repository[ModelT: Base]:
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_or_none(self, id_: Any, *, user_id: uuid.UUID) -> ModelT | None:
        obj = await self.session.get(self.model, id_)
        if obj is None:
            return None
        row_user = getattr(obj, "user_id", None)
        row_owner = getattr(obj, "owner_id", None)
        if row_user == user_id or (row_user is None and row_owner is None):
            return obj
        return None

    async def get(self, id_: Any, *, user_id: uuid.UUID) -> ModelT:
        obj = await self.get_or_none(id_, user_id=user_id)
        if obj is None:
            raise NotFoundError(detail=f"{self.model.__name__} {id_} not found")
        return obj

    async def list_for(
        self, user_id: uuid.UUID, *, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[ModelT], str | None]:
        model: Any = self.model
        stmt = (
            select(self.model)
            .where(model.user_id == user_id)
            .order_by(model.created_at.desc(), model.id.desc())
            .limit(limit + 1)
        )
        if cursor:
            c_ts, c_id = _decode_cursor(cursor)
            stmt = stmt.where(
                tuple_(model.created_at, model.id) < tuple_(literal(c_ts), literal(c_id))
            )
        rows = list((await self.session.execute(stmt)).scalars().all())
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last: Any = rows[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)
        return rows, next_cursor

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()
