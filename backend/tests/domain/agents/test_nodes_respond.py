from app.domain.agents.nodes.recommendation import recommendation


class _FakeLLM:
    model = "fake"

    async def complete(self, messages, **kw):
        from app.domain.llm.provider import LLMResult

        return LLMResult(text="", model="fake", input_tokens=1, output_tokens=1, cost_usd=0.0)


async def test_recommendation_is_a_skipped_stub():
    out = await recommendation({}, deps=object())
    assert out["_step_status"] == "skipped_fresh"


async def test_respond_emits_insufficient_info_when_nothing_retrieved(db_session):
    from app.domain.agents.nodes.respond import respond
    from app.domain.agents.service import AgentService
    from app.models.user import User

    u = User(email="respond-empty@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    s = await AgentService(db_session).create_session(u.id)

    class D:
        session = db_session
        llm = _FakeLLM()
        svc = AgentService(db_session)
        user_id = u.id
        session_id = s.id
        run_id = "r1"

    out = await respond({"retrieved_jobs": [], "match_refs": [],
                         "budget": {"llm_calls_made": 0, "cost_usd": 0.0}}, deps=D())
    assert out["status"] == "completed"
    assert out["blocks"][0]["kind"] == "insufficient_info"
