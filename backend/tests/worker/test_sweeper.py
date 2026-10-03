"""DB-gated: the stuck-job sweeper moves stale in-progress work to failure."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import uuid

from sqlalchemy import select

from app.domain.auth.service import AuthService
from app.models.ai import AiSession
from app.models.application import ApplicationEmail
from app.models.job import Job
from app.models.learning import LearningRecommendation
from app.models.match import JobMatch
from app.models.resume import Resume
from app.worker.tasks.sweeper import STALE_AFTER, sweep_stuck_jobs


class _RecordingRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, object]]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, json.loads(message)))
        return 1

    async def aclose(self) -> None:
        return None


@contextlib.asynccontextmanager
async def _ctx(session):
    yield session


async def _seed(db_session):
    reg = await AuthService(db_session).register(
        "sweeper@example.com", "correct-passphrase", "S", ip=None, user_agent=None
    )
    uid = reg.user.id
    stuck_resume = Resume(
        user_id=uid, file_ref="k1", content_type="application/pdf", size_bytes=1,
        status="parsing",
    )
    done_resume = Resume(
        user_id=uid, file_ref="k2", content_type="application/pdf", size_bytes=1,
        status="extracted",
    )
    job = Job(user_id=uid, raw_text="A job", source="user_paste", status="ingesting")
    db_session.add_all([stuck_resume, done_resume, job])
    await db_session.flush()
    match = JobMatch(user_id=uid, job_id=job.id, scorer_version="t", status="scoring")
    run_id = str(uuid.uuid4())
    running = AiSession(user_id=uid, kind="agent_run", status="running", run_id=run_id)
    waiting = AiSession(
        user_id=uid, kind="agent_run", status="awaiting_approval", run_id=str(uuid.uuid4())
    )
    roadmap = LearningRecommendation(
        user_id=uid, scope="aggregate", title="Plan", status="planning"
    )
    sending = ApplicationEmail(
        user_id=uid, job_id=job.id, subject="Application", body="Hello", status="sending"
    )
    sent = ApplicationEmail(
        user_id=uid, job_id=job.id, subject="Application", body="Hello", status="sent"
    )
    db_session.add_all([match, running, waiting, roadmap, sending, sent])
    await db_session.flush()
    return {
        "stuck_resume": stuck_resume.id, "done_resume": done_resume.id, "job": job.id,
        "match": match.id, "running": running.id, "waiting": waiting.id,
        "roadmap": roadmap.id, "run_id": run_id, "sending": sending.id, "sent": sent.id,
    }


async def test_fresh_work_is_left_alone(db_session, monkeypatch):
    ids = await _seed(db_session)
    monkeypatch.setattr("app.worker.tasks.sweeper._session_for", lambda: _ctx(db_session))
    redis = _RecordingRedis()
    monkeypatch.setattr("app.worker.tasks.sweeper.redis_from_settings", lambda s: redis)

    counts = await sweep_stuck_jobs({})
    assert sum(counts.values()) == 0
    assert (await db_session.get(Resume, ids["stuck_resume"])).status == "parsing"
    assert redis.published == []


async def test_stale_in_progress_work_reaches_an_explicit_failure(db_session, monkeypatch):
    ids = await _seed(db_session)
    monkeypatch.setattr("app.worker.tasks.sweeper._session_for", lambda: _ctx(db_session))
    redis = _RecordingRedis()
    monkeypatch.setattr("app.worker.tasks.sweeper.redis_from_settings", lambda s: redis)

    later = dt.datetime.now(dt.UTC) + STALE_AFTER + dt.timedelta(minutes=1)
    counts = await sweep_stuck_jobs({}, now=later)

    assert counts == {
        "resumes": 1, "jobs": 1, "matches": 1, "agent_runs": 1, "roadmaps": 1,
        "application_emails": 1,
    }
    db_session.expire_all()

    async def one(model, pk):
        return (await db_session.execute(select(model).where(model.id == pk))).scalar_one()

    stuck = await one(Resume, ids["stuck_resume"])
    assert stuck.status == "failed" and stuck.parse_error
    assert (await one(Resume, ids["done_resume"])).status == "extracted"
    assert (await one(Job, ids["job"])).status == "failed"
    assert (await one(JobMatch, ids["match"])).status == "failed"
    run = await one(AiSession, ids["running"])
    assert run.status == "error" and run.ended_at is not None
    # Waiting on a human is a legitimate long-lived state: never swept.
    assert (await one(AiSession, ids["waiting"])).status == "awaiting_approval"
    assert (await one(LearningRecommendation, ids["roadmap"])).status == "archived"
    # An email stuck mid-send is failed with an inbox-check note, never resent;
    # one that was sent stays sent.
    stuck_email = await one(ApplicationEmail, ids["sending"])
    assert stuck_email.status == "failed" and "Check the inbox" in stuck_email.send_error
    assert (await one(ApplicationEmail, ids["sent"])).status == "sent"

    channels = {channel for channel, _ in redis.published}
    assert f"sse:resume:{ids['stuck_resume']}" in channels
    assert f"sse:ai:{ids['run_id']}" in channels
    assert f"sse:roadmap:{ids['roadmap']}" in channels
    done = [p for c, p in redis.published if c == f"sse:ai:{ids['run_id']}"]
    assert {"event": "done", "status": "error", "totals": {}} in done
