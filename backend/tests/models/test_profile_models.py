import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.profile import (
    CareerProfile,
    ProfileCertification,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
)
from app.models.user import User


async def _user(db_session, email="p@example.com") -> User:
    u = User(email=email, password_hash="x", full_name="P")
    db_session.add(u)
    await db_session.flush()
    return u


async def _profile(db_session, user: User) -> CareerProfile:
    p = CareerProfile(user_id=user.id)
    db_session.add(p)
    await db_session.flush()
    return p


async def test_profile_defaults(db_session):
    u = await _user(db_session)
    p = await _profile(db_session, u)
    got = (await db_session.execute(
        select(CareerProfile).where(CareerProfile.id == p.id)
    )).scalar_one()
    assert got.profile_strength == 0
    assert got.completeness == {}
    assert got.preferred_roles == []


async def test_one_profile_per_user(db_session):
    u = await _user(db_session, "one@example.com")
    await _profile(db_session, u)
    with pytest.raises(IntegrityError):
        await _profile(db_session, u)


async def test_salary_period_check(db_session):
    u = await _user(db_session, "sal@example.com")
    p = await _profile(db_session, u)
    p.salary_period = "weekly"  # fits varchar(8) but not in the CHECK set
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (ProfileExperience, {"company": "Acme", "title": "Eng"}),
        (ProfileEducation, {"institution": "Uni"}),
        (ProfileProject, {"name": "RAG thing"}),
        (ProfileCertification, {"name": "AWS SAA"}),
    ],
)
async def test_subentity_round_trip_and_cascade(db_session, model, kwargs):
    u = await _user(db_session, f"{model.__name__.lower()}@example.com")
    p = await _profile(db_session, u)
    row = model(user_id=u.id, profile_id=p.id, **kwargs)
    db_session.add(row)
    await db_session.flush()
    assert row.source == "user"
    assert row.order_index == 0
    await db_session.delete(p)
    await db_session.flush()
    gone = (await db_session.execute(select(model).where(model.id == row.id))).first()
    assert gone is None


async def test_experience_is_current_default_false(db_session):
    u = await _user(db_session, "cur@example.com")
    p = await _profile(db_session, u)
    e = ProfileExperience(user_id=u.id, profile_id=p.id, company="A", title="B",
                          start_date=dt.date(2020, 1, 1))
    db_session.add(e)
    await db_session.flush()
    assert e.is_current is False
    assert e.highlights == [] and e.tech == []
