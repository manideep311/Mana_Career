from app.domain.agents.graph import _after_resume_claim_check


def test_after_resume_claim_check_routes_prepare_application_to_cover_letter():
    state = {"goal": "prepare_application", "status": "running"}
    assert _after_resume_claim_check(state) == "cover_letter"


def test_after_resume_claim_check_routes_tailor_resume_to_respond():
    state = {"goal": "tailor_resume", "status": "running"}
    assert _after_resume_claim_check(state) == "respond"


def test_after_resume_claim_check_routes_halted_state_to_halted():
    state = {"goal": "prepare_application", "status": "halted"}
    assert _after_resume_claim_check(state) == "halted"
