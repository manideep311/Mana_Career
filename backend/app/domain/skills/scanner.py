"""Find taxonomy skills mentioned in free text, with the lines that mention them.

Deterministic and conservative: a skill only counts when its name appears in
the text. Every hit carries the line it came from, so the UI can always show
the evidence ("Python — 'Automated weekly reporting with Python and pandas'").

Short or common-word names are the risk ("cv" means résumé, "go" is a verb,
"Express" is an English word), so:
- lowercase aliases of three characters or fewer are ignored;
- names that are ordinary words match only with their exact capitalisation;
- one-letter names (R, C) match only inside a list of other skills.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_TAXONOMY = Path(__file__).with_name("taxonomy.json")

# Skill names that are also ordinary English words: exact capitalisation only.
_CASE_SENSITIVE = frozenset(
    {"Go", "Express", "Swift", "Julia", "Ruby", "Rust", "Spark", "Flask", "Gin", "Vim", "Git"}
)
_LIST_SEPARATORS = re.compile(r"[,;/|•·]")


@dataclass(frozen=True)
class TaxonomySkill:
    slug: str
    label: str
    category: str
    aliases: tuple[str, ...] = ()


@dataclass
class SkillHit:
    slug: str
    label: str
    category: str
    lines: list[str] = field(default_factory=list)

    @property
    def mentions(self) -> int:
        return len(self.lines)


@lru_cache(maxsize=1)
def load_taxonomy() -> tuple[TaxonomySkill, ...]:
    raw = json.loads(_TAXONOMY.read_text(encoding="utf-8"))
    return tuple(
        TaxonomySkill(
            slug=e["slug"], label=e["label"], category=e["category"],
            aliases=tuple(e.get("aliases", [])),
        )
        for e in raw
    )


def _pattern(term: str, *, case_sensitive: bool) -> re.Pattern[str]:
    # Lookarounds instead of \b so names ending in symbols (C++, C#, .NET) work.
    body = re.escape(term).replace(r"\ ", r"[\s\-]+")
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<![A-Za-z0-9+#]){body}(?![A-Za-z0-9+#]|-[A-Za-z])", flags)


@dataclass(frozen=True)
class _Matcher:
    skill: TaxonomySkill
    patterns: tuple[re.Pattern[str], ...]
    single_letter: bool


@lru_cache(maxsize=4)
def _matchers(taxonomy: tuple[TaxonomySkill, ...]) -> tuple[_Matcher, ...]:
    out: list[_Matcher] = []
    for skill in taxonomy:
        terms: list[tuple[str, bool]] = []
        label_case = skill.label in _CASE_SENSITIVE or len(skill.label) <= 3
        terms.append((skill.label, label_case))
        slug_words = skill.slug.replace("-", " ")
        if slug_words.lower() != skill.label.lower() and len(slug_words) > 3:
            terms.append((slug_words, False))
        for alias in skill.aliases:
            if len(alias) <= 3 and alias == alias.lower():
                continue  # "cv", "es", "pg", "go": too ambiguous in prose
            terms.append((alias, len(alias) <= 3))
        seen: set[tuple[str, bool]] = set()
        patterns: list[re.Pattern[str]] = []
        for term, cs in terms:
            key = (term if cs else term.lower(), cs)
            if key not in seen:
                seen.add(key)
                patterns.append(_pattern(term, case_sensitive=cs))
        out.append(
            _Matcher(skill=skill, patterns=tuple(patterns), single_letter=len(skill.label) == 1)
        )
    return tuple(out)


def scan_lines(
    lines: Iterable[str], taxonomy: Sequence[TaxonomySkill] | None = None
) -> dict[str, SkillHit]:
    """Map skill slug -> hit (with every line that mentions it), in slug order."""
    tax = tuple(taxonomy) if taxonomy is not None else load_taxonomy()
    matchers = _matchers(tax)
    hits: dict[str, SkillHit] = {}
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        found: list[_Matcher] = []
        for m in matchers:
            if any(p.search(line) for p in m.patterns):
                found.append(m)
        # A lone "R" or "C" is only a skill inside a list of other skills.
        multi = [m for m in found if not m.single_letter]
        for m in found:
            if m.single_letter and not (multi and _LIST_SEPARATORS.search(line)):
                continue
            hit = hits.setdefault(
                m.skill.slug, SkillHit(m.skill.slug, m.skill.label, m.skill.category)
            )
            if line not in hit.lines:
                hit.lines.append(line)
    return dict(sorted(hits.items()))


def scan_text(text: str, taxonomy: Sequence[TaxonomySkill] | None = None) -> dict[str, SkillHit]:
    return scan_lines(text.splitlines(), taxonomy)


def labels_to_slugs(labels: Iterable[str]) -> dict[str, str]:
    """Resolve skill names (e.g. a job's tech list) to slugs via the scanner."""
    out: dict[str, str] = {}
    for label in labels:
        hits = scan_lines([label])
        if hits:
            out[label] = next(iter(hits))
    return out
