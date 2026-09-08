"""No user can read or mutate another user's rows. DB integration, CI-deferred.

Isolation is enforced by every user-scoped service filtering ``user_id`` and
raising ``NotFoundError`` (404, never 403 -- a 403 would leak that the row
exists). This module proves the guarantee holds for *every* resource with a
by-id or list route, not just the ones with ad-hoc coverage in ``tests/api/``.

One A-owned row per resource is inserted directly with ``db_session`` (mirroring
``tests/api/test_approvals.py`` and ``tests/api/test_roadmaps.py``); user B then
drives every by-id route the resource supports and must get **404** on each. A
companion test asserts B's list endpoints never surface A's ids.

DB-gated: the module ERRORs at the session-scoped ``_migrated`` fixture without a
Postgres instance (CI-only) but must collect clean.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.ai import AiSession
from app.models.application import Application, ApprovalRequest
from app.models.job import Job
from app.models.learning import LearningRecommendation, RoadmapMilestone
from app.models.match import JobMatch, SkillGap
from app.models.resume import Resume
from app.models.skill import Skill
from app.models.user import User

_PASSWORD = "correct-passphrase"


async def _auth(client, email):
    """Register + log in a real user; return an Authorization header for B/A."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "full_name": "M"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed_all_as_a(db_session, user_a) -> dict[str, str]:
    """Insert exactly one A-owned row per resource; return the ids as strings."""
    uid = user_a.id

    job = Job(
        user_id=uid, is_seed=False, source="user_paste", status="ready",
        raw_text="x" * 60, title="T", company="C",
        required_skills=[], preferred_skills=[],
    )
    resume = Resume(
        user_id=uid, file_ref="seed/iso.pdf", content_type="application/pdf",
        size_bytes=1024, original_filename="iso.pdf", status="uploaded",
    )
    db_session.add_all([job, resume])
    await db_session.flush()

    match = JobMatch(
        user_id=uid, job_id=job.id, scorer_version="v1", status="ready",
    )
    application = Application(
        user_id=uid, job_id=job.id, status="saved", source="user",
    )
    db_session.add_all([match, application])
    await db_session.flush()

    approval = ApprovalRequest(
        user_id=uid, application_id=application.id, ai_session_id=application.id,
        run_id=f"run-{uuid.uuid4().hex}", payload_hash="a" * 64,
    )
    session = AiSession(user_id=uid, kind="chat", status="idle")
    rec = LearningRecommendation(
        user_id=uid, scope="aggregate", title="R", constraints={},
        status="active", generation_meta={},
    )
    skill = Skill(slug="python", label="Python", category="language", aliases=[])
    db_session.add_all([approval, session, rec, skill])
    await db_session.flush()

    milestone = RoadmapMilestone(
        recommendation_id=rec.id, user_id=uid, order_index=0,
        skill_slug="python", skill_label="Python", title="M",
        why_it_matters="x", resource_ids=[],
    )
    gap = SkillGap(
        user_id=uid, scope="aggregate", skill_id=skill.id, skill_slug="python",
        skill_label="Python", severity="important", frequency=1, status="open",
    )
    db_session.add_all([milestone, gap])
    await db_session.flush()

    return {
        "resume_id": str(resume.id),
        "job_id": str(job.id),
        "match_id": str(match.id),
        "application_id": str(application.id),
        "approval_id": str(approval.id),
        "roadmap_id": str(rec.id),
        "milestone_id": str(milestone.id),
        "session_id": str(session.id),
        "skill_gap_id": str(gap.id),
    }


@pytest.fixture
async def isolation_env(client, db_session):
    """Register A + B, then seed one owned row per resource as A.

    Returns ``(b_headers, ids)`` -- B's auth header and A's resource ids.
    """
    await _auth(client, "iso-a@x.com")
    b_headers = await _auth(client, "iso-b@x.com")
    user_a = (
        await db_session.execute(select(User).where(User.email == "iso-a@x.com"))
    ).scalar_one()
    ids = await _seed_all_as_a(db_session, user_a)
    return b_headers, ids


# (method, path template keyed on the ``_seed_all_as_a`` id names, json body).
# Only methods the route actually defines are listed:
#   matches    -> GET only
#   skill-gaps -> PATCH only
#   ai/sessions-> GET + POST /stop
_PROBES = [
    pytest.param("GET", "/api/v1/resumes/{resume_id}", None, id="resumes-GET"),
    pytest.param(
        "PATCH", "/api/v1/resumes/{resume_id}", {"title": "x"}, id="resumes-PATCH"
    ),
    pytest.param(
        "DELETE", "/api/v1/resumes/{resume_id}", None, id="resumes-DELETE"
    ),
    pytest.param("GET", "/api/v1/jobs/{job_id}", None, id="jobs-GET"),
    pytest.param(
        "PATCH", "/api/v1/jobs/{job_id}", {"title": "x"}, id="jobs-PATCH"
    ),
    pytest.param("DELETE", "/api/v1/jobs/{job_id}", None, id="jobs-DELETE"),
    pytest.param("GET", "/api/v1/matches/{match_id}", None, id="matches-GET"),
    pytest.param(
        "GET", "/api/v1/applications/{application_id}", None,
        id="applications-GET",
    ),
    pytest.param(
        "PATCH", "/api/v1/applications/{application_id}", {"status": "applied"},
        id="applications-PATCH",
    ),
    pytest.param(
        "DELETE", "/api/v1/applications/{application_id}", None,
        id="applications-DELETE",
    ),
    pytest.param(
        "GET", "/api/v1/approvals/{approval_id}", None, id="approvals-GET"
    ),
    pytest.param(
        "POST", "/api/v1/approvals/{approval_id}", {"decision": "reject"},
        id="approvals-POST",
    ),
    pytest.param(
        "GET", "/api/v1/roadmaps/{roadmap_id}", None, id="roadmaps-GET"
    ),
    pytest.param(
        "PATCH", "/api/v1/roadmaps/{roadmap_id}", {"status": "archived"},
        id="roadmaps-PATCH",
    ),
    pytest.param(
        "PATCH",
        "/api/v1/roadmaps/{roadmap_id}/milestones/{milestone_id}",
        {"status": "done"},
        id="roadmaps-milestone-PATCH",
    ),
    pytest.param(
        "GET", "/api/v1/ai/sessions/{session_id}", None, id="ai-sessions-GET"
    ),
    pytest.param(
        "POST", "/api/v1/ai/sessions/{session_id}/stop", None,
        id="ai-sessions-stop",
    ),
    pytest.param(
        "PATCH", "/api/v1/skill-gaps/{skill_gap_id}", {"status": "learning"},
        id="skill-gaps-PATCH",
    ),
]


@pytest.mark.parametrize(("method", "path_tmpl", "body"), _PROBES)
async def test_non_owner_gets_404(client, isolation_env, method, path_tmpl, body):
    """B hitting A's resource id must get 404 -- never 403 (existence leak) or 200."""
    b_headers, ids = isolation_env
    path = path_tmpl.format(**ids)
    kwargs: dict[str, object] = {"headers": b_headers}
    if body is not None:
        kwargs["json"] = body
    r = await client.request(method, path, **kwargs)
    # Strict on purpose: a 403 leaks that the row exists, a 2xx is a breach.
    # If a route ever returns something else for a non-owner, this fails and the
    # finding gets reported -- do not soften to ``in (403, 404)``.
    assert r.status_code == 404, (
        f"{method} {path} returned {r.status_code} for a non-owner, expected 404"
    )


def _ids_in(payload) -> set[str]:
    items = payload if isinstance(payload, list) else payload.get("items", [])
    return {item["id"] for item in items}


async def test_list_endpoints_do_not_leak_a_rows(client, isolation_env):
    """B's collection endpoints must never include A's rows."""
    b_headers, ids = isolation_env
    for path, key in (
        ("/api/v1/applications", "application_id"),
        ("/api/v1/roadmaps", "roadmap_id"),
        ("/api/v1/resumes", "resume_id"),
    ):
        r = await client.get(path, headers=b_headers)
        assert r.status_code == 200
        assert ids[key] not in _ids_in(r.json()), f"{path} leaked A's row to B"
