import uuid

import pytest

from app.core.errors import NotFoundError, ValidationAppError
from app.domain.auth.service import AuthService
from app.domain.profile.service import ProfileService
from app.models.profile import ProfileExperience
from app.models.skill import ProfileSkill, Skill


async def _user_id(db_session, email="svc@example.com") -> uuid.UUID:
    reg = await AuthService(db_session).register(email, "correct-passphrase", "S",
                                                 ip=None, user_agent=None)
    return reg.user.id


async def test_get_or_create_is_idempotent(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session)
    a = await svc.get_or_create(uid)
    b = await svc.get_or_create(uid)
    assert a.id == b.id


async def test_update_scalars_recomputes_strength(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "sc@example.com")
    p = await svc.update_scalars(uid, {"location": "Hyderabad",
                                       "career_goals": "Ship models."})
    assert p.location == "Hyderabad"
    assert p.profile_strength == 18  # location 8 + goals 10
    assert p.completeness["location"] is True


async def test_update_scalars_ignores_unknown_and_derived_keys(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "wl@example.com")
    p = await svc.update_scalars(uid, {"profile_strength": 999, "nope": 1,
                                       "location": "Berlin"})
    assert p.profile_strength == 8
    assert not hasattr(p, "nope")


async def test_add_update_delete_item_updates_counts(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "it@example.com")
    e = await svc.add_item(uid, "experiences", {"company": "Acme", "title": "Eng"})
    assert isinstance(e, ProfileExperience) and e.order_index == 0
    p = await svc.get_or_create(uid)
    assert p.profile_strength == 16  # work experience weight
    await svc.update_item(uid, "experiences", e.id, {"title": "Senior Eng"})
    await svc.delete_item(uid, "experiences", e.id)
    p = await svc.get_or_create(uid)
    assert p.profile_strength == 0


async def test_item_ops_are_user_scoped(db_session):
    svc = ProfileService(db_session)
    mine = await _user_id(db_session, "mine@example.com")
    other = await _user_id(db_session, "other@example.com")
    e = await svc.add_item(other, "projects", {"name": "Theirs"})
    with pytest.raises(NotFoundError):
        await svc.update_item(mine, "projects", e.id, {"name": "Hacked"})
    with pytest.raises(NotFoundError):
        await svc.delete_item(mine, "projects", e.id)


async def test_reorder_reassigns_order_index(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "ord@example.com")
    a = await svc.add_item(uid, "education", {"institution": "A"})
    b = await svc.add_item(uid, "education", {"institution": "B"})
    out = await svc.reorder(uid, "education", [b.id, a.id])
    assert [r.institution for r in out] == ["B", "A"]
    assert [r.order_index for r in out] == [0, 1]


async def test_reorder_rejects_mismatched_id_set(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "bad@example.com")
    a = await svc.add_item(uid, "education", {"institution": "A"})
    with pytest.raises(ValidationAppError):
        await svc.reorder(uid, "education", [a.id, uuid.uuid4()])


async def _add_skills(db_session, uid, profile_id, n) -> None:
    skills = []
    for _ in range(n):
        slug = f"mapped-skill-{uuid.uuid4().hex}"
        skills.append(Skill(slug=slug, label=slug, category="language"))
    db_session.add_all(skills)
    await db_session.flush()
    for s in skills:
        db_session.add(
            ProfileSkill(user_id=uid, profile_id=profile_id, skill_id=s.id)
        )
    await db_session.flush()


async def test_recompute_scores_skills_mapped_dimension(db_session):
    svc = ProfileService(db_session)
    uid = await _user_id(db_session, "mapped@example.com")
    profile = await svc.get_or_create(uid)

    await _add_skills(db_session, uid, profile.id, 4)
    await svc._recompute(profile)
    assert profile.completeness["skills_mapped"] is False
    strength_with_four = profile.profile_strength

    await _add_skills(db_session, uid, profile.id, 1)
    await svc._recompute(profile)
    assert profile.completeness["skills_mapped"] is True
    assert profile.profile_strength == strength_with_four + 8
