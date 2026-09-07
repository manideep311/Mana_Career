"""plan_roadmap worker task -- DB integration, CI-deferred.

Drives the ARQ ``plan_roadmap`` task end to end against a real (migrated) DB:
seeds a ``status='planning'`` recommendation plus one open aggregate skill gap,
runs the task with a fake Redis that records every published frame and a
session seam pinned to the rolled-back test session, then asserts the
recommendation reached ``status='active'`` and a terminal ``done`` frame landed
on ``sse:roadmap:{rec_id}``. With ``LLM_PROVIDER=fake`` every milestone draft is
empty and dropped, so the roadmap lands with 0 milestones but still activates.
"""
from __future__ import annotations

import contextlib
import json
from typing import Any

from sqlalchemy import select

from app.models.learning import LearningRecommendation, LearningResource
from app.models.match import SkillGap
from app.models.skill import Skill
from app.models.user import User
from app.worker.tasks.roadmap import plan_roadmap


@contextlib.asynccontextmanager
async def _session_cm(session: Any) -> Any:
    """Yield the passed session unchanged (seam for ``AsyncSessionLocal``)."""
    yield session


class _RecordingRedis:
    def __init__(self) -> None:
        self.frames: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.frames.append((channel, json.loads(message)))
        return 1

    async def aclose(self) -> None:
        return None


def _fake_redis_cls(rec: _RecordingRedis) -> type:
    return type("R", (), {"from_url": staticmethod(lambda *a, **k: rec)})


async def _seed(db_session: Any) -> tuple[User, LearningRecommendation]:
    user = User(email="plan-roadmap-task@x.com", password_hash="x", full_name="U")
    db_session.add(user)
    await db_session.flush()

    skill = Skill(slug="kubernetes", label="Kubernetes", category="tool", aliases=[])
    db_session.add(skill)
    await db_session.flush()

    db_session.add(
        LearningResource(
            title="Kubernetes the Hard Way",
            provider="Google",
            url="https://example.com/plan-roadmap-task-k8s",
            type="course",
            skills=["kubernetes"],
            level="intermediate",
            cost="free",
            summary="Bootstrap a cluster by hand to learn every moving part.",
            embedding=[0.1] * 1024,
        )
    )
    db_session.add(
        SkillGap(
            user_id=user.id, scope="aggregate", skill_id=skill.id,
            skill_slug="kubernetes", skill_label="Kubernetes",
            severity="critical", frequency=2, status="open",
        )
    )
    rec = LearningRecommendation(
        user_id=user.id, scope="aggregate", title="Close your top skill gaps",
        constraints={}, status="planning", generation_meta={},
    )
    db_session.add(rec)
    await db_session.flush()
    return user, rec


async def test_plan_roadmap_activates_and_publishes_done(db_session, monkeypatch):
    _user, rec = await _seed(db_session)
    assert rec.status == "planning"

    redis = _RecordingRedis()
    monkeypatch.setattr(
        "app.worker.tasks.roadmap.AsyncSessionLocal", lambda: _session_cm(db_session)
    )
    monkeypatch.setattr("app.worker.tasks.roadmap.Redis", _fake_redis_cls(redis))

    out = await plan_roadmap({"job_id": "t"}, str(rec.id))
    assert out is None

    refreshed = (
        await db_session.execute(
            select(LearningRecommendation).where(LearningRecommendation.id == rec.id)
        )
    ).scalar_one()
    assert refreshed.status == "active"

    channels = {ch for ch, _f in redis.frames}
    assert f"sse:roadmap:{rec.id}" in channels

    done = [f for _ch, f in redis.frames if f.get("event") == "done"]
    assert done, "plan_roadmap published no done frame"
    assert done[-1]["status"] == "active"
    assert done[-1]["id"] == str(rec.id)

    # The fake LLM yields empty drafts, so every milestone is dropped.
    assert [f for _ch, f in redis.frames if f.get("event") == "milestone"] == []
