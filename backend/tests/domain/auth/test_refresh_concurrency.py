"""DB-gated, real concurrency: simultaneous refreshes with one cookie.

Each refresh runs in its own connection and transaction (not the shared,
rolled-back test session), exactly like parallel HTTP requests. Before the fix,
the second rotation saw an already-rotated token, treated it as theft and
revoked the whole session — logging a legitimate user out.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.db import make_session_factory
from app.core.errors import AuthError
from app.domain.auth.service import AccessResult, AuthService
from app.domain.auth.tokens import decode_access_token
from app.models.audit import AuditLog
from app.models.user import User


async def test_concurrent_refreshes_with_one_cookie_keep_the_session(db_engine) -> None:
    factory = make_session_factory(db_engine)
    email = f"concurrent-{uuid.uuid4().hex}@example.com"
    async with factory() as session:
        reg = await AuthService(session).register(
            email, "correct-passphrase", "C", ip=None, user_agent=None
        )
        await session.commit()
        user_id = reg.user.id

    async def refresh_once() -> AccessResult | AuthError:
        async with factory() as session:
            try:
                result = await AuthService(session).rotate(
                    reg.refresh_token, ip=None, user_agent=None
                )
                await session.commit()
                return result
            except AuthError as exc:
                await session.rollback()
                return exc

    try:
        results = await asyncio.gather(*(refresh_once() for _ in range(4)))
        failures = [r for r in results if isinstance(r, AuthError)]
        assert failures == [], [f.code for f in failures]

        tokens = [r for r in results if isinstance(r, AccessResult)]
        sessions = {
            decode_access_token(t.access_token, settings=get_settings()).session_id
            for t in tokens
        }
        assert len(sessions) == 1  # all four stayed in the same sign-in
        async with factory() as session:
            assert await AuthService(session).is_session_live(user_id, sessions.pop())
            reuse_alerts = await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action == "auth.refresh_reuse_detected",
                    AuditLog.actor_user_id == user_id,
                )
            )
            assert reuse_alerts == 0
    finally:
        async with factory() as session:
            await session.execute(delete(User).where(User.id == user_id))  # cascades tokens
            await session.commit()
