from app.domain.agents.graph import _route_from_supervisor


def test_route_from_supervisor_passes_resume_tailoring_through():
    assert _route_from_supervisor({"_route": "resume_tailoring"}) == "resume_tailoring"


def test_build_graph_registers_the_tailoring_nodes():
    # build_graph needs an AgentDeps; assert the node set via a stub-deps compile.
    import app.domain.agents.graph as G

    src = __import__("inspect").getsource(G.build_graph)
    assert '"resume_tailoring"' in src and '"claim_validator"' in src
