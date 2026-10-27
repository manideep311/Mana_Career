"""LLM provider for any OpenAI-compatible chat-completions API.

Groq is the default (``LLM_BASE_URL=https://api.groq.com/openai/v1``) because
its free plan needs no card; OpenRouter, vLLM and Ollama speak the same API.

Structured output uses ``response_format: json_schema``. When the schema can be
expressed in strict mode (every object closed, every field listed in
``required``), the provider decodes against it, so the reply always parses;
otherwise it is a best-effort request. Either way the reply is validated with
the Pydantic model, and one invalid reply gets a single retry that quotes the
validation errors back to the model.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from app.core.errors import AIUnavailableError, AppError
from app.core.logging import get_logger
from app.domain.llm.provider import LLMCapabilities, LLMMessage, LLMResult

log = get_logger("llm.openai_compat")

ReasoningEffort = Literal["none", "low", "medium", "high"]

# USD list prices per 1M tokens as ``(input_rate, output_rate)``, from
# console.groq.com/docs/models (checked 2026-10-27). They keep the agent's cost
# budget meaningful even on the free plan, where nothing is billed. A model
# missing here costs 0.0 and is logged.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
}

# Reasoning models spend completion tokens thinking before they answer; this
# much is added on top of the caller's ``max_tokens`` so the answer itself
# isn't cut short.
REASONING_HEADROOM_TOKENS = 1024
# A 429 that asks for at most this long is waited out once, in place.
MAX_INLINE_WAIT_SECONDS = 10.0
_SERVER_ERRORS = {500, 502, 503, 504}
_THINK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
# JSON-schema keywords strict mode doesn't need; Pydantic re-checks them anyway.
_DROP_KEYS = frozenset(
    {
        "title", "default", "examples", "format", "pattern",
        "minLength", "maxLength", "minimum", "maximum",
        "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        "minItems", "maxItems", "uniqueItems",
    }
)


class _SchemaMismatch(Exception):
    """The provider itself rejected its own reply as not matching the schema."""

    def __init__(self, generated: str) -> None:
        super().__init__("generated JSON did not match the schema")
        self.generated = generated


def strip_reasoning(text: str) -> str:
    """Drop ``<think>…</think>`` blocks (and an unclosed one at the end)."""
    return _THINK_RE.sub("", text).strip()


def _json_payload(text: str) -> str:
    text = strip_reasoning(text)
    fenced = _FENCE_RE.match(text)
    return fenced.group(1) if fenced else text


def to_response_schema(model: type[BaseModel]) -> tuple[dict[str, Any], bool]:
    """The model's JSON schema made strict-mode friendly, and whether strict
    mode can be used at all (a ``dict[str, X]`` field has no fixed keys, so a
    schema containing one falls back to best-effort mode)."""
    strict = True

    def walk(node: Any) -> Any:
        nonlocal strict
        if isinstance(node, list):
            return [walk(v) for v in node]
        if not isinstance(node, dict):
            return node
        out = {k: walk(v) for k, v in node.items() if k not in _DROP_KEYS}
        if "properties" in out:
            # Properties are names, not keywords: keep every one of them.
            out["properties"] = {k: walk(v) for k, v in node["properties"].items()}
            out["required"] = list(out["properties"])
            out["additionalProperties"] = False
        elif out.get("type") == "object":
            strict = False
        return out

    schema = walk(model.model_json_schema())
    return schema, strict


def _validation_summary(exc: ValidationError) -> str:
    lines = [
        f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
        for err in exc.errors(include_input=False, include_url=False)
    ]
    return "\n".join(lines[:20])


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return max(0.0, float(response.headers["retry-after"]))
    except (KeyError, ValueError):
        return None


class OpenAICompatAdapter:
    """``LLMProvider`` over ``POST {base_url}/chat/completions``."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        reasoning_effort: ReasoningEffort = "low",
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model
        self._timeout = timeout_seconds
        self._reasoning_effort = reasoning_effort
        self._transport = transport
        self._sleep = sleep

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if self._reasoning_effort != "none":
            body["reasoning_effort"] = self._reasoning_effort
            body["max_completion_tokens"] = max_tokens + REASONING_HEADROOM_TOKENS
        if schema is None:
            data = await self._post(body)
            return self._result(data, strip_reasoning(self._content(data)), None)

        response_schema, strict = to_response_schema(schema)
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "strict": strict, "schema": response_schema},
        }
        spent: list[dict[str, Any]] = []
        reply = ""
        try:
            spent.append(await self._post(body))
            reply = self._content(spent[-1])
            structured = schema.model_validate_json(_json_payload(reply))
        except _SchemaMismatch as exc:
            reply, problem = exc.generated, str(exc)
            structured = None
        except ValidationError as exc:
            problem = _validation_summary(exc)
            structured = None
        if structured is None:
            # One retry, showing the model exactly what was wrong.
            log.info("llm_structured_retry", schema=schema.__name__, strict=strict)
            retry = {
                **body,
                "messages": [
                    *body["messages"],
                    {"role": "assistant", "content": reply},
                    {
                        "role": "user",
                        "content": "That reply did not match the required JSON schema:\n"
                        f"{problem}\nReply again with only the corrected JSON object.",
                    },
                ],
            }
            try:
                spent.append(await self._post(retry))
                structured = schema.model_validate_json(_json_payload(self._content(spent[-1])))
            except (ValidationError, _SchemaMismatch) as again:
                raise AppError(code="llm.invalid_output") from again
        dumped = structured.model_dump()
        return self._result(spent[-1], json.dumps(dumped), dumped, spent=spent)

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(structured_output=True, tools=False, streaming=False)

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"].get("content") or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError(code="llm.malformed_response") from exc

    def _result(
        self,
        data: dict[str, Any],
        text: str,
        structured: dict[str, Any] | None,
        *,
        spent: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        responses = spent if spent else [data]
        input_tokens = sum(int((r.get("usage") or {}).get("prompt_tokens", 0)) for r in responses)
        output_tokens = sum(
            int((r.get("usage") or {}).get("completion_tokens", 0)) for r in responses
        )
        model = str(data.get("model") or self._model)
        rates = _PRICE_PER_MTOK.get(model) or _PRICE_PER_MTOK.get(self._model)
        if rates is None:
            log.debug("llm_price_unknown", model=model)
            cost_usd = 0.0
        else:
            cost_usd = input_tokens / 1e6 * rates[0] + output_tokens / 1e6 * rates[1]
        return LLMResult(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            structured=structured,
        )

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        """One call, with a single in-place retry for a short 429 or a 5xx."""
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url, headers=self._headers,
                    timeout=self._timeout, transport=self._transport,
                ) as client:
                    response = await client.post("/chat/completions", json=body)
            except httpx.TimeoutException as exc:
                log.warning("llm_timeout", timeout_seconds=self._timeout)
                raise AIUnavailableError() from exc
            except httpx.TransportError as exc:
                log.warning("llm_transport_error", error=type(exc).__name__)
                raise AIUnavailableError() from exc

            status = response.status_code
            if status == 429:
                wait = _retry_after(response)
                log.warning("llm_rate_limited", retry_after=wait, attempt=attempt + 1)
                if attempt == 0 and wait is not None and wait <= MAX_INLINE_WAIT_SECONDS:
                    await self._sleep(wait)
                    continue
                raise AIUnavailableError(
                    retry_after=math.ceil(wait) if wait is not None else None
                )
            if status in _SERVER_ERRORS:
                log.warning("llm_server_error", status=status, attempt=attempt + 1)
                if attempt == 0:
                    await self._sleep(1.0)
                    continue
                raise AIUnavailableError()
            if status >= 400:
                raise self._client_error(response)
            try:
                payload: dict[str, Any] = response.json()
            except ValueError as exc:
                raise AppError(code="llm.malformed_response") from exc
            return payload
        raise AIUnavailableError()  # pragma: no cover - the loop always returns or raises

    @staticmethod
    def _client_error(response: httpx.Response) -> Exception:
        try:
            error = response.json().get("error") or {}
        except ValueError:
            error = {}
        if not isinstance(error, dict):
            error = {}
        if error.get("code") == "json_validate_failed":
            return _SchemaMismatch(str(error.get("failed_generation") or ""))
        # Log the provider's own message (never our request or key) for operators.
        log.error(
            "llm_request_rejected",
            status=response.status_code,
            code=error.get("code"),
            message=str(error.get("message", ""))[:300],
        )
        if response.status_code in (401, 403):
            return AppError(code="llm.auth_failed")
        return AppError(code="llm.bad_request")
