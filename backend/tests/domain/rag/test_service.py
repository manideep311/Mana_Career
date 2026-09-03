import uuid

from app.domain.embeddings.adapters.fake import FakeEmbeddingsProvider
from app.domain.rag.service import RagService
from app.domain.rag.types import RetrievalSource
from app.models.job import Job, JobChunk
from app.models.user import User


async def _seed(db_session):
    u = User(email="rag@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    job = Job(user_id=None, is_seed=True, source="seed", status="ready",
              raw_text="x" * 60, title="Staff ML Engineer")
    db_session.add(job)
    await db_session.flush()
    emb = FakeEmbeddingsProvider(1024, "fake-embed-1")
    contents = [
        "Design and ship large language model inference systems at scale.",
        "Mentor engineers and set the technical direction for the ML platform.",
        "Own model evaluation, drift detection, and the retraining loop.",
        "Partner with product to translate goals into measurable ML metrics.",
    ]
    vecs = await emb.embed_documents(contents)
    for i, (c, v) in enumerate(zip(contents, vecs, strict=True)):
        db_session.add(JobChunk(
            job_id=job.id, owner_id=None, chunk_index=i, section="description",
            content=c, token_count=len(c.split()), embed_model="fake-embed-1",
            embed_dim=1024, embedding=v,
        ))
    await db_session.flush()
    return u, job


async def test_retrieve_returns_fenced_context_with_citations(db_session):
    u, job = await _seed(db_session)
    svc = RagService(db_session, FakeEmbeddingsProvider(1024, "fake-embed-1"))
    ctx = await svc.retrieve(
        "machine learning platform inference and evaluation",
        source=RetrievalSource.JOB_CHUNKS, user_id=u.id, job_id=job.id, k=3,
    )
    assert 1 <= len(ctx.blocks) <= 3
    assert ctx.text.count("<untrusted_data ") == len(ctx.blocks)
    assert all(c.ref_id.startswith(str(job.id)) for c in ctx.citations)
    assert all(b.rrf_score > 0.0 for b in ctx.blocks)
    assert all(b.mmr_score is not None for b in ctx.blocks)


async def test_retrieve_blank_query_is_empty(db_session):
    u, _job = await _seed(db_session)
    svc = RagService(db_session, FakeEmbeddingsProvider(1024, "fake-embed-1"))
    ctx = await svc.retrieve("  ", source=RetrievalSource.JOB_CHUNKS, user_id=u.id)
    assert ctx.blocks == () and ctx.text == ""


async def test_retrieve_no_matches_is_empty(db_session):
    u, _job = await _seed(db_session)
    svc = RagService(db_session, FakeEmbeddingsProvider(1024, "fake-embed-1"))
    ctx = await svc.retrieve(
        "anything", source=RetrievalSource.JOB_CHUNKS, user_id=u.id, job_id=uuid.uuid4(),
    )
    assert ctx.blocks == ()
