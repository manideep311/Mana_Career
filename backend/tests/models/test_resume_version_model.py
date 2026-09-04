from sqlalchemy import select

from app.models.resume import Resume
from app.models.resume_version import ResumeSuggestion, ResumeVersion
from app.models.user import User


async def test_version_and_suggestion_roundtrip(db_session):
    u = User(email="rv@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()

    r = Resume(
        user_id=u.id, file_ref="r.pdf", content_type="application/pdf", size_bytes=100,
    )
    db_session.add(r)
    await db_session.flush()

    v = ResumeVersion(
        user_id=u.id, resume_id=r.id, kind="ai_tailored",
        content={"full_name": "A"}, generation_meta={"model": "fake"},
    )
    db_session.add(v)
    await db_session.flush()

    s = ResumeSuggestion(
        user_id=u.id, resume_version_id=v.id, section="summary",
        suggestion_type="rewrite", title="Tighten the summary", body="Make it punchier.",
    )
    db_session.add(s)
    await db_session.flush()

    got_v = (
        await db_session.execute(select(ResumeVersion).where(ResumeVersion.id == v.id))
    ).scalar_one()
    got_s = (
        await db_session.execute(select(ResumeSuggestion).where(ResumeSuggestion.id == s.id))
    ).scalar_one()
    assert got_v.kind == "ai_tailored"
    assert got_v.content == {"full_name": "A"}
    assert got_v.created_by == "user"  # server default, not set above
    assert got_s.status == "open"  # server default, not set above
