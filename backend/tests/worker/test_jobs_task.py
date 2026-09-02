import contextlib

from sqlalchemy import func, select

from app.domain.jobs.extractor import JDSkill, JobExtraction
from app.domain.llm.provider import LLMResult
from app.models.job import Job, JobChunk
from app.models.skill import Skill


@contextlib.asynccontextmanager
async def _ctx(session):
    """Yield the passed session unchanged (test seam for ``_session_for``)."""
    yield session


def _extraction(**overrides) -> JobExtraction:
    base = dict(
        title="Senior ML Engineer",
        company="Acme",
        description="Own the model serving stack and ship low-latency inference infra.",
        responsibilities=["Design serving infra", "Mentor engineers"],
        required_skills=[JDSkill(raw="Python", weight=0.9)],
        preferred_skills=[JDSkill(raw="Kubernetes", weight=0.4)],
    )
    base.update(overrides)
    return JobExtraction(**base)


def _extractor_returning(extraction: JobExtraction):
    """A stand-in for ``JobExtractor`` that skips the LLM and returns a canned model."""

    class _FE:
        def __init__(self, llm, *, model):  # matches JobExtractor(llm, *, model)
            self.last_usage = LLMResult(
                text="",
                model="fake-extract-1",
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
            )

        async def extract(self, text: str) -> JobExtraction:
            return extraction

    return _FE


def _wire(monkeypatch, jobs_task, db_session, fake_redis, extraction):
    monkeypatch.setattr(jobs_task, "_session_for", lambda: _ctx(db_session))
    monkeypatch.setattr(jobs_task, "redis_from_settings", lambda s: fake_redis)
    monkeypatch.setattr(jobs_task, "JobExtractor", _extractor_returning(extraction))


async def test_ingest_job_marks_ready_and_writes_embedded_chunks(
    db_session, monkeypatch, fake_redis
):
    from app.worker.tasks import jobs as jobs_task

    db_session.add(Skill(slug="python", label="Python", category="backend", aliases=[]))
    _wire(monkeypatch, jobs_task, db_session, fake_redis, _extraction())

    job = Job(
        user_id=None,
        is_seed=False,
        source="user_paste",
        status="ingesting",
        raw_text=(
            "Senior ML Engineer at Acme. Remote. Own the model serving stack. "
            "Requires Python and PyTorch. Nice to have Kubernetes."
        ),
    )
    db_session.add(job)
    await db_session.flush()

    out = await jobs_task.ingest_job({}, str(job.id))
    assert out["status"] == "ready"

    await db_session.refresh(job)
    assert job.status == "ready"
    assert job.ingest_error is None
    assert job.extraction_meta.get("embed_model") == "fake-embed-1"
    assert [s["slug"] for s in job.required_skills] == ["python"]

    n = (
        await db_session.execute(
            select(func.count()).select_from(JobChunk).where(JobChunk.job_id == job.id)
        )
    ).scalar_one()
    assert n >= 1
    missing = (
        await db_session.execute(
            select(func.count())
            .select_from(JobChunk)
            .where(JobChunk.job_id == job.id, JobChunk.embedding.is_(None))
        )
    ).scalar_one()
    assert missing == 0


async def test_ingest_job_skips_when_not_ingesting(db_session, monkeypatch, fake_redis):
    from app.worker.tasks import jobs as jobs_task

    _wire(monkeypatch, jobs_task, db_session, fake_redis, _extraction())
    job = Job(
        user_id=None, source="seed", is_seed=True, status="ready", raw_text="x" * 60
    )
    db_session.add(job)
    await db_session.flush()

    out = await jobs_task.ingest_job({}, str(job.id))
    assert out["status"] == "skipped"


async def test_ingest_job_coerces_drifting_enum_values(db_session, monkeypatch, fake_redis):
    from app.worker.tasks import jobs as jobs_task

    _wire(
        monkeypatch,
        jobs_task,
        db_session,
        fake_redis,
        _extraction(
            work_mode="Remote",
            seniority="Sr.",
            salary_period="annually",
            salary_currency="usd",
        ),
    )
    job = Job(
        user_id=None, is_seed=False, source="user_paste", status="ingesting",
        raw_text="Staff role at Acme. " + "detail " * 20,
    )
    db_session.add(job)
    await db_session.flush()

    out = await jobs_task.ingest_job({}, str(job.id))
    assert out["status"] == "ready"

    await db_session.refresh(job)
    assert job.status == "ready"
    assert job.work_mode == "remote"
    assert job.seniority == "senior"
    assert job.salary_period == "year"
    assert job.salary_currency == "USD"
    # structured JSON is coerced in lock-step with the typed columns
    assert job.structured["work_mode"] == "remote"
    assert job.structured["seniority"] == "senior"


async def test_ingest_job_drops_out_of_vocab_enum_values(
    db_session, monkeypatch, fake_redis
):
    from app.worker.tasks import jobs as jobs_task

    _wire(
        monkeypatch,
        jobs_task,
        db_session,
        fake_redis,
        _extraction(
            work_mode="somewhere",
            seniority="wizard",
            salary_period="fortnightly",
            salary_currency="dollars",
        ),
    )
    job = Job(
        user_id=None, is_seed=False, source="user_paste", status="ingesting",
        raw_text="Some role at Acme. " + "detail " * 20,
    )
    db_session.add(job)
    await db_session.flush()

    out = await jobs_task.ingest_job({}, str(job.id))
    assert out["status"] == "ready"

    await db_session.refresh(job)
    assert job.status == "ready"
    assert job.work_mode is None
    assert job.seniority is None
    assert job.salary_period is None
    assert job.salary_currency is None
