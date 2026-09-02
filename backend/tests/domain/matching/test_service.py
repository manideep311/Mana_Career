import decimal

from sqlalchemy import select

from app.domain.matching.gaps import GapDraft
from app.domain.matching.scorer import score
from app.domain.matching.service import MatchService
from app.domain.matching.weights import SCORER_VERSION
from app.models.job import Job, JobChunk
from app.models.match import MatchComponent, SkillGap
from app.models.profile import CareerProfile, ProfileExperience
from app.models.skill import ProfileSkill, Skill
from app.models.user import User


async def _seed(db_session, email="ms@x.com"):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    p = CareerProfile(user_id=u.id, seniority="senior", years_experience=decimal.Decimal("6"))
    s = Skill(slug="python", label="Python", category="language")
    db_session.add_all([p, s])
    await db_session.flush()
    db_session.add(ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id, source="user"))
    db_session.add(ProfileExperience(
        user_id=u.id, profile_id=p.id, company="A", title="ML Engineer",
        source="user", order_index=0, tech=["Python"],
    ))
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Senior ML Engineer",
        required_skills=[
            {"skill_id": str(s.id), "slug": "python", "label": "Python", "weight": 0.9}
        ],
        preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    db_session.add(JobChunk(
        job_id=j.id, chunk_index=0, section="description", content="c",
        token_count=1, embed_model="fake-embed-1", embed_dim=1024,
        embedding=[0.1] * 1024,
    ))
    await db_session.flush()
    return u, p, s, j


async def test_build_snapshots(db_session):
    u, _p, s, j = await _seed(db_session)
    svc = MatchService(db_session)
    ps = await svc.build_profile_snapshot(u.id)
    assert str(s.id) in ps.skill_ids and ps.seniority == "senior"
    js = await svc.build_job_snapshot(j.id)
    assert js.required and js.required[0][0] == str(s.id)
    assert len(js.chunk_embeddings) == 1


async def test_get_or_create_inserts_scoring_and_enqueues(db_session, monkeypatch):
    calls: list[str] = []

    async def _spy(task, *a, **k):
        calls.append(task)
        return "x"

    monkeypatch.setattr("app.domain.matching.service.enqueue", _spy)
    u, _p, _s, j = await _seed(db_session, "ms2@x.com")
    m = await MatchService(db_session).get_or_create(u.id, j.id)
    assert m.status == "scoring" and m.scorer_version == SCORER_VERSION
    assert calls == ["score_match"]
    again = await MatchService(db_session).get_or_create(u.id, j.id)
    assert again.id == m.id


async def test_apply_score_writes_components_and_gaps(db_session):
    u, _p, _s, j = await _seed(db_session, "ms3@x.com")
    svc = MatchService(db_session)
    m = await svc.get_or_create(u.id, j.id)
    ps = await svc.build_profile_snapshot(u.id)
    js = await svc.build_job_snapshot(j.id)
    result = score(ps, js)
    # a real gap needs a real skill row for the FK
    rust = Skill(slug="rust", label="Rust", category="language")
    db_session.add(rust)
    await db_session.flush()
    gap = GapDraft(skill_id=str(rust.id), slug="rust", label="Rust", severity="critical")
    await svc.apply_score(m.id, result=result, gaps=[gap], explanation="ok",
                          explanation_meta={"model": "fake"}, rationales={"Rust": "Needed."})
    await db_session.refresh(m)
    assert m.status == "ready" and m.score is not None and m.band is not None
    comps = (await db_session.execute(
        select(MatchComponent).where(MatchComponent.job_match_id == m.id)
    )).scalars().all()
    assert len(comps) == 10
    sg = (await db_session.execute(
        select(SkillGap).where(SkillGap.job_match_id == m.id)
    )).scalars().all()
    assert len(sg) == 1 and sg[0].rationale == "Needed."


async def test_job_scores_for(db_session):
    u, _p, _s, j = await _seed(db_session, "ms4@x.com")
    svc = MatchService(db_session)
    m = await svc.get_or_create(u.id, j.id)
    m.score = decimal.Decimal("92.00")
    m.band = "strong"
    m.status = "ready"
    await db_session.flush()
    scores = await svc.job_scores_for(u.id, [j.id])
    assert scores[j.id] == (92.0, "strong", "ready")
