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


async def test_human_approval_routes_approve_to_email_external_action(monkeypatch):
    from unittest.mock import AsyncMock

    import app.domain.agents.nodes.human_approval as mod

    deps = AsyncMock()
    deps.session.get = AsyncMock(return_value=None)

    # human_approval calls interrupt(), which raises GraphInterrupt when not
    # running inside a real graph invocation with a resume value queued.
    # Test the routing logic directly instead, bypassing interrupt(): this is
    # the same "test the pure decision logic, not the LangGraph plumbing"
    # split already used elsewhere (e.g. claim_validator's node vs its
    # ClaimValidator primitive). Patch interrupt() to return a canned value.
    monkeypatch.setattr(mod, "interrupt", lambda payload: {"decision": "approve"})
    out = await mod.human_approval(
        {"approval_request_id": "11111111-1111-1111-1111-111111111111"}, deps=deps
    )
    assert out["_route"] == "email_external_action"


async def test_human_approval_routes_reject_to_halted(monkeypatch):
    from unittest.mock import AsyncMock

    import app.domain.agents.nodes.human_approval as mod

    deps = AsyncMock()
    deps.session.get = AsyncMock(return_value=None)

    monkeypatch.setattr(mod, "interrupt", lambda payload: {"decision": "reject"})
    out = await mod.human_approval(
        {"approval_request_id": "11111111-1111-1111-1111-111111111111"}, deps=deps
    )
    assert out["status"] == "rejected"
    assert out["_route"] == "halted"


async def test_email_external_action_halts_when_not_approved():
    from unittest.mock import AsyncMock

    from app.domain.agents.nodes.email_external_action import email_external_action

    deps = AsyncMock()
    approval = AsyncMock(status="pending")
    deps.session.get = AsyncMock(return_value=approval)

    out = await email_external_action(
        {"approval_request_id": "11111111-1111-1111-1111-111111111111"}, deps=deps
    )
    assert out["status"] == "halted"
