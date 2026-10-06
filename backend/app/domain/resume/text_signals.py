"""What a résumé's own text says, found without an AI model.

After extraction, this fills the gaps the extractor left. It matters most in
demo mode, which runs without a model and gets nothing back:

- skills: the shared skills catalogue's entries whose name (or alias) appears in
  the text, so career paths and matching work straight after an upload;
- an email address and GitHub / LinkedIn profile links written in the text.

Nothing is inferred: every value appears verbatim in the résumé. Skill names
that are also ordinary words only count with the catalogue's capitalisation
(``Go``, ``Swift``, ``Snowflake``), and a few that are too ambiguous to find
reliably in prose ("Make", "rest", "CV") are never matched.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.domain.resume.extractor import ResumeExtraction

_TAXONOMY = Path(__file__).resolve().parents[1] / "skills" / "taxonomy.json"

# Ordinary words that are also catalogue entries: matched only when written
# with the catalogue's capitalisation, e.g. "Go" but not "go".
_CASE_SENSITIVE = frozenset({
    "go", "r", "rust", "swift", "julia", "ruby", "express", "gin", "jest", "mocha",
    "prefect", "polars", "bootstrap", "playwright", "snowflake", "pinecone",
    "poetry", "agile", "angular", "helm", "storybook", "postman", "prisma",
})

# Too ambiguous in prose to count without a model, even capitalised.
_NEVER = frozenset({
    "make", "black", "fiber", "chroma", "remix", "astro", "spring", "rest",
    "actions", "architecture", "security", "optimization", "evaluation",
    "collaboration", "coaching", "lambda", "elastic", "node", "docs", "cv", "dl",
    "rl", "es", "tf", "pg", "sh", "ts", "uv", "asp",
})

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_GITHUB = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?![A-Za-z0-9-])",
    re.IGNORECASE,
)
_LINKEDIN = re.compile(
    r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9_-]{3,100})", re.IGNORECASE
)


def _pattern(term: str, *, case_sensitive: bool) -> re.Pattern[str]:
    # A term must stand on its own, not inside a longer word or name ("Java" in
    # "JavaScript", "SQL" in "MySQL", "js" in "node.js"); "Python/Django",
    # "React-based" and a sentence-ending full stop are fine, and so is a
    # ".js" suffix ("Express.js"). Ordinary-word names are stricter, so that
    # "Go-to-market" and "R&D" aren't mentions of Go or R.
    if case_sensitive:
        before = r"(?<![A-Za-z0-9+#._/-])"
        after = r"(?![A-Za-z0-9+#_&'/-]|\.[A-Za-z0-9])"
    else:
        before = r"(?<![A-Za-z0-9+#.])"
        after = r"(?![A-Za-z0-9+#]|\.[A-Za-z0-9])"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(before + re.escape(term) + r"(?:\.js)?" + after, flags)


# A capitalised ordinary word that opens a sentence and runs on into prose
# ("Swift turnaround on...", "Go fast") is the word, not the tool.
_SENTENCE_START = re.compile(r"(?:^|[.!?]\s+|\n\s*)$")
_PROSE_FOLLOWS = re.compile(r"\s+[a-z]")

_Patterns = tuple[tuple[re.Pattern[str], bool], ...]


def _reads_as_prose(text: str, match: re.Match[str]) -> bool:
    return bool(
        _SENTENCE_START.search(text, 0, match.start())
        and _PROSE_FOLLOWS.match(text, match.end())
    )


@lru_cache(maxsize=1)
def _catalogue() -> tuple[tuple[str, _Patterns], ...]:
    """(label, ((pattern, is_ordinary_word), ...)) per catalogue entry."""
    entries = json.loads(_TAXONOMY.read_text(encoding="utf-8"))
    out: list[tuple[str, _Patterns]] = []
    for entry in entries:
        label: str = entry["label"]
        patterns: list[tuple[re.Pattern[str], bool]] = []
        for term in dict.fromkeys([label, *entry.get("aliases", [])]):
            key = term.strip().lower()
            if not key or key in _NEVER:
                continue
            if key in _CASE_SENSITIVE:
                # Only the catalogue's own spelling counts (its label casing).
                if term != label:
                    continue
                patterns.append((_pattern(term, case_sensitive=True), True))
            else:
                patterns.append((_pattern(term, case_sensitive=False), False))
        if patterns:
            out.append((label, tuple(patterns)))
    return tuple(out)


def skills_named_in(text: str) -> list[str]:
    """Catalogue skills the text names, in the order they first appear."""
    found: list[tuple[int, str]] = []
    for label, patterns in _catalogue():
        hits = [
            m.start()
            for pattern, ordinary_word in patterns
            for m in pattern.finditer(text)
            if not (ordinary_word and _reads_as_prose(text, m))
        ]
        if hits:
            found.append((min(hits), label))
    return [label for _, label in sorted(found)]


def _email_in(text: str) -> str | None:
    m = _EMAIL.search(text)
    return m.group(0) if m else None


def _github_in(text: str) -> str | None:
    m = _GITHUB.search(text)
    return f"https://github.com/{m.group(1)}" if m else None


def _linkedin_in(text: str) -> str | None:
    m = _LINKEDIN.search(text)
    return f"https://www.linkedin.com/in/{m.group(1)}" if m else None


def complete_from_text(extraction: ResumeExtraction, text: str) -> ResumeExtraction:
    """The extraction with empty fields filled from what the text itself says.

    Fields the extractor already filled are left exactly as they are."""
    updates: dict[str, object] = {}
    if not extraction.skills:
        skills = skills_named_in(text)
        if skills:
            updates["skills"] = skills
    if not extraction.email and (email := _email_in(text)):
        updates["email"] = email
    if not extraction.github_url and (github := _github_in(text)):
        updates["github_url"] = github
    if not extraction.linkedin_url and (linkedin := _linkedin_in(text)):
        updates["linkedin_url"] = linkedin
    return extraction.model_copy(update=updates) if updates else extraction
