import pytest
from pydantic import BaseModel

from app.domain.generation.service import GenerationError, GenerationService
from app.domain.llm.adapters.fake import FakeLLMProvider


class _Tiny(BaseModel):
    a: str = ""
    b: int = 0


async def test_generate_returns_validated_structured_and_stable_hash():
    llm = FakeLLMProvider()
    svc = GenerationService(llm)
    r1 = await svc.generate(system="S", user="U-one", schema=_Tiny, prompt_version="v1")
    r2 = await svc.generate(system="S", user="U-one", schema=_Tiny, prompt_version="v1")
    r3 = await svc.generate(system="S", user="U-two", schema=_Tiny, prompt_version="v1")
    assert r1.meta.prompt_hash == r2.meta.prompt_hash
    assert r1.meta.prompt_hash != r3.meta.prompt_hash
    assert r1.meta.prompt_version == "v1"
    assert r1.meta.claim_validation == {}
    assert set(r1.structured) == {"a", "b"}   # schema-validated dump
    assert r1.meta.cost_usd == 0.0


async def test_generate_raises_when_no_structured_payload():
    class _NoStruct(FakeLLMProvider):
        async def complete(self, messages, **kw):  # type: ignore[override]
            from app.domain.llm.provider import LLMResult
            return LLMResult(text="x", model="fake", input_tokens=1, output_tokens=1, cost_usd=0.0)

    with pytest.raises(GenerationError):
        await GenerationService(_NoStruct()).generate(
            system="S", user="U", schema=_Tiny, prompt_version="v1"
        )
