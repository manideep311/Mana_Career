"""GET /catalog/stats -- DB integration, CI-deferred.

Public counts for the landing page: catalogue roles grouped into career paths,
plus skills and active learning resources. A user's own saved jobs are private
and must never be counted.
"""
from __future__ import annotations

from sqlalchemy import select

from app.api.v1.catalog import clear_stats_cache
from app.models.job import Job
from app.models.user import User


async def test_stats_are_public_and_count_only_the_shared_catalogue(client, db_session):
    clear_stats_cache()
    before = (await client.get("/api/v1/catalog/stats")).json()

    user = User(email="catalog-owner@x.com", password_hash="x", full_name="U")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all([
        Job(raw_text="x", title="Senior Backend Engineer", status="ready"),
        Job(raw_text="x", title="Backend Engineer, Payments", status="ready"),
        Job(raw_text="x", title="Draft role", status="ingesting"),
        Job(user_id=user.id, raw_text="x", title="Private Data Analyst", status="ready"),
    ])
    await db_session.flush()

    # Fresh numbers, not the few-minute cached answer from the first call.
    clear_stats_cache()
    r = await client.get("/api/v1/catalog/stats")  # no Authorization header
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=300"
    after = r.json()
    assert set(after) == {"career_paths", "roles", "skills", "learning_resources"}
    assert after["roles"] == before["roles"] + 2  # the private and ingesting rows don't count
    owned = (await db_session.execute(select(Job).where(Job.user_id == user.id))).scalars().all()
    assert len(owned) == 1


async def test_repeat_views_are_answered_from_the_cache(client, db_session):
    clear_stats_cache()
    first = (await client.get("/api/v1/catalog/stats")).json()
    db_session.add(Job(raw_text="x", title="Cached Platform Engineer", status="ready"))
    await db_session.flush()
    # Within the cache window the landing page sees the same numbers, without
    # another round of counting queries.
    assert (await client.get("/api/v1/catalog/stats")).json() == first
