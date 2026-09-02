from sqlalchemy import select

from app.core.config import get_settings
from app.domain.auth.service import AuthService
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.profile.builder import ProfileBuilder
from app.domain.profile.service import ProfileService
from app.models.profile import ProfileExperience, ProfileProject
from app.models.skill import ProfileSkill, Skill


async def _seed_taxonomy(db_session):
    for slug, label, cat, aliases in [
        ("pytorch", "PyTorch", "ml_framework", ["torch"]),
        ("fastapi", "FastAPI", "backend", []),
        ("python", "Python", "language", ["py"]),
    ]:
        db_session.add(Skill(slug=slug, label=label, category=cat, aliases=aliases))
    await db_session.flush()


async def _user(db_session, email):
    reg = await AuthService(db_session).register(email, "correct-passphrase", "B",
                                                 ip=None, user_agent=None)
    return reg.user.id


async def test_rebuild_maps_tech_with_evidence(db_session):
    await _seed_taxonomy(db_session)
    uid = await _user(db_session, "b1@example.com")
    profile = await ProfileService(db_session).get_or_create(uid)
    e = ProfileExperience(user_id=uid, profile_id=profile.id, company="Acme", title="ML Eng",
                          source="resume_extraction", order_index=0, tech=["PyTorch", "Python"])
    p = ProfileProject(user_id=uid, profile_id=profile.id, name="Thing",
                       source="resume_extraction", order_index=0, tech=["torch", "xyzzy"])
    db_session.add_all([e, p])
    await db_session.flush()

    res = await ProfileBuilder(
        db_session, embeddings=get_embeddings_provider(get_settings())
    ).rebuild(uid)
    # "PyTorch" + "torch" -> pytorch, "Python" -> python; "xyzzy" resolves to nothing.
    assert res.matched == 2
    assert res.evidence_total == 3
    rows = (await db_session.execute(
        select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
    )).scalars().all()
    by_slug = {}
    for ps in rows:
        s = (await db_session.execute(select(Skill).where(Skill.id == ps.skill_id))).scalar_one()
        by_slug[s.slug] = ps
    assert set(by_slug) == {"pytorch", "python"}
    kinds = {ev["kind"] for ev in by_slug["pytorch"].evidence_refs}
    assert kinds == {"experience", "project"}
    assert all(ps.source == "resume_extraction" for ps in rows)
    assert "xyzzy" in res.unmatched


async def test_rebuild_is_idempotent_and_keeps_user_skills(db_session):
    await _seed_taxonomy(db_session)
    uid = await _user(db_session, "b2@example.com")
    profile = await ProfileService(db_session).get_or_create(uid)
    db_session.add(ProfileExperience(user_id=uid, profile_id=profile.id, company="A", title="T",
                                     source="resume_extraction", order_index=0, tech=["FastAPI"]))
    fa = (await db_session.execute(select(Skill).where(Skill.slug == "fastapi"))).scalar_one()
    db_session.add(ProfileSkill(user_id=uid, profile_id=profile.id, skill_id=fa.id, source="user"))
    await db_session.flush()

    await ProfileBuilder(db_session).rebuild(uid)
    await ProfileBuilder(db_session).rebuild(uid)
    rows = (await db_session.execute(
        select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
    )).scalars().all()
    # one user fastapi + one resume_extraction fastapi is a UNIQUE violation on
    # (profile_id, skill_id) — so the builder must SKIP a skill that already has a
    # source="user" row. Assert: exactly one fastapi row, still source="user".
    assert len(rows) == 1 and rows[0].source == "user"
