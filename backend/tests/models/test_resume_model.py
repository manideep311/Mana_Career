import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.resume import Resume
from app.models.user import User


async def _user(db_session, email="r@example.com") -> User:
    u = User(email=email, password_hash="x", full_name="R")
    db_session.add(u)
    await db_session.flush()
    return u


async def test_defaults(db_session):
    u = await _user(db_session)
    r = Resume(user_id=u.id, file_ref="resumes/x.pdf", content_type="application/pdf",
               size_bytes=1234, original_filename="cv.pdf")
    db_session.add(r)
    await db_session.flush()
    got = (await db_session.execute(select(Resume).where(Resume.id == r.id))).scalar_one()
    assert got.status == "uploaded"
    assert got.is_primary is False
    assert got.page_count is None
    assert got.confirmed_at is None


async def test_status_check(db_session):
    u = await _user(db_session, "s@example.com")
    r = Resume(user_id=u.id, file_ref="f", content_type="application/pdf", size_bytes=1)
    r.status = "weird"
    db_session.add(r)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_primary_per_user(db_session):
    u = await _user(db_session, "p@example.com")
    for i in range(2):
        db_session.add(Resume(user_id=u.id, file_ref=f"f{i}", content_type="application/pdf",
                              size_bytes=1, is_primary=True))
    with pytest.raises(IntegrityError):
        await db_session.flush()
