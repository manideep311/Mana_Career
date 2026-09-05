from app.domain.agents.nodes.supervisor import supervisor


async def test_supervisor_routes_prepare_application():
    out = await supervisor(
        {"goal": "prepare_application", "inputs": {"job_id": "j1"}}, deps=object()
    )
    assert out["_route"] == "resume_tailoring"


async def test_cover_letter_halts_with_no_tailored_resume():
    from app.domain.agents.nodes.cover_letter import cover_letter

    out = await cover_letter(
        {"inputs": {"job_id": "j1"}, "tailored_resume_version_id": None}, deps=object()
    )
    assert out["status"] == "halted"


async def test_letter_claim_validator_skips_with_no_cover_letter():
    from app.domain.agents.nodes.letter_claim_validator import letter_claim_validator

    out = await letter_claim_validator({"cover_letter_id": None}, deps=object())
    assert out["_step_status"] == "skipped_fresh"


async def test_email_draft_halts_with_no_cover_letter():
    from app.domain.agents.nodes.email_draft import email_draft

    out = await email_draft({"cover_letter_id": None}, deps=object())
    assert out["status"] == "halted"
