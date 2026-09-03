import uuid

import pytest

from app.domain.rag.types import RetrievalSource
from app.domain.rag.vector_store import VectorStore
from app.models.job import Job, JobChunk
from app.models.user import User


async def _seed(db_session):
    u = User(email="vs@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    job = Job(user_id=None, is_seed=True, source="seed", status="ready",
              raw_text="x" * 60, title="Senior Python Backend Engineer")
    db_session.add(job)
    await db_session.flush()
    db_session.add_all([
        JobChunk(job_id=job.id, owner_id=None, chunk_index=0, section="description",
                 content="We need a senior Python engineer with Kafka and Postgres.",
                 token_count=10, embed_model="fake-embed-1", embed_dim=1024,
                 embedding=[0.1] * 1024),
        # A genuinely different direction, not a scalar multiple of chunk 0, so the
        # cosine-distance ordering is unambiguous (both-are-all-ones would tie at 0).
        JobChunk(job_id=job.id, owner_id=None, chunk_index=1, section="responsibilities",
                 content="Own the streaming ingestion pipeline and its SLAs.",
                 token_count=9, embed_model="fake-embed-1", embed_dim=1024,
                 embedding=[0.1] * 512 + [0.9] * 512),
    ])
    await db_session.flush()
    return u, job


async def test_vector_search_returns_ranked_chunks(db_session):
    u, job = await _seed(db_session)
    rows = await VectorStore(db_session).vector_search(
        source=RetrievalSource.JOB_CHUNKS, query_embedding=[0.1] * 1024, user_id=u.id,
    )
    assert len(rows) == 2
    assert rows[0].vector_rank == 1 and rows[1].vector_rank == 2
    assert rows[0].ref_id == f"{job.id}:0"  # exact match to the query -> nearest
    assert rows[1].ref_id == f"{job.id}:1"
    assert rows[0].embedding is not None and len(rows[0].embedding) == 1024


async def test_text_search_matches_on_tsv(db_session):
    u, job = await _seed(db_session)
    rows = await VectorStore(db_session).text_search(
        source=RetrievalSource.JOB_CHUNKS, query_text="kafka postgres", user_id=u.id,
    )
    assert [r.ref_id for r in rows][:1] == [f"{job.id}:0"]
    assert rows[0].text_rank == 1


async def test_text_search_blank_query_returns_empty(db_session):
    u, _job = await _seed(db_session)
    rows = await VectorStore(db_session).text_search(
        source=RetrievalSource.JOB_CHUNKS, query_text="   ", user_id=u.id,
    )
    assert rows == []


async def test_job_id_filter_scopes_to_one_job(db_session):
    u, _job = await _seed(db_session)
    other = uuid.uuid4()
    rows = await VectorStore(db_session).vector_search(
        source=RetrievalSource.JOB_CHUNKS, query_embedding=[0.1] * 1024,
        user_id=u.id, job_id=other,
    )
    assert rows == []


async def test_unknown_source_raises(db_session):
    with pytest.raises(NotImplementedError):
        await VectorStore(db_session).vector_search(
            source="resume_chunks", query_embedding=[0.0] * 1024, user_id=uuid.uuid4(),  # type: ignore[arg-type]
        )
