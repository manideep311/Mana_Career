from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any

from app.domain.generation.service import GenerationService
from app.domain.generation.types import GenerationMeta
from app.domain.resume.extractor import ResumeExtraction

_MIN_SUPPORT = 0.60  # token-overlap ratio threshold

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
        "at", "by", "from", "as", "is", "are", "was", "were", "be", "been",
        "being", "this", "that", "these", "those", "i", "we", "you", "they",
        "it", "he", "she", "his", "her", "its", "their", "our", "your", "my",
        "but", "not", "no", "so", "if", "then", "than", "into", "over",
        "under", "up", "down", "out", "about", "also", "using", "via",
    }
)

MAX_CLAIM_REPROMPTS = 2

_TAILOR_SYSTEM = (
    "You rewrite a candidate's résumé to fit a specific job. You may re-order, "
    "re-emphasise, and re-word existing achievements and skills. You must NOT "
    "invent employers, titles, dates, metrics, technologies, or accomplishments "
    "that are not already present in the provided base résumé and profile. Keep "
    "every bullet grounded in the source material. Return the full structured résumé."
)
_TAILOR_PROMPT_VERSION = "tailor-1"

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


@dataclass(frozen=True)
class ClaimReport:
    checked: int
    unsupported: list[str]
    supported_ratio: float
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "unsupported": self.unsupported,
            "supported_ratio": self.supported_ratio,
            "passed": self.passed,
        }


def _split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


class ClaimValidator:
    def __init__(self, sources: list[str]) -> None:
        self._source_tokens = [self._norm(s) for s in sources if s.strip()]

    @staticmethod
    def _norm(s: str) -> frozenset[str]:
        lowered = s.lower()
        stripped = _PUNCT_RE.sub(" ", lowered)
        tokens = stripped.split()
        return frozenset(t for t in tokens if t not in _STOPWORDS)

    def _supported(self, claim: str) -> bool:
        ct = self._norm(claim)
        if not ct:
            return True
        best = max(
            (len(ct & st) / len(ct) for st in self._source_tokens), default=0.0
        )
        return best >= _MIN_SUPPORT

    def check(self, tailored: ResumeExtraction) -> ClaimReport:
        claim_lines: list[str] = []
        for exp in tailored.experiences:
            claim_lines.extend(exp.highlights)
            if exp.description and exp.description.strip():
                claim_lines.extend(_split_sentences(exp.description))
        for proj in tailored.projects:
            claim_lines.extend(proj.highlights)
            if proj.description and proj.description.strip():
                claim_lines.extend(_split_sentences(proj.description))
        if tailored.summary and tailored.summary.strip():
            claim_lines.extend(_split_sentences(tailored.summary))

        checked = 0
        unsupported: list[str] = []
        for line in claim_lines:
            if not line.strip():
                continue
            checked += 1
            if not self._supported(line):
                unsupported.append(line)

        supported_ratio = (
            (checked - len(unsupported)) / checked if checked else 1.0
        )
        return ClaimReport(
            checked=checked,
            unsupported=unsupported,
            supported_ratio=supported_ratio,
            passed=not unsupported,
        )


def _collect_sources(base: ResumeExtraction, profile_summary: str) -> list[str]:
    sources: list[str] = []

    def _add(*values: str | None) -> None:
        for v in values:
            if v and v.strip():
                sources.append(v)

    _add(base.summary)
    for exp in base.experiences:
        _add(exp.description, exp.title, exp.company)
        sources.extend(h for h in exp.highlights if h and h.strip())
        sources.extend(t for t in exp.tech if t and t.strip())
    for proj in base.projects:
        _add(proj.description, proj.name)
        sources.extend(h for h in proj.highlights if h and h.strip())
        sources.extend(t for t in proj.tech if t and t.strip())
    for edu in base.education:
        _add(edu.institution, edu.degree, edu.field)
    for cert in base.certifications:
        _add(cert.name, cert.issuer)
    sources.extend(s for s in base.skills if s and s.strip())
    if profile_summary and profile_summary.strip():
        sources.extend(_split_sentences(profile_summary))

    return sources


def _render_prompt(
    base: ResumeExtraction,
    profile_summary: str,
    job_brief: str,
    rejected: list[str] | None,
) -> str:
    base_json = json.dumps(base.model_dump(mode="json"), indent=2)
    parts = [
        f"Base résumé (JSON):\n{base_json}",
        f"Candidate profile summary:\n{profile_summary}",
        f"Target job:\n{job_brief}",
    ]
    if rejected:
        rejected_lines = "\n".join(f"- {line}" for line in rejected)
        parts.append(
            "The following lines were not grounded in the source material; "
            f"rewrite or drop them:\n{rejected_lines}"
        )
    return "\n\n".join(parts)


async def tailor_resume(
    *,
    gen: GenerationService,
    base: ResumeExtraction,
    profile_summary: str,
    job_brief: str,
) -> tuple[ResumeExtraction, GenerationMeta]:
    sources = _collect_sources(base, profile_summary)
    validator = ClaimValidator(sources)
    user = _render_prompt(base, profile_summary, job_brief, rejected=None)
    for attempt in range(MAX_CLAIM_REPROMPTS + 1):
        res = await gen.generate(
            system=_TAILOR_SYSTEM,
            user=user,
            schema=ResumeExtraction,
            prompt_version=_TAILOR_PROMPT_VERSION,
            max_tokens=1600,
        )
        tailored = ResumeExtraction.model_validate(res.structured)
        report = validator.check(tailored)
        meta = replace(res.meta, claim_validation=report.as_dict())
        if report.passed or attempt == MAX_CLAIM_REPROMPTS:
            return tailored, meta
        user = _render_prompt(base, profile_summary, job_brief, rejected=report.unsupported)
    raise AssertionError("unreachable")
