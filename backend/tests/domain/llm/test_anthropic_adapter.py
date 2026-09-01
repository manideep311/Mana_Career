from types import SimpleNamespace

from app.domain.llm.adapters.anthropic import AnthropicAdapter


class _FakeMessages:
    def __init__(self, block):
        self._block = block

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[self._block],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
            model=kwargs["model"],
        )


class _FakeClient:
    def __init__(self, block):
        self.messages = _FakeMessages(block)


async def test_text_completion(monkeypatch):
    block = SimpleNamespace(type="text", text="hello there")
    a = AnthropicAdapter("k", default_model="claude-haiku-4-5-20251001")
    monkeypatch.setattr(a, "_client", _FakeClient(block))
    out = await a.complete([{"role": "user", "content": "hi"}])
    assert out.text == "hello there"
    assert out.structured is None
    assert out.input_tokens == 11 and out.output_tokens == 7


async def test_structured_via_forced_tool(monkeypatch):
    from app.domain.resume.extractor import ResumeExtraction

    block = SimpleNamespace(type="tool_use", name="emit",
                            input={"full_name": "Jane", "skills": ["Python"]})
    a = AnthropicAdapter("k", default_model="claude-haiku-4-5-20251001")
    monkeypatch.setattr(a, "_client", _FakeClient(block))
    out = await a.complete([{"role": "user", "content": "resume text"}],
                           schema=ResumeExtraction)
    assert out.structured["full_name"] == "Jane"
    assert out.structured["skills"] == ["Python"]
    # forced tool_choice was sent
    assert a._client.messages.kwargs["tool_choice"]["name"] == "emit"


def test_capabilities():
    a = AnthropicAdapter("k", default_model="m")
    caps = a.capabilities()
    assert caps.structured_output and caps.tools and caps.streaming is False
