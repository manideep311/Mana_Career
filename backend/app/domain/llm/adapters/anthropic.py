from __future__ import annotations

import json
from typing import Any, cast

from anthropic import APIError, AsyncAnthropic
from anthropic.types import Message
from pydantic import BaseModel

from app.core.errors import AppError
from app.core.logging import get_logger
from app.domain.llm.provider import LLMCapabilities, LLMMessage, LLMResult

log = get_logger("llm.anthropic")

# Approximate USD list prices per 1M tokens as ``(input_rate, output_rate)``.
# Hand-maintained and rounded -- reconcile against actual Anthropic billing
# before using these figures for anything that must be exact.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-5": (15.0, 75.0),
}


class AnthropicAdapter:
    """Real Claude provider: ``complete()`` with forced-tool structured output.

    Streaming is intentionally unsupported here; it lands in a later phase.
    """

    def __init__(self, api_key: str, *, default_model: str) -> None:
        self._default_model = default_model
        # Cheap: builds an HTTP client, performs no network I/O. Tests replace
        # this attribute wholesale with a fake, so it must exist after __init__.
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        convo = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] != "system"
        ]

        # This SDK version exposes no ``temperature`` parameter on
        # ``messages.create``; forward the caller's value via ``extra_body``.
        create_kwargs: dict[str, Any] = {
            "model": self._default_model,
            "max_tokens": max_tokens,
            "messages": convo,
            "extra_body": {"temperature": temperature},
        }
        if system_parts:
            create_kwargs["system"] = "\n\n".join(system_parts)
        if schema is not None:
            create_kwargs["tools"] = [
                {
                    "name": "emit",
                    "description": "Return the structured result.",
                    "input_schema": schema.model_json_schema(),
                }
            ]
            create_kwargs["tool_choice"] = {"type": "tool", "name": "emit"}

        try:
            raw = await self._client.messages.create(**create_kwargs)
        except APIError as exc:
            raise AppError(code="llm.upstream_error", detail=str(exc)) from exc

        # We never pass ``stream``, so the union is always a ``Message``.
        response = cast(Message, raw)
        blocks = list(response.content)

        structured: dict[str, Any] | None = None
        if schema is None:
            text = next(
                (
                    getattr(b, "text", "")
                    for b in blocks
                    if getattr(b, "type", None) == "text"
                ),
                "",
            )
        else:
            tool_block = next(
                (b for b in blocks if getattr(b, "type", None) == "tool_use"), None
            )
            if tool_block is None:
                raise AppError(code="llm.no_tool_use")
            structured = schema.model_validate(
                getattr(tool_block, "input", {})
            ).model_dump()
            text = json.dumps(structured)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        model: str = response.model

        rates = _PRICE_PER_MTOK.get(model)
        if rates is None:
            log.debug("llm_price_unknown", model=model)
            cost_usd = 0.0
        else:
            in_rate, out_rate = rates
            cost_usd = input_tokens / 1e6 * in_rate + output_tokens / 1e6 * out_rate

        return LLMResult(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            structured=structured,
        )

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(structured_output=True, tools=True, streaming=False)
