"""learning-resource seed -- DB integration, CI-deferred."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models.learning import LearningResource
from app.seed import seed_learning_resources


async def test_seed_learning_resources_is_idempotent(db_session):
    n1 = await seed_learning_resources(db_session)
    assert n1 >= 40
    count1 = (
        await db_session.execute(select(func.count()).select_from(LearningResource))
    ).scalar_one()
    n2 = await seed_learning_resources(db_session)
    count2 = (
        await db_session.execute(select(func.count()).select_from(LearningResource))
    ).scalar_one()
    assert count1 == count2 == n1 == n2
    row = (await db_session.execute(select(LearningResource).limit(1))).scalar_one()
    assert row.embedding is not None and len(row.embedding) == 1024
