from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic import BaseModel

from app.domain.llm.provider import LLMCapabilities, LLMMessage, LLMResult

_SCALAR_STUBS: dict[type, Any] = {str: "", int: 0, float: 0.0, bool: False}


def _stub_for(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (list, set, tuple, frozenset):
        return []
    if origin is dict:
        return {}
    if annotation in _SCALAR_STUBS:
        return _SCALAR_STUBS[annotation]
    args = [a for a in get_args(annotation) if a is not type(None)]
    if args:
        return _stub_for(args[0])
    return None


class FakeLLMProvider:
    """Deterministic, offline stand-in for a real LLM provider."""

    def __init__(self, scripted: list[str] | None = None) -> None:
        self._scripted = list(scripted or [])

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult:
        if self._scripted:
            text = self._scripted.pop(0)
        else:
            last = messages[-1]["content"] if messages else ""
            text = f"[fake:{last[:40]}]"
        structured: dict[str, Any] | None = None
        if schema is not None:
            data = {
                name: _stub_for(field.annotation)
                for name, field in schema.model_fields.items()
            }
            structured = schema.model_validate(data).model_dump()
        n = max(1, len(text.split()))
        return LLMResult(
            text=text,
            model="fake-llm-1",
            input_tokens=n,
            output_tokens=n,
            cost_usd=0.0,
            structured=structured,
        )

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(structured_output=True, tools=False, streaming=False)
