from __future__ import annotations

import hashlib

from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.domain.generation.types import GenerationMeta, GenerationResult
from app.domain.llm.provider import LLMMessage, LLMProvider

PROMPT_VERSION = "gen-1"


class GenerationError(Exception):
    """A model call produced no usable structured payload."""


class GenerationService:
    def __init__(self, llm: LLMProvider, *, settings: Settings | None = None) -> None:
        self._llm = llm
        self._settings = settings or get_settings()

    async def generate(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        prompt_version: str,
        max_tokens: int = 1200,
    ) -> GenerationResult:
        messages: list[LLMMessage] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        prompt_hash = hashlib.sha256(
            f"{prompt_version}\n{system}\n{user}".encode()
        ).hexdigest()
        res = await self._llm.complete(messages, schema=schema, max_tokens=max_tokens)
        if res.structured is None:
            raise GenerationError("model returned no structured payload")
        try:
            validated = schema.model_validate(res.structured)
        except ValidationError as exc:  # pragma: no cover - defensive
            raise GenerationError(f"structured payload failed schema: {exc}") from exc
        meta = GenerationMeta(
            model=res.model,
            provider=type(self._llm).__name__,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            cost_usd=res.cost_usd,
            claim_validation={},
        )
        return GenerationResult(
            structured=validated.model_dump(mode="json"), text=res.text or "", meta=meta
        )
