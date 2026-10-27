"""Reading a résumé while the AI quota is paused or busy."""

from __future__ import annotations

import contextlib

import pytest
from arq.worker import Retry
from sqlalchemy import select

from app.core.errors import AIPausedError, AIUnavailableError
from app.domain.auth.service import AuthService
from app.models.resume import Resume
from app.worker.retry import MAX_TRIES
from app.worker.tasks.resume import extract_resume

TEXT = (
    "Jordan Rivera - Data Analyst\njordan@example.com\n"
    "Skills: SQL, Python, Tableau\nhttps://github.com/jrivera"
)


class _Unavailable:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def complete(self, *args, **kwargs):
        raise self.exc


@contextlib.asynccontextmanager
async def _ctx(session):
    yield session


async def _parsed_resume(db_session, email: str) -> Resume:
    reg = await AuthService(db_session).register(
        email, "correct-passphrase", "J", ip=None, user_agent=None
    )
    r = Resume(
        user_id=reg.user.id, file_ref="k", content_type="application/pdf", size_bytes=1,
        status="parsed", extracted_text=TEXT,
    )
    db_session.add(r)
    await db_session.flush()
    return r


@pytest.fixture
def wire(db_session, monkeypatch, fake_redis):
    def _wire(exc: Exception) -> None:
        monkeypatch.setattr("app.worker.tasks.resume._session_for", lambda: _ctx(db_session))
        monkeypatch.setattr("app.worker.tasks.resume.redis_from_settings", lambda s: fake_redis)
        monkeypatch.setattr(
            "app.worker.tasks.resume.get_llm_provider", lambda s: _Unavailable(exc)
        )

    return _wire


async def _fresh(db_session, rid) -> Resume:
    return (await db_session.execute(select(Resume).where(Resume.id == rid))).scalar_one()


async def test_a_paused_ai_still_reads_skills_and_links_from_the_text(db_session, wire):
    wire(AIPausedError())
    r = await _parsed_resume(db_session, "paused@example.com")
    assert (await extract_resume({"job_try": 1}, str(r.id)))["status"] == "extracted"
    fresh = await _fresh(db_session, r.id)
    assert fresh.status == "extracted"
    assert {"SQL", "Python"} <= set(fresh.extraction["skills"])
    assert fresh.extraction["email"] == "jordan@example.com"
    assert fresh.extraction["github_url"] == "https://github.com/jrivera"


async def test_a_busy_ai_is_retried_then_fails_with_a_plain_message(db_session, wire):
    wire(AIUnavailableError(retry_after=20))
    r = await _parsed_resume(db_session, "busy@example.com")
    with pytest.raises(Retry):
        await extract_resume({"job_try": 1}, str(r.id))
    with pytest.raises(AIUnavailableError):
        await extract_resume({"job_try": MAX_TRIES}, str(r.id))
    fresh = await _fresh(db_session, r.id)
    assert fresh.status == "failed"
    assert fresh.parse_error == "The free AI quota is busy, try again shortly"
