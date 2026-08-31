from pydantic import BaseModel

from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMMessage


class _Extraction(BaseModel):
    name: str
    years: int
    skills: list[str]


async def test_complete_returns_deterministic_text():
    p = FakeLLMProvider()
    msgs: list[LLMMessage] = [{"role": "user", "content": "hello world"}]
    r1 = await p.complete(msgs)
    r2 = await p.complete(msgs)
    assert r1.text == r2.text
    assert r1.output_tokens > 0


async def test_scripted_responses_are_consumed_in_order():
    p = FakeLLMProvider(scripted=["first", "second"])
    assert (await p.complete([{"role": "user", "content": "x"}])).text == "first"
    assert (await p.complete([{"role": "user", "content": "x"}])).text == "second"


async def test_schema_path_returns_valid_model_dict():
    p = FakeLLMProvider()
    r = await p.complete([{"role": "user", "content": "extract"}], schema=_Extraction)
    assert r.structured is not None
    _Extraction.model_validate(r.structured)  # must not raise


def test_capabilities_shape():
    caps = FakeLLMProvider().capabilities()
    assert caps.structured_output is True
