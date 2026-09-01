import contextlib
import io
import uuid

from pypdf import PdfWriter
from sqlalchemy import select

from app.domain.auth.service import AuthService
from app.models.resume import Resume
from app.worker.tasks.resume import parse_resume


class _MemStore:
    def __init__(self, blob=b""):
        self.blob = blob

    async def get(self, k):
        return self.blob


@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


async def _anoop() -> None:
    return None


async def _seed_resume(db_session, *, text_blob: bytes) -> tuple[uuid.UUID, Resume]:
    reg = await AuthService(db_session).register(
        "wt@example.com", "correct-passphrase", "W", ip=None, user_agent=None
    )
    r = Resume(
        user_id=reg.user.id,
        file_ref="k",
        content_type="application/pdf",
        size_bytes=len(text_blob),
        status="uploaded",
    )
    db_session.add(r)
    await db_session.flush()
    return reg.user.id, r


async def test_parse_marks_scanned_pdf_failed(db_session, monkeypatch, fake_redis):
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    _, r = await _seed_resume(db_session, text_blob=buf.getvalue())

    monkeypatch.setattr("app.worker.tasks.resume._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr(
        "app.worker.tasks.resume.get_file_store", lambda s: _MemStore(buf.getvalue())
    )
    monkeypatch.setattr("app.worker.tasks.resume.redis_from_settings", lambda s: fake_redis)
    enq = []
    monkeypatch.setattr(
        "app.worker.tasks.resume.enqueue", lambda *a, **k: enq.append(a) or _anoop()
    )

    await parse_resume({}, str(r.id))
    fresh = (
        await db_session.execute(select(Resume).where(Resume.id == r.id))
    ).scalar_one()
    assert fresh.status == "failed"
    assert "scanned" in fresh.parse_error.lower()
    assert enq == []  # extract not enqueued
