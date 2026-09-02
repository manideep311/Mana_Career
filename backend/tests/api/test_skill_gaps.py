from __future__ import annotations

import decimal

from sqlalchemy import select

from app.domain.matching.weights import SCORER_VERSION
from app.models.job import Job
from app.models.match import JobMatch, SkillGap
from app.models.profile import CareerProfile
from app.models.skill import Skill
from app.models.user import User


async def _auth(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "G"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed(db_session, email: str) -> tuple[User, JobMatch, SkillGap, SkillGap]:
    """User + CareerProfile + a JobMatch + two job-scoped SkillGap rows
    (one ``critical``, one ``nice_to_have``) — mirrors
    tests/api/test_matches.py::_seed, adapted for skill gaps."""
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    db_session.add(
        CareerProfile(
            user_id=user.id, seniority="senior", years_experience=decimal.Decimal("6")
        )
    )
    job = Job(
        user_id=None,
        is_seed=True,
        source="seed",
        status="ready",
        raw_text="x" * 60,
        title="Senior ML Engineer",
    )
    python = Skill(slug="python", label="Python", category="language")
    rust = Skill(slug="rust", label="Rust", category="language")
    db_session.add_all([job, python, rust])
    await db_session.flush()

    match = JobMatch(
        user_id=user.id, job_id=job.id, scorer_version=SCORER_VERSION, status="ready"
    )
    db_session.add(match)
    await db_session.flush()

    critical = SkillGap(
        user_id=user.id,
        scope="job",
        job_match_id=match.id,
        skill_id=rust.id,
        skill_slug="rust",
        skill_label="Rust",
        severity="critical",
    )
    nice = SkillGap(
        user_id=user.id,
        scope="job",
        job_match_id=match.id,
        skill_id=python.id,
        skill_slug="python",
        skill_label="Python",
        severity="nice_to_have",
    )
    db_session.add_all([critical, nice])
    await db_session.commit()
    return user, match, critical, nice


async def test_list_skill_gaps_returns_both_critical_first(client, db_session):
    email = "skill-gaps-list@x.com"
    h = await _auth(client, email)
    _user, match, critical, _nice = await _seed(db_session, email)

    r = await client.get(
        f"/api/v1/skill-gaps?scope=job&job_match_id={match.id}", headers=h
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and len(body) == 2
    assert body[0]["id"] == str(critical.id)
    assert body[0]["severity"] == "critical"
    assert body[1]["severity"] == "nice_to_have"
    assert body[0]["scope"] == "job"
    assert body[0]["job_match_id"] == str(match.id)
    assert body[0]["skill_slug"] == "rust"
    assert body[0]["frequency"] == 1
    assert body[0]["status"] == "open"


async def test_patch_skill_gap_updates_status(client, db_session):
    email = "skill-gaps-patch@x.com"
    h = await _auth(client, email)
    _user, _match, critical, _nice = await _seed(db_session, email)

    r = await client.patch(
        f"/api/v1/skill-gaps/{critical.id}", headers=h, json={"status": "learning"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(critical.id)
    assert body["status"] == "learning"


async def test_patch_other_users_skill_gap_is_404(client, db_session):
    owner_email = "skill-gaps-owner@x.com"
    await _auth(client, owner_email)
    _owner, _match, critical, _nice = await _seed(db_session, owner_email)

    intruder_h = await _auth(client, "skill-gaps-intruder@x.com")
    r = await client.patch(
        f"/api/v1/skill-gaps/{critical.id}",
        headers=intruder_h,
        json={"status": "closed"},
    )
    assert r.status_code == 404
