import uuid

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, ValidationAppError
from app.domain.auth.service import AuthService
from app.domain.resume.extractor import ExtractedExperience, ResumeExtraction
from app.domain.resume.service import ResumeService
from app.models.profile import ProfileExperience
from app.models.resume import Resume


class _MemStore:
    def __init__(self): self.d = {}
    async def put(self, k, data, *, content_type): self.d[k] = data
    async def get(self, k): return self.d[k]
    async def delete(self, k): self.d.pop(k, None)
    async def exists(self, k): return k in self.d


async def _uid(db_session, email) -> uuid.UUID:
    reg = await AuthService(db_session).register(email, "correct-passphrase", "R",
                                                 ip=None, user_agent=None)
    return reg.user.id


def _svc(db_session):
    return ResumeService(db_session, file_store=_MemStore())


_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


async def _noop() -> None:
    return None


async def _anoop() -> None:
    return None


async def test_create_rejects_non_pdf(db_session, monkeypatch):
    monkeypatch.setattr("app.domain.resume.service.enqueue", lambda *a, **k: _noop())
    uid = await _uid(db_session, "np@example.com")
    with pytest.raises(ValidationAppError):
        await _svc(db_session).create(uid, filename="cv.txt", data=b"hello",
                                      declared_content_type="text/plain")


async def test_create_first_resume_is_primary(db_session, monkeypatch):
    calls = []
    async def fake_enqueue(task, *a, **k): calls.append((task, a))
    monkeypatch.setattr("app.domain.resume.service.enqueue", fake_enqueue)
    uid = await _uid(db_session, "pr@example.com")
    r = await _svc(db_session).create(uid, filename="cv.pdf", data=_PDF,
                                      declared_content_type="application/pdf")
    assert r.is_primary is True and r.status == "uploaded"
    assert calls == [("parse_resume", (str(r.id),))]


async def test_confirm_profile_requires_extracted(db_session, monkeypatch):
    monkeypatch.setattr("app.domain.resume.service.enqueue",
                        lambda *a, **k: _anoop())
    uid = await _uid(db_session, "cf@example.com")
    r = await _svc(db_session).create(uid, filename="cv.pdf", data=_PDF,
                                      declared_content_type="application/pdf")
    with pytest.raises(ConflictError):
        await _svc(db_session).confirm_profile(uid, r.id, ResumeExtraction())


async def test_confirm_profile_merges_experiences(db_session, monkeypatch):
    monkeypatch.setattr("app.domain.resume.service.enqueue",
                        lambda *a, **k: _anoop())
    uid = await _uid(db_session, "mg@example.com")
    svc = _svc(db_session)
    r = await svc.create(uid, filename="cv.pdf", data=_PDF,
                         declared_content_type="application/pdf")
    r.status = "extracted"
    await db_session.flush()
    await svc.confirm_profile(uid, r.id, ResumeExtraction(
        location="Berlin",
        experiences=[ExtractedExperience(company="Acme", title="ML Eng")],
    ))
    rows = (await db_session.execute(
        select(ProfileExperience).where(ProfileExperience.user_id == uid)
    )).scalars().all()
    assert [x.company for x in rows] == ["Acme"]
    assert all(x.source == "resume_extraction" for x in rows)
    fresh = (await db_session.execute(select(Resume).where(Resume.id == r.id))).scalar_one()
    assert fresh.confirmed_at is not None
