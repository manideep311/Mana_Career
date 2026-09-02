from sqlalchemy import func, select

from app.models.job import Job, JobChunk
from app.seed import load_jobs_demo, seed_jobs


async def test_demo_file_is_well_formed():
    rows = await load_jobs_demo()
    assert 30 <= len(rows) <= 60
    keys = [r["key"] for r in rows]
    assert len(keys) == len(set(keys))
    for r in rows:
        assert r["title"] and r["company"] and r["description"]
        assert r["work_mode"] in {"remote", "hybrid", "onsite"}
        assert r["seniority"] in {
            "intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager"
        }
        assert isinstance(r["responsibilities"], list) and r["responsibilities"]
        assert isinstance(r["required_skill_slugs"], list) and r["required_skill_slugs"]


async def test_demo_skill_slugs_all_exist_in_taxonomy():
    from app.seed import load_taxonomy

    taxo = {e["slug"] for e in await load_taxonomy()}
    for r in await load_jobs_demo():
        for slug in [*r["required_skill_slugs"], *r.get("preferred_skill_slugs", [])]:
            assert slug in taxo, f"{r['key']}: unknown skill slug {slug!r}"


async def test_seed_jobs_populates_ready_rows_with_embedded_chunks(db_session):
    # taxonomy must be present so skill slugs resolve
    from app.seed import seed_skills
    await seed_skills(db_session)

    n = await seed_jobs(db_session)
    assert n >= 30

    ready = (await db_session.execute(
        select(func.count()).select_from(Job).where(Job.is_seed.is_(True), Job.status == "ready")
    )).scalar_one()
    assert ready >= 30

    missing = (await db_session.execute(
        select(func.count()).select_from(JobChunk).where(JobChunk.embedding.is_(None))
    )).scalar_one()
    assert missing == 0

    # idempotent
    n2 = await seed_jobs(db_session)
    total = (await db_session.execute(
        select(func.count()).select_from(Job).where(Job.is_seed.is_(True))
    )).scalar_one()
    assert n2 == n and total == n
