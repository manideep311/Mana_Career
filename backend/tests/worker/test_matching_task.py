import contextlib
import decimal

from sqlalchemy import select

from app.domain.matching.scorer import inputs_hash
from app.domain.matching.service import MatchService
from app.models.job import Job, JobChunk
from app.models.match import MatchComponent
from app.models.profile import CareerProfile, ProfileExperience
from app.models.skill import ProfileSkill, Skill
from app.models.user import User
from app.worker.tasks.matching import score_match


@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


async def _seed(db_session, email="mt@x.com"):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    p = CareerProfile(
        user_id=u.id, seniority="senior", years_experience=decimal.Decimal("6")
    )
    s = Skill(slug="python", label="Python", category="language")
    db_session.add_all([p, s])
    await db_session.flush()
    db_session.add(
        ProfileSkill(user_id=u.id, profile_id=p.id, skill_id=s.id, source="user")
    )
    db_session.add(
        ProfileExperience(
            user_id=u.id, profile_id=p.id, company="A", title="ML Engineer",
            source="user", order_index=0, tech=["Python"],
        )
    )
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Senior ML Engineer", company="Acme",
        required_skills=[
            {"skill_id": str(s.id), "slug": "python", "label": "Python", "weight": 0.9}
        ],
        preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    db_session.add(
        JobChunk(
            job_id=j.id, chunk_index=0, section="description", content="c",
            token_count=1, embed_model="fake-embed-1", embed_dim=1024,
            embedding=[0.1] * 1024,
        )
    )
    await db_session.flush()
    return u, p, s, j


async def test_score_match_marks_ready_and_writes_components(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.worker.tasks.matching._session_for", lambda: _ctx(db_session)
    )
    u, _p, _s, j = await _seed(db_session)
    m = await MatchService(db_session).get_or_create(u.id, j.id)

    out = await score_match({}, str(m.id))
    assert out["status"] == "ready"

    await db_session.refresh(m)
    assert m.status == "ready"
    assert m.score is not None
    assert m.band is not None
    assert len(m.dimension_scores) == 10
    # rag in the loop must not break the semantic dimension
    assert 0.0 <= m.dimension_scores["semantic"] <= 1.0

    comps = (
        await db_session.execute(
            select(MatchComponent).where(MatchComponent.job_match_id == m.id)
        )
    ).scalars().all()
    assert len(comps) == 10


async def test_score_match_skips_when_inputs_hash_matches(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.worker.tasks.matching._session_for", lambda: _ctx(db_session)
    )
    u, _p, _s, j = await _seed(db_session, "mt2@x.com")
    svc = MatchService(db_session)
    m = await svc.get_or_create(u.id, j.id)
    ps = await svc.build_profile_snapshot(u.id)
    js = await svc.build_job_snapshot(j.id)
    m.inputs_hash = inputs_hash(ps, js)
    m.status = "ready"
    await db_session.flush()

    out = await score_match({}, str(m.id))
    assert out["status"] == "skipped"
