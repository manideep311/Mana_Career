from app.domain.agents.graph import _route_from_human_approval


def test_route_from_human_approval_reads_the_explicit_route():
    state = {"_route": "email_external_action"}
    assert _route_from_human_approval(state) == "email_external_action"


def test_route_from_human_approval_defaults_to_halted():
    assert _route_from_human_approval({}) == "halted"
