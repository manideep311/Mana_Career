from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenerationMeta:
    model: str
    provider: str
    prompt_version: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    claim_validation: dict[str, Any]


@dataclass(frozen=True)
class GenerationResult:
    structured: dict[str, Any]
    text: str
    meta: GenerationMeta
