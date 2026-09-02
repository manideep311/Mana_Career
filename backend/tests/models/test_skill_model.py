import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.profile import CareerProfile
from app.models.skill import ProfileSkill, Skill
from app.models.user import User


async def _profile(db_session, email="sk@example.com"):
    u = User(email=email, password_hash="x", full_name="S")
    db_session.add(u)
    await db_session.flush()
    p = CareerProfile(user_id=u.id)
    db_session.add(p)
    await db_session.flush()
    return u, p


async def test_skill_slug_unique(db_session):
    db_session.add(Skill(slug="pytorch", label="PyTorch", category="ml_framework"))
    await db_session.flush()
    db_session.add(Skill(slug="pytorch", label="PyTorch 2", category="ml_framework"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_profile_skill_defaults_and_unique(db_session):
    u, p = await _profile(db_session)
    s = Skill(slug="fastapi", label="FastAPI", category="backend")
    db_session.add(s)
    await db_session.flush()
    ps = ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id)
    db_session.add(ps)
    await db_session.flush()
    got = (
        await db_session.execute(
            select(ProfileSkill).where(ProfileSkill.id == ps.id)
        )
    ).scalar_one()
    assert got.source == "resume_extraction"
    assert got.evidence_refs == []
    assert got.proficiency is None
    db_session.add(ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_profile_skill_source_check(db_session):
    u, p = await _profile(db_session, "sk2@example.com")
    s = Skill(slug="numpy", label="NumPy", category="data")
    db_session.add(s)
    await db_session.flush()
    ps = ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id)
    ps.source = "bogus"
    db_session.add(ps)
    with pytest.raises(IntegrityError):
        await db_session.flush()
