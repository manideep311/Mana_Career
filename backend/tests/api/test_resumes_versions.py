"""/resumes tailor + versions + diff + render — DB integration, CI-deferred."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.models.job import Job
from app.models.resume import Resume
from app.models.resume_version import ResumeVersion
from app.models.user import User


async def _auth(client, email="resume-versions@x.com"):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _confirmed_resume(db_session, email) -> Resume:
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    r = Resume(
        user_id=user.id, file_ref="r.pdf", content_type="application/pdf", size_bytes=100,
        status="extracted", is_primary=True, confirmed_at=dt.datetime.now(dt.UTC),
        extraction={"full_name": "A. Dev", "summary": "s", "skills": ["python"]},
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _seed_job(db_session) -> Job:
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()
    return j


async def test_tailor_returns_202_run_ref(client, db_session):
    h = await _auth(client, "tailor-ok@x.com")
    resume = await _confirmed_resume(db_session, "tailor-ok@x.com")
    job = await _seed_job(db_session)
    r = await client.post(
        f"/api/v1/resumes/{resume.id}/tailor", headers=h, json={"job_id": str(job.id)}
    )
    assert r.status_code == 202
    assert r.json()["run_id"]


async def test_tailor_rejects_an_unconfirmed_resume(client, db_session):
    h = await _auth(client, "tailor-unconfirmed@x.com")
    user = (
        await db_session.execute(select(User).where(User.email == "tailor-unconfirmed@x.com"))
    ).scalar_one()
    resume = Resume(
        user_id=user.id, file_ref="r.pdf", content_type="application/pdf", size_bytes=100,
    )
    db_session.add(resume)
    await db_session.flush()
    job = await _seed_job(db_session)
    r = await client.post(
        f"/api/v1/resumes/{resume.id}/tailor", headers=h, json={"job_id": str(job.id)}
    )
    assert r.status_code == 422


async def test_versions_list_and_detail(client, db_session):
    h = await _auth(client, "versions-list@x.com")
    resume = await _confirmed_resume(db_session, "versions-list@x.com")
    user = (
        await db_session.execute(select(User).where(User.email == "versions-list@x.com"))
    ).scalar_one()
    v = ResumeVersion(
        user_id=user.id, resume_id=resume.id, kind="ai_tailored",
        content={"full_name": "A. Dev", "summary": "different", "skills": ["python"]},
        generation_meta={"claim_validation": {"checked": 1, "passed": True}},
    )
    db_session.add(v)
    await db_session.flush()

    r1 = await client.get(f"/api/v1/resumes/{resume.id}/versions", headers=h)
    assert r1.status_code == 200
    assert len(r1.json()["items"]) == 1
    assert r1.json()["items"][0]["claim_validation"]["passed"] is True

    r2 = await client.get(f"/api/v1/resumes/versions/{v.id}", headers=h)
    assert r2.status_code == 200
    assert r2.json()["content"]["summary"] == "different"


async def test_diff_against_base_snapshot(client, db_session):
    h = await _auth(client, "versions-diff@x.com")
    resume = await _confirmed_resume(db_session, "versions-diff@x.com")
    user = (
        await db_session.execute(select(User).where(User.email == "versions-diff@x.com"))
    ).scalar_one()
    v = ResumeVersion(
        user_id=user.id, resume_id=resume.id, kind="ai_tailored",
        content={"full_name": "A. Dev", "summary": "different", "skills": ["python"]},
        generation_meta={},
    )
    db_session.add(v)
    await db_session.flush()

    r = await client.get(f"/api/v1/resumes/versions/{v.id}/diff", headers=h)
    assert r.status_code == 200
    assert any(d["path"] == "summary" for d in r.json()["deltas"])


async def test_render_markdown(client, db_session):
    h = await _auth(client, "versions-render@x.com")
    resume = await _confirmed_resume(db_session, "versions-render@x.com")
    user = (
        await db_session.execute(select(User).where(User.email == "versions-render@x.com"))
    ).scalar_one()
    v = ResumeVersion(
        user_id=user.id, resume_id=resume.id, kind="base_snapshot",
        content={"full_name": "Jamie Rivera", "summary": "s", "skills": []},
        generation_meta={},
    )
    db_session.add(v)
    await db_session.flush()

    r = await client.get(f"/api/v1/resumes/versions/{v.id}/render?fmt=md", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "Jamie Rivera" in r.text
