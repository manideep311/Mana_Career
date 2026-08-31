from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

from pydantic import BaseModel


class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMCapabilities:
    structured_output: bool
    tools: bool
    streaming: bool


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    structured: dict[str, Any] | None = None


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult: ...

    def capabilities(self) -> LLMCapabilities: ...
