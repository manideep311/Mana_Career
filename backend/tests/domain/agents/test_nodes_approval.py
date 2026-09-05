from app.domain.agents.nodes.application_prep import application_prep


async def test_application_prep_halts_with_no_cover_letter():
    out = await application_prep(
        {"inputs": {"job_id": "j1"}, "cover_letter_id": None, "email_draft_id": None},
        deps=object(),
    )
    assert out["status"] == "halted"


async def test_application_prep_halts_with_letter_but_no_email():
    out = await application_prep(
        {
            "inputs": {"job_id": "j1"},
            "cover_letter_id": "11111111-1111-1111-1111-111111111111",
            "email_draft_id": None,
        },
        deps=object(),
    )
    assert out["status"] == "halted"
