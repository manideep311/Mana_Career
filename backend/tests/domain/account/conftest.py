"""A realistic account spread across many tables, for export and deletion tests."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

from app.domain.auth.passwords import hash_password
from app.models.ai import AiAction, AiSession, Message
from app.models.application import Application, ApplicationEmail, ApprovalRequest, CoverLetter
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.learning import LearningRecommendation
from app.models.profile import CareerProfile, ProfileExperience
from app.models.resume import Resume
from app.models.user import User

PASSWORD = "correct-passphrase"


@dataclass
class Person:
    user: User
    resume: Resume
    job: Job
    run_id: str
    file_ref: str
    rows: dict[str, object] = field(default_factory=dict)


@pytest.fixture
def seed_person(db_session):
    async def _seed(email: str, *, store=None, pdf: bytes = b"%PDF-1.4 resume") -> Person:
        user = User(email=email, password_hash=hash_password(PASSWORD), full_name="Asha Rao")
        db_session.add(user)
        await db_session.flush()
        uid = user.id

        profile = CareerProfile(user_id=uid, preferred_roles=["Backend Engineer"])
        db_session.add(profile)
        await db_session.flush()
        db_session.add(ProfileExperience(
            user_id=uid, profile_id=profile.id, company="Acme", title="Backend Engineer",
            highlights=["Built FastAPI services"],
        ))

        file_ref = f"resumes/{uid}/{uuid.uuid4()}.pdf"
        if store is not None:
            await store.put(file_ref, pdf, content_type="application/pdf")
        resume = Resume(
            user_id=uid, file_ref=file_ref, content_type="application/pdf", size_bytes=len(pdf),
            original_filename="Asha Rao CV.pdf", status="extracted", is_primary=True,
            extracted_text="Backend engineer. Built Python and FastAPI services.",
        )
        job = Job(user_id=uid, raw_text="A private pasted role", title="Platform Engineer",
                  company="Initech", status="ready")
        db_session.add_all([resume, job])
        await db_session.flush()

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        session = AiSession(user_id=uid, kind="agent_run", run_id=run_id)
        db_session.add(session)
        await db_session.flush()
        db_session.add(Message(ai_session_id=session.id, user_id=uid, role="user",
                               content="Help me apply to Initech"))
        db_session.add(AiAction(user_id=uid, ai_session_id=session.id, run_id=run_id,
                                node="cover_letter", action_key="wrote_letter",
                                summary="Wrote a cover letter", status="ok"))

        letter = CoverLetter(user_id=uid, job_id=job.id, content="Dear Initech, I build APIs.")
        email_row = ApplicationEmail(user_id=uid, job_id=job.id, subject="Application",
                                     body="Hello Initech", to_email="jobs@initech.test")
        db_session.add_all([letter, email_row])
        await db_session.flush()
        application = Application(user_id=uid, job_id=job.id, status="awaiting_approval",
                                  cover_letter_id=letter.id, application_email_id=email_row.id)
        db_session.add(application)
        await db_session.flush()
        db_session.add(ApprovalRequest(user_id=uid, application_id=application.id,
                                       ai_session_id=session.id, run_id=run_id,
                                       payload_hash="a" * 64))
        db_session.add(LearningRecommendation(user_id=uid, scope="aggregate",
                                              title="Close your gaps", constraints={},
                                              status="active", generation_meta={}))
        db_session.add(AuditLog(actor_type="user", actor_user_id=uid, action="auth.login",
                                ip="203.0.113.7", user_agent="Firefox",
                                before={"email": email}, after={"email": email}))
        await db_session.flush()
        return Person(user=user, resume=resume, job=job, run_id=run_id, file_ref=file_ref)

    return _seed
