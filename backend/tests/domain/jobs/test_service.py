import uuid

import pytest

from app.core.errors import NotFoundError, ValidationAppError
from app.domain.jobs.service import JobFilters, JobService
from app.models.job import Job
from app.models.user import User


async def _user(db_session, email):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    return u


def _ready_job(**kw):
    base = dict(raw_text="x" * 60, status="ready", is_seed=False)
    base.update(kw)
    return Job(**base)


async def test_create_inserts_ingesting_and_enqueues(db_session, monkeypatch):
    calls: list[tuple] = []

    async def _spy(task, *a, **k):
        calls.append((task, a, k))
        return "job-1"

    monkeypatch.setattr("app.domain.jobs.service.enqueue", _spy)
    u = await _user(db_session, "c1@x.com")
    raw = "Senior ML Engineer\n" + "detail " * 20
    job = await JobService(db_session).create(u.id, raw_text=raw)
    assert job.status == "ingesting" and job.source == "user_paste" and job.user_id == u.id
    assert calls and calls[0][0] == "ingest_job"


async def test_create_rejects_near_empty(db_session):
    u = await _user(db_session, "c2@x.com")
    with pytest.raises(ValidationAppError):
        await JobService(db_session).create(u.id, raw_text="too short")


async def test_get_returns_own_and_seed_but_not_other_users(db_session):
    u1 = await _user(db_session, "g1@x.com")
    u2 = await _user(db_session, "g2@x.com")
    mine = _ready_job(user_id=u1.id, title="Mine")
    seed = _ready_job(user_id=None, is_seed=True, source="seed", title="Seed")
    theirs = _ready_job(user_id=u2.id, title="Theirs")
    db_session.add_all([mine, seed, theirs])
    await db_session.flush()
    svc = JobService(db_session)
    assert (await svc.get(u1.id, mine.id)).title == "Mine"
    assert (await svc.get(u1.id, seed.id)).title == "Seed"
    with pytest.raises(NotFoundError):
        await svc.get(u1.id, theirs.id)


async def test_list_filters_by_query_workmode_and_skill_slug(db_session):
    u = await _user(db_session, "l1@x.com")
    rust_skill = {"skill_id": str(uuid.uuid4()), "slug": "rust", "label": "Rust", "weight": 0.9}
    react_skill = {"skill_id": str(uuid.uuid4()), "slug": "react", "label": "React", "weight": 0.8}
    db_session.add_all([
        _ready_job(user_id=None, is_seed=True, source="seed", title="Rust Platform Engineer",
                   company="Foo", work_mode="remote", required_skills=[rust_skill]),
        _ready_job(user_id=None, is_seed=True, source="seed", title="Frontend Engineer",
                   company="Bar", work_mode="onsite", required_skills=[react_skill]),
    ])
    await db_session.flush()
    svc = JobService(db_session)
    rows, total = await svc.list_(u.id, JobFilters(q="rust"))
    assert total == 1 and rows[0].title == "Rust Platform Engineer"
    rows, total = await svc.list_(u.id, JobFilters(work_mode="remote"))
    assert {r.title for r in rows} == {"Rust Platform Engineer"}
    rows, total = await svc.list_(u.id, JobFilters(skills=("react",)))
    assert {r.title for r in rows} == {"Frontend Engineer"}


async def test_delete_soft_deletes_user_job_and_404s_seed(db_session):
    u = await _user(db_session, "d1@x.com")
    mine = _ready_job(user_id=u.id, title="Mine")
    seed = _ready_job(user_id=None, is_seed=True, source="seed", title="Seed")
    db_session.add_all([mine, seed])
    await db_session.flush()
    svc = JobService(db_session)
    await svc.delete(u.id, mine.id)
    with pytest.raises(NotFoundError):
        await svc.get(u.id, mine.id)
    with pytest.raises(NotFoundError):
        await svc.delete(u.id, seed.id)
