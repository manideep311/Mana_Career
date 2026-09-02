import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.job import Job, JobChunk
from app.models.user import User


async def _user(db_session, email="job@example.com"):
    u = User(email=email, password_hash="x", full_name="J")
    db_session.add(u)
    await db_session.flush()
    return u


async def test_job_defaults_and_seed_row_has_null_user(db_session):
    job = Job(raw_text="We are hiring an ML Engineer.", is_seed=True, source="seed",
              title="ML Engineer", company="Acme", status="ready")
    db_session.add(job)
    await db_session.flush()
    got = (await db_session.execute(select(Job).where(Job.id == job.id))).scalar_one()
    assert got.user_id is None
    assert got.responsibilities == []
    assert got.required_skills == [] and got.preferred_skills == []
    assert got.structured == {} and got.extraction_meta == {}
    assert got.status == "ready"


async def test_job_status_check_rejects_bad_value(db_session):
    u = await _user(db_session)
    job = Job(user_id=u.id, raw_text="x", status="bogus")
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_search_tsv_is_generated_from_title_company_description(db_session):
    job = Job(raw_text="x", title="Senior Rust Engineer", company="Foobar",
              description="Build low-latency services.", status="ready")
    db_session.add(job)
    await db_session.flush()
    await db_session.refresh(job)
    row = (await db_session.execute(
        select(Job).where(Job.search_tsv.op("@@")(  # websearch match
            func.websearch_to_tsquery("english", "rust")))
    )).scalar_one()
    assert row.id == job.id


async def test_job_chunk_unique_index_and_cascade(db_session):
    job = Job(raw_text="x", status="ready")
    db_session.add(job)
    await db_session.flush()
    db_session.add(JobChunk(job_id=job.id, chunk_index=0, section="description",
                            content="c", token_count=1, embed_model="fake-embed-1", embed_dim=1024))
    await db_session.flush()
    db_session.add(JobChunk(job_id=job.id, chunk_index=0, section="description",
                            content="d", token_count=1, embed_model="fake-embed-1", embed_dim=1024))
    with pytest.raises(IntegrityError):
        await db_session.flush()
