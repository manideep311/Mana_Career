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


# --------------------------------------------------------------------------- #
# Retry / terminal-failure behaviour (DB-gated)
# --------------------------------------------------------------------------- #
import os  # noqa: E402

import pytest  # noqa: E402
from arq.worker import Retry  # noqa: E402

from app.worker import retry as retry_policy  # noqa: E402
from app.worker.retry import MAX_TRIES  # noqa: E402


def _text_pdf(lines: list[str]) -> bytes:
    """A one-page PDF whose content stream draws ``lines`` of real text."""
    ops = ["BT /F1 11 Tf 40 760 Td"]
    for i, line in enumerate(lines):
        safe = line.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")
        ops.append(f"({safe}) Tj" if i == 0 else f"0 -16 Td ({safe}) Tj")
    ops.append("ET")
    stream = " ".join(ops).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (n, body)
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        pdf += b"%010d 00000 n \n" % off
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(pdf)


_RESUME_LINES = [
    "Jordan Rivera - Data Analyst",
    "jordan@example.com",
    "Experience: Analyst at Northwind Traders 2021-2024",
    "Built SQL dashboards in Tableau used by 40 regional managers",
    "Automated weekly reporting with Python and pandas, saving 6 hours a week",
    "Skills: SQL, Python, Tableau, Excel, statistics",
]


class _RecordingRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def aclose(self) -> None:
        return None


class _FlakyStore:
    """Raises a transient OSError for the first ``failures`` reads."""

    def __init__(self, blob: bytes, *, failures: int) -> None:
        self.blob = blob
        self.failures = failures
        self.calls = 0

    async def get(self, key: str) -> bytes:
        self.calls += 1
        if self.calls <= self.failures:
            raise OSError("file store temporarily unavailable")
        return self.blob


def _patch_task(monkeypatch, db_session, store, redis) -> None:
    monkeypatch.setattr("app.worker.tasks.resume._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.resume.get_file_store", lambda s: store)
    monkeypatch.setattr("app.worker.tasks.resume.redis_from_settings", lambda s: redis)
    monkeypatch.setattr("app.worker.tasks.resume.enqueue", lambda *a, **k: _anoop())


async def _status_of(db_session, rid) -> Resume:
    db_session.expire_all()
    return (await db_session.execute(select(Resume).where(Resume.id == rid))).scalar_one()


async def test_transient_error_raises_arq_retry_then_final_attempt_fails_explicitly(
    db_session, monkeypatch
):
    pdf = _text_pdf(_RESUME_LINES)
    _, r = await _seed_resume(db_session, text_blob=pdf)
    rid = r.id
    await db_session.commit()  # survive the task's rollback on error
    store, redis = _FlakyStore(pdf, failures=99), _RecordingRedis()
    _patch_task(monkeypatch, db_session, store, redis)

    with pytest.raises(Retry):
        await parse_resume({"job_try": 1}, str(rid))
    assert (await _status_of(db_session, rid)).status == "parsing"
    assert not any('"failed"' in msg for _, msg in redis.published)

    with pytest.raises(OSError):
        await parse_resume({"job_try": MAX_TRIES}, str(rid))
    fresh = await _status_of(db_session, rid)
    assert fresh.status == "failed"
    assert fresh.parse_error == "We couldn't read this file."
    assert any('"failed"' in msg for _, msg in redis.published)


async def test_unreadable_pdf_fails_on_first_attempt_without_retry(db_session, monkeypatch):
    blob = b"%PDF-1.4 this is not really a pdf"
    _, r = await _seed_resume(db_session, text_blob=blob)
    rid = r.id
    await db_session.commit()
    _patch_task(monkeypatch, db_session, _FlakyStore(blob, failures=0), _RecordingRedis())

    with pytest.raises(Exception) as caught:
        await parse_resume({"job_try": 1}, str(rid))
    assert not isinstance(caught.value, Retry)
    assert (await _status_of(db_session, rid)).status == "failed"


async def test_real_arq_worker_retries_parse_resume_until_it_succeeds(
    db_session, monkeypatch
):
    """End to end through a genuine ARQ worker: a transient file-store error on
    the first attempt is retried by ARQ and the résumé reaches ``parsed``."""
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379/1"))
    settings.conn_retries = 0
    queue = f"test:parse-retry:{uuid.uuid4().hex}"
    try:
        pool = await create_pool(settings, default_queue_name=queue)
        await pool.ping()
    except Exception as exc:  # any connection failure means "no Redis"
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Redis unavailable locally ({exc!r}); runs in CI")

    pdf = _text_pdf(_RESUME_LINES)
    _, r = await _seed_resume(db_session, text_blob=pdf)
    rid = r.id
    await db_session.commit()
    store = _FlakyStore(pdf, failures=1)
    _patch_task(monkeypatch, db_session, store, _RecordingRedis())
    monkeypatch.setattr(retry_policy, "BASE_DELAY_SECONDS", 0)

    try:
        await pool.enqueue_job("parse_resume", str(rid))
        worker = Worker(
            functions=[parse_resume],
            queue_name=queue,  # Worker defaults to the global "arq:queue"
            redis_pool=pool,
            burst=True,
            poll_delay=0.01,
            max_tries=MAX_TRIES,
            handle_signals=False,
        )
        try:
            await worker.main()
        finally:
            await worker.close()
    finally:
        await pool.delete(queue)
        await pool.aclose()

    assert store.calls == 2
    fresh = await _status_of(db_session, rid)
    assert fresh.status == "parsed"
    assert "Northwind" in (fresh.extracted_text or "")
