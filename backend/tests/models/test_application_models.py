"""CoverLetter / ApplicationEmail model round-trip -- DB integration, CI-deferred."""
from __future__ import annotations

from app.models.application import ApplicationEmail, CoverLetter
from app.models.job import Job
from app.models.user import User


async def test_cover_letter_and_application_email_round_trip(db_session):
    u = User(email="app-docs@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    j = Job(
        user_id=None, is_seed=True, source="seed", status="ready", raw_text="x" * 60,
        title="Backend Engineer", company="Acme", required_skills=[], preferred_skills=[],
    )
    db_session.add(j)
    await db_session.flush()

    letter = CoverLetter(
        user_id=u.id, job_id=j.id, content="Dear Hiring Team,\n\nI am excited to apply.",
        created_by="mana_ai",
    )
    db_session.add(letter)
    await db_session.flush()
    assert letter.tone == "professional"
    assert letter.version == 1
    assert letter.content_json == {}
    assert letter.created_at is not None

    email = ApplicationEmail(
        user_id=u.id, job_id=j.id, subject="Application: Backend Engineer",
        body="Please find my résumé and cover letter attached.",
    )
    db_session.add(email)
    await db_session.flush()
    assert email.status == "draft"
    assert email.body_format == "plain"
    assert email.cc == []
    assert email.to_email is None
