import contextlib

from sqlalchemy import select

from app.domain.auth.service import AuthService
from app.domain.profile.service import ProfileService
from app.models.profile import ProfileExperience
from app.models.skill import ProfileSkill, Skill
from app.worker.tasks.profile import build_profile


@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


async def test_build_profile_task_writes_profile_skills(db_session, monkeypatch):
    monkeypatch.setattr("app.worker.tasks.profile._session_for", lambda: _ctx(db_session))
    for slug, label in [("python", "Python"), ("fastapi", "FastAPI")]:
        db_session.add(Skill(slug=slug, label=label, category="backend", aliases=[]))
    reg = await AuthService(db_session).register(
        "pt@example.com", "correct-passphrase", "P", ip=None, user_agent=None
    )
    uid = reg.user.id
    profile = await ProfileService(db_session).get_or_create(uid)
    db_session.add(
        ProfileExperience(
            user_id=uid,
            profile_id=profile.id,
            company="A",
            title="T",
            source="resume_extraction",
            order_index=0,
            tech=["Python", "FastAPI"],
        )
    )
    await db_session.flush()

    out = await build_profile({}, str(uid))
    assert out["matched"] == 2
    rows = (
        await db_session.execute(
            select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
        )
    ).scalars().all()
    assert len(rows) == 2
