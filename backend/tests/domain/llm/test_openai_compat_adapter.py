"""OpenAICompatAdapter against a fake chat-completions API (httpx.MockTransport)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field

from app.core.errors import AIUnavailableError, AppError
from app.domain.llm.adapters.openai_compat import (
    REASONING_HEADROOM_TOKENS,
    OpenAICompatAdapter,
    strip_reasoning,
    to_response_schema,
)
from app.domain.matching.explainer import RationalesOut
from app.domain.resume.extractor import ResumeExtraction

KEY = "gsk_test_key"
MODEL = "openai/gpt-oss-20b"


class Verdict(BaseModel):
    label: str
    score: int = Field(ge=0, le=10)
    note: str | None = None


def _reply(content: str, *, prompt: int = 100, completion: int = 20) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": MODEL,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        },
    )


class FakeAPI:
    """Hands out the queued responses in order and records every request."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.queue = list(responses)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.path == "/openai/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {KEY}"
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def body(self, n: int) -> dict[str, Any]:
        return json.loads(self.requests[n].content)


def _adapter(api: FakeAPI, **kw: Any) -> tuple[OpenAICompatAdapter, list[float]]:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    adapter = OpenAICompatAdapter(
        base_url="https://api.groq.com/openai/v1/",
        api_key=KEY,
        model=MODEL,
        transport=httpx.MockTransport(api.handler),
        sleep=sleep,
        **kw,
    )
    return adapter, slept


async def test_plain_text_with_reasoning_headroom_and_cost():
    api = FakeAPI(_reply("Hello there", prompt=1_000_000, completion=1_000_000))
    adapter, _ = _adapter(api)
    out = await adapter.complete(
        [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}],
        max_tokens=300,
        temperature=0.1,
    )
    assert out.text == "Hello there" and out.structured is None
    assert out.model == MODEL
    # Groq list price for gpt-oss-20b: $0.075 in / $0.30 out per million tokens.
    assert out.cost_usd == pytest.approx(0.375)
    sent = api.body(0)
    assert sent["model"] == MODEL and sent["temperature"] == 0.1
    assert sent["messages"][0] == {"role": "system", "content": "Be brief."}
    assert sent["reasoning_effort"] == "low"
    assert sent["max_completion_tokens"] == 300 + REASONING_HEADROOM_TOKENS
    assert "response_format" not in sent


async def test_reasoning_can_be_switched_off():
    api = FakeAPI(_reply("ok"))
    adapter, _ = _adapter(api, reasoning_effort="none")
    await adapter.complete([{"role": "user", "content": "hi"}], max_tokens=50)
    assert "reasoning_effort" not in api.body(0)
    assert api.body(0)["max_completion_tokens"] == 50


async def test_think_blocks_are_stripped():
    api = FakeAPI(_reply("<think>The user wants a greeting.</think>\nHi!"))
    adapter, _ = _adapter(api)
    out = await adapter.complete([{"role": "user", "content": "hi"}])
    assert out.text == "Hi!"
    assert strip_reasoning("<THINK>a\nb</THINK> x <think>cut off") == "x"


async def test_structured_output_uses_strict_json_schema():
    api = FakeAPI(_reply('{"label": "fit", "score": 7, "note": null}'))
    adapter, _ = _adapter(api)
    out = await adapter.complete([{"role": "user", "content": "rate"}], schema=Verdict)
    assert out.structured == {"label": "fit", "score": 7, "note": None}
    assert json.loads(out.text) == out.structured
    fmt = api.body(0)["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "Verdict"
    assert fmt["json_schema"]["strict"] is True
    schema = fmt["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["label", "score", "note"]
    # Validation keywords are left to Pydantic, not the provider.
    assert "maximum" not in json.dumps(schema)


async def test_invalid_json_gets_one_retry_with_the_validation_error():
    fenced = '```json\n{"label": "fit", "score": 9, "note": "close"}\n```'
    api = FakeAPI(
        _reply('{"label": "fit", "score": 42, "note": null}', prompt=50, completion=10),
        _reply(fenced, prompt=80, completion=12),
    )
    adapter, _ = _adapter(api)
    out = await adapter.complete([{"role": "user", "content": "rate"}], schema=Verdict)
    assert out.structured == {"label": "fit", "score": 9, "note": "close"}
    # Both calls are paid for.
    assert (out.input_tokens, out.output_tokens) == (130, 22)
    retry_msgs = api.body(1)["messages"]
    assert retry_msgs[-2]["role"] == "assistant"
    assert "score" in retry_msgs[-1]["content"]
    assert "less than or equal to 10" in retry_msgs[-1]["content"]


async def test_two_invalid_replies_give_a_clear_error():
    api = FakeAPI(_reply("not json"), _reply("still not json"))
    adapter, _ = _adapter(api)
    with pytest.raises(AppError) as caught:
        await adapter.complete([{"role": "user", "content": "rate"}], schema=Verdict)
    assert caught.value.code == "llm.invalid_output"


async def test_provider_side_schema_rejection_is_retried():
    # Groq's best-effort mode answers a mismatch with a 400 json_validate_failed.
    rejected = httpx.Response(
        400,
        json={"error": {"code": "json_validate_failed", "failed_generation": '{"x": 1}'}},
    )
    api = FakeAPI(rejected, _reply('{"rationales": {"Docker": "Ships the app."}}'))
    adapter, _ = _adapter(api)
    out = await adapter.complete([{"role": "user", "content": "why"}], schema=RationalesOut)
    assert out.structured == {"rationales": {"Docker": "Ships the app."}}
    assert api.body(1)["messages"][-2] == {"role": "assistant", "content": '{"x": 1}'}


def test_free_form_dict_fields_fall_back_to_best_effort_mode():
    _, strict = to_response_schema(RationalesOut)
    assert strict is False
    schema, strict = to_response_schema(ResumeExtraction)
    assert strict is True
    # Every object, including the nested $defs, is closed with all keys required.
    for d in schema["$defs"].values():
        assert d["additionalProperties"] is False
        assert d["required"] == list(d["properties"])


async def test_a_short_429_is_waited_out_once():
    limited = httpx.Response(429, headers={"retry-after": "2"}, json={"error": {}})
    api = FakeAPI(limited, _reply("ok"))
    adapter, slept = _adapter(api)
    out = await adapter.complete([{"role": "user", "content": "hi"}])
    assert out.text == "ok" and slept == [2.0]


async def test_a_long_429_becomes_a_busy_quota_error():
    api = FakeAPI(httpx.Response(429, headers={"retry-after": "37.2"}, json={"error": {}}))
    adapter, slept = _adapter(api)
    with pytest.raises(AIUnavailableError) as caught:
        await adapter.complete([{"role": "user", "content": "hi"}])
    assert caught.value.retry_after == 38 and slept == []
    assert caught.value.code == "ai_busy"
    assert str(caught.value) == "The free AI quota is busy, try again shortly"


async def test_repeated_429s_stop_after_one_wait():
    limited = httpx.Response(429, headers={"retry-after": "1"}, json={"error": {}})
    api = FakeAPI(limited, limited)
    adapter, slept = _adapter(api)
    with pytest.raises(AIUnavailableError):
        await adapter.complete([{"role": "user", "content": "hi"}])
    assert slept == [1.0]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_server_errors_retry_once_then_report_busy(status: int):
    api = FakeAPI(httpx.Response(status), httpx.Response(status))
    adapter, slept = _adapter(api)
    with pytest.raises(AIUnavailableError):
        await adapter.complete([{"role": "user", "content": "hi"}])
    assert len(api.requests) == 2 and slept == [1.0]


async def test_timeouts_report_busy_without_leaking_details():
    api = FakeAPI(httpx.ReadTimeout("slow"))
    adapter, _ = _adapter(api)
    with pytest.raises(AIUnavailableError) as caught:
        await adapter.complete([{"role": "user", "content": "hi"}])
    assert caught.value.detail is None


async def test_a_bad_key_is_an_auth_error_not_a_busy_quota():
    api = FakeAPI(httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))
    adapter, _ = _adapter(api)
    with pytest.raises(AppError) as caught:
        await adapter.complete([{"role": "user", "content": "hi"}])
    assert not isinstance(caught.value, AIUnavailableError)
    assert caught.value.code == "llm.auth_failed"


async def test_a_request_over_the_per_minute_token_allowance_is_not_a_busy_quota():
    too_big = httpx.Response(
        413,
        json={"error": {"code": "rate_limit_exceeded", "message": "Request too large for model"}},
    )
    api = FakeAPI(too_big)
    adapter, slept = _adapter(api)
    with pytest.raises(AppError) as caught:
        await adapter.complete([{"role": "user", "content": "a very long résumé"}])
    assert not isinstance(caught.value, AIUnavailableError)
    assert caught.value.code == "llm.request_too_large"
    assert slept == [] and len(api.requests) == 1


async def test_unknown_models_cost_nothing_rather_than_guessing():
    api = FakeAPI(_reply("ok"))
    adapter = OpenAICompatAdapter(
        base_url="https://api.groq.com/openai/v1", api_key=KEY, model="some/new-model",
        transport=httpx.MockTransport(api.handler),
    )
    api.queue[0] = httpx.Response(
        200,
        json={
            "model": "some/new-model",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )
    out = await adapter.complete([{"role": "user", "content": "hi"}])
    assert out.cost_usd == 0.0 and out.input_tokens == 10


def test_capabilities():
    adapter, _ = _adapter(FakeAPI())
    caps = adapter.capabilities()
    assert caps.structured_output and not caps.tools and not caps.streaming
