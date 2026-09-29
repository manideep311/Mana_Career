"""/career guidance API and /resumes/{id}/analysis -- DB integration, CI-deferred.

Seeds a résumé with extracted text and a few private job postings, then checks
the deterministic guidance: an evidence-backed direction, paths with reasons
rather than percentages, a short skill plan, résumé analysis framed as problem /
why / suggestion, and that another user can't read any of it.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User

RESUME_TEXT = """Asha Rao
asha@example.com | +91 98765 43210

SUMMARY
Backend engineer who builds reliable APIs.

EXPERIENCE
Backend Engineer, Acme 2021 - 2024
• Built Python and FastAPI services handling 2M requests a day
• Designed PostgreSQL schemas and cut query time by 40%
• Responsible for code reviews

SKILLS
Python, FastAPI, PostgreSQL, Docker
"""


def _skills(*slugs: str) -> list[dict[str, str]]:
    return [{"slug": s, "label": s.title()} for s in slugs]


async def _auth(client, email):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-passphrase"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed(db_session, email: str, *, text: str | None = RESUME_TEXT) -> Resume:
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    resume = Resume(
        user_id=user.id, file_ref=f"test/{uuid.uuid4()}.pdf", content_type="application/pdf",
        size_bytes=1000, page_count=1, status="extracted" if text else "parsing",
        extracted_text=text, is_primary=True,
    )
    db_session.add(resume)
    for i in range(3):
        db_session.add(Job(
            user_id=user.id, raw_text="x", title=f"Backend Engineer {i}", company="Co",
            seniority="mid", status="ready",
            required_skills=_skills("python", "postgresql", "kubernetes"),
            preferred_skills=_skills("docker"),
        ))
    await db_session.flush()
    return resume


async def test_overview_for_a_new_user_says_what_to_do_first(client, db_session):
    h = await _auth(client, "career-empty@x.com")
    r = await client.get("/api/v1/career/overview", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["has_resume"] is False
    assert body["next_actions"][0]["kind"] == "upload_resume"
    assert body["next_actions"][0]["href"] == "/resume"
    assert [s["key"] for s in body["journey"]] == [
        "profile", "skills", "proof", "applications", "target",
    ]
    assert body["journey"][0]["status"] == "current"


async def test_overview_grounds_the_direction_in_resume_evidence(client, db_session):
    email = "career-overview@x.com"
    h = await _auth(client, email)
    await _seed(db_session, email)

    body = (await client.get("/api/v1/career/overview", headers=h)).json()
    direction = body["direction"]
    assert direction["slug"] == "backend-engineer"
    have = {s["slug"] for s in direction["have"]}
    assert {"python", "postgresql"} <= have
    assert "kubernetes" in {s["slug"] for s in direction["missing"]}
    assert "%" not in direction["fit_label"] + direction["why"]
    assert 1 <= len(body["next_actions"]) <= 3
    assert body["skills"][0]["slug"] == "kubernetes"


async def test_paths_and_path_detail(client, db_session):
    email = "career-paths@x.com"
    h = await _auth(client, email)
    await _seed(db_session, email)

    paths = (await client.get("/api/v1/career/paths", headers=h)).json()
    slugs = [p["slug"] for p in paths["paths"]]
    assert "backend-engineer" in slugs

    detail = await client.get("/api/v1/career/paths/backend-engineer", headers=h)
    assert detail.status_code == 200
    assert detail.json()["roles"], "path detail should list the roles behind it"

    missing = await client.get("/api/v1/career/paths/astronaut", headers=h)
    assert missing.status_code == 404


async def test_skill_plan_is_short_and_concrete(client, db_session):
    email = "career-skills@x.com"
    h = await _auth(client, email)
    await _seed(db_session, email)

    body = (
        await client.get("/api/v1/career/skills?path=backend-engineer", headers=h)
    ).json()
    assert body["path_slug"] == "backend-engineer"
    assert 1 <= len(body["steps"]) <= 5
    step = body["steps"][0]
    assert step["slug"] == "kubernetes"
    assert step["requirement"] == "Usually a requirement."
    assert "Kubernetes" in step["practice_project"]


async def test_resume_analysis_is_problem_why_suggestion(client, db_session):
    email = "career-analysis@x.com"
    h = await _auth(client, email)
    resume = await _seed(db_session, email)

    r = await client.get(f"/api/v1/resumes/{resume.id}/analysis", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["enough_text"] is True
    assert body["bullets_with_results"] >= 2
    for issue in body["issues"]:
        assert issue["problem"] and issue["why_it_matters"] and issue["suggestion"]
    assert body["target_path"]["slug"] == "backend-engineer"
    assert "Kubernetes" in body["alignment"]["missing"]


async def test_resume_analysis_waits_until_the_text_is_read(client, db_session):
    email = "career-unread@x.com"
    h = await _auth(client, email)
    resume = await _seed(db_session, email, text=None)
    r = await client.get(f"/api/v1/resumes/{resume.id}/analysis", headers=h)
    assert r.status_code == 404
    assert r.json()["code"] == "resume.not_read"


async def test_another_user_cannot_read_the_analysis(client, db_session):
    owner = "career-owner@x.com"
    await _auth(client, owner)
    resume = await _seed(db_session, owner)
    intruder = await _auth(client, "career-intruder@x.com")
    r = await client.get(f"/api/v1/resumes/{resume.id}/analysis", headers=intruder)
    assert r.status_code == 404
    paths = (await client.get("/api/v1/career/paths", headers=intruder)).json()
    assert all(p["slug"] != "backend-engineer" or not p["have"] for p in paths["paths"])
