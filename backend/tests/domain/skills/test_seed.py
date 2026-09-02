from sqlalchemy import func, select

from app.models.skill import Skill
from app.seed import seed_skills


async def test_seed_populates_skills_with_embeddings(db_session):
    n = await seed_skills(db_session)
    assert n >= 150

    count = await db_session.scalar(select(func.count()).select_from(Skill))
    assert count >= 150

    missing = await db_session.scalar(
        select(func.count()).select_from(Skill).where(Skill.embedding.is_(None))
    )
    assert missing == 0


async def test_seed_is_idempotent(db_session):
    await seed_skills(db_session)
    first = await db_session.scalar(select(func.count()).select_from(Skill))

    await seed_skills(db_session)
    second = await db_session.scalar(select(func.count()).select_from(Skill))

    assert first == second
    assert second >= 150
