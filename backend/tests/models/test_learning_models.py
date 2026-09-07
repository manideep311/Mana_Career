"""learning_* model round-trips -- DB integration, CI-deferred."""
from __future__ import annotations

from app.models.learning import (
    LearningRecommendation,
    LearningResource,
    RoadmapMilestone,
)
from app.models.user import User


async def test_learning_models_round_trip(db_session):
    u = User(email="learn@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()

    res = LearningResource(
        title="SQL Performance Explained", provider="Markus Winand", url="https://use-the-index-luke.com",
        type="book", skills=["sql", "databases"], level="intermediate", cost="free",
        summary="Indexing and query tuning from first principles.",
    )
    db_session.add(res)
    await db_session.flush()
    await db_session.refresh(res)
    assert res.is_active is True and res.skills == ["sql", "databases"]

    rec = LearningRecommendation(user_id=u.id, scope="aggregate", title="Learning roadmap")
    db_session.add(rec)
    await db_session.flush()
    await db_session.refresh(rec)
    assert rec.status == "planning" and rec.constraints == {}

    ms = RoadmapMilestone(
        recommendation_id=rec.id, user_id=u.id, order_index=0,
        skill_slug="sql", skill_label="SQL", title="Master indexing",
        why_it_matters="Every backend role expects it.", resource_ids=[res.id],
    )
    db_session.add(ms)
    await db_session.flush()
    await db_session.refresh(ms)
    assert ms.status == "not_started" and ms.resource_ids == [res.id]
