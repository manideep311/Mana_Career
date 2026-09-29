"""Deterministic résumé review: what's strong, what's missing, what to change.

Works on the extracted text alone (no model), so it is fast, repeatable and
available in every deployment. Every finding is grounded in the user's own
lines, and suggestions never propose content the résumé doesn't support: a
missing keyword is either "add the evidence if you have it" or a skill gap.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.domain.skills.scanner import scan_lines

Severity = Literal["high", "medium", "low"]
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

SECTIONS = ("contact", "summary", "experience", "education", "skills", "projects", "certifications")

_HEADERS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "profile", "professional summary", "about", "about me", "objective",
                "career objective", "professional profile"),
    "experience": ("experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history", "relevant experience"),
    "education": ("education", "academic background", "qualifications", "education and training"),
    "skills": ("skills", "technical skills", "core skills", "key skills", "competencies",
               "technologies", "tech stack", "tools", "skills and tools"),
    "projects": ("projects", "personal projects", "selected projects", "side projects",
                 "portfolio", "key projects"),
    "certifications": ("certifications", "certificates", "licenses", "licenses and certifications",
                       "licenses & certifications", "courses", "training"),
}
_HEADER_LOOKUP = {alias: name for name, aliases in _HEADERS.items() for alias in aliases}

# Bullet glyphs as pypdf/PDFium return them: bullet, hyphen, en/em dash, star,
# small square, black circle, white bullet, triangular bullet, middle dot.
_EN_DASH, _EM_DASH, _TIMES = chr(0x2013), chr(0x2014), chr(0x00D7)
_BULLET_GLYPHS = "".join(
    chr(c) for c in (0x2022, 0x2D, 0x2013, 0x2014, 0x2A, 0x25AA, 0x25CF, 0x25E6, 0x2023, 0xB7)
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_DASHES = f"-{_EN_DASH}{_EM_DASH}"
_DATE_RANGE = re.compile(
    rf"\b(19|20)\d{{2}}\s*(?:[{_DASHES}]|to)\s*(?:(19|20)\d{{2}}|present|current|now)\b", re.I
)
_METRIC = re.compile(
    rf"(\d[\d,.]*\s?%|[$€£₹]\s?\d|\b\d[\d,.]*\s?(?:x|{_TIMES}|k|m|bn|million|thousand|hours?|hrs|"
    r"days?|weeks?|months?|users|customers|clients|people|engineers|requests|ms|seconds|"
    r"minutes)\b|\b\d{2,}[\d,]*\b)",
    re.I,
)
_WEAK_OPENINGS = ("responsible for", "worked on", "helped", "assisted", "involved in",
                  "duties included", "tasked with", "participated in", "handled", "in charge of")
_STRONG_VERBS = frozenset(
    "led built designed developed launched improved reduced increased automated created delivered "
    "analyzed analysed managed implemented optimized optimised migrated shipped drove owned "
    "mentored architected scaled cut grew saved streamlined resolved established introduced "
    "negotiated trained coordinated wrote produced redesigned modernized modernised deployed "
    "integrated accelerated achieved won secured presented researched".split()
)


@dataclass(frozen=True)
class AnalysisIssue:
    id: str
    severity: Severity
    area: str
    problem: str
    why_it_matters: str
    suggestion: str
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillEvidence:
    slug: str
    label: str
    category: str
    applied: bool  # shown in an experience/project line, not only listed
    lines: tuple[str, ...]


@dataclass(frozen=True)
class TargetSpec:
    title: str
    skills: tuple[tuple[str, str], ...]  # (slug, label), most important first


@dataclass(frozen=True)
class RoleAlignment:
    target: str
    evidenced: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def coverage(self) -> float:
        total = len(self.evidenced) + len(self.missing)
        return len(self.evidenced) / total if total else 0.0


@dataclass(frozen=True)
class ResumeAnalysis:
    sections: dict[str, bool]
    word_count: int
    page_count: int | None
    bullet_count: int
    bullets_with_results: int
    strengths: tuple[str, ...]
    issues: tuple[AnalysisIssue, ...]
    skills: tuple[SkillEvidence, ...]
    alignment: RoleAlignment | None
    enough_text: bool = True


@dataclass
class _Line:
    text: str
    section: str | None
    is_bullet: bool = False


@dataclass
class _Parsed:
    lines: list[_Line] = field(default_factory=list)
    sections: set[str] = field(default_factory=set)


def _header_of(line: str) -> str | None:
    cleaned = line.strip().strip(":").strip()
    lowered = re.sub(r"\s+", " ", cleaned.lower())
    if len(lowered.split()) > 5:
        # "Skills: Python, SQL" — a header with inline content.
        head = lowered.split(":", 1)[0].strip() if ":" in lowered else ""
        return _HEADER_LOOKUP.get(head)
    if lowered in _HEADER_LOOKUP:
        return _HEADER_LOOKUP[lowered]
    head = lowered.split(":", 1)[0].strip() if ":" in lowered else ""
    return _HEADER_LOOKUP.get(head)


def _is_title_line(text: str) -> bool:
    """A role/employer/date line rather than an achievement."""
    return bool(_DATE_RANGE.search(text)) or len(text.split()) <= 5


def _parse(text: str) -> _Parsed:
    parsed = _Parsed()
    section: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        header = _header_of(line)
        if header is not None:
            section = header
            parsed.sections.add(header)
            inline = line.split(":", 1)[1].strip() if ":" in line else ""
            if inline:
                parsed.lines.append(_Line(inline, section))
            continue
        glyph = line[0] in _BULLET_GLYPHS and len(line) > 1
        body = line[1:].strip() if glyph else line
        is_bullet = glyph or (
            section in ("experience", "projects")
            and not _is_title_line(body)
            and len(body.split()) >= 6
        )
        parsed.lines.append(_Line(body, section, is_bullet))
    return parsed


def _has_phone(text: str) -> bool:
    """A 9-15 digit number that isn't a date range like '2019 - 2021'."""
    for m in _PHONE.finditer(text):
        candidate = m.group(1)
        digits = sum(ch.isdigit() for ch in candidate)
        if 9 <= digits <= 15 and not _DATE_RANGE.search(candidate) and not _YEAR.fullmatch(
            candidate.strip()
        ):
            return True
    return False


def _has_metric(text: str) -> bool:
    return bool(_METRIC.search(_YEAR.sub("", text)))


def _first_word(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.split()[0].lower()) if text.split() else ""


def analyze_resume(
    text: str, *, page_count: int | None = None, target: TargetSpec | None = None
) -> ResumeAnalysis:
    words = len(text.split())
    if words < 40:
        return ResumeAnalysis(
            sections=dict.fromkeys(SECTIONS, False), word_count=words, page_count=page_count,
            bullet_count=0, bullets_with_results=0, strengths=(), skills=(), alignment=None,
            enough_text=False,
            issues=(AnalysisIssue(
                id="not_enough_text", severity="high", area="structure",
                problem="We could read very little text from this file.",
                why_it_matters="Without the text we can't find your experience, skills or results.",
                suggestion=(
                    "Upload a text-based PDF (exported from Word or Google Docs), not a scan."
                ),
            ),),
        )

    parsed = _parse(text)
    sections = {name: name in parsed.sections for name in SECTIONS}
    sections["contact"] = bool(_EMAIL.search(text)) or _has_phone(text)

    bullets = [line for line in parsed.lines if line.is_bullet]
    with_results = [b for b in bullets if _has_metric(b.text)]
    weak = [b for b in bullets if b.text.lower().startswith(_WEAK_OPENINGS)]
    long_bullets = [b for b in bullets if len(b.text.split()) > 38]

    hits = scan_lines(line.text for line in parsed.lines)
    applied_lines = {
        line.text for line in parsed.lines if line.section in ("experience", "projects")
    }
    skills = tuple(
        SkillEvidence(
            slug=h.slug, label=h.label, category=h.category,
            applied=any(line in applied_lines for line in h.lines),
            lines=tuple(h.lines[:3]),
        )
        for h in hits.values()
    )

    alignment = None
    if target and target.skills:
        found = {s.slug for s in skills}
        alignment = RoleAlignment(
            target=target.title,
            evidenced=tuple(label for slug, label in target.skills if slug in found),
            missing=tuple(label for slug, label in target.skills if slug not in found),
        )

    issues = _issues(
        sections=sections, bullets=bullets, with_results=with_results, weak=weak,
        long_bullets=long_bullets, skills=skills, alignment=alignment, text=text,
        words=words, page_count=page_count,
    )
    strengths = _strengths(
        sections=sections, bullets=bullets, with_results=with_results, skills=skills,
        alignment=alignment,
    )
    return ResumeAnalysis(
        sections=sections, word_count=words, page_count=page_count,
        bullet_count=len(bullets), bullets_with_results=len(with_results),
        strengths=strengths, issues=issues, skills=skills, alignment=alignment,
    )


def _examples(lines: Sequence[_Line], n: int = 2) -> tuple[str, ...]:
    return tuple(line.text for line in lines[:n])


def _issues(
    *,
    sections: dict[str, bool],
    bullets: list[_Line],
    with_results: list[_Line],
    weak: list[_Line],
    long_bullets: list[_Line],
    skills: tuple[SkillEvidence, ...],
    alignment: RoleAlignment | None,
    text: str,
    words: int,
    page_count: int | None,
) -> tuple[AnalysisIssue, ...]:
    out: list[AnalysisIssue] = []

    if not sections["contact"]:
        out.append(AnalysisIssue(
            "missing_contact", "high", "contact",
            "We couldn't find an email address or phone number.",
            "A recruiter who likes your résumé needs a way to reach you.",
            "Add your email (and a phone number if you're comfortable) at the top.",
        ))
    if not sections["experience"] and not bullets:
        out.append(AnalysisIssue(
            "missing_experience", "high", "structure",
            "There's no clear experience section.",
            "Reviewers look for what you did and where first; without it they move on.",
            "Add an Experience section listing roles, dates and 2-4 achievement lines each. "
            "Internships, freelance work and substantial projects count.",
        ))

    if bullets:
        share = len(with_results) / len(bullets)
        missing_results = [b for b in bullets if b not in with_results]
        if share < 0.3:
            out.append(AnalysisIssue(
                "few_results", "high", "impact",
                f"Only {len(with_results)} of {len(bullets)} achievement lines show a "
                "measurable result.",
                "Numbers (time saved, users reached, errors reduced) are what make an "
                "achievement credible and memorable.",
                "For each line, add the outcome you actually observed: how much, how many, "
                "how fast. If you don't know an exact figure, describe the scale "
                "(e.g. 'for a team of 12'). Don't estimate numbers you can't stand behind.",
                _examples(missing_results),
            ))
        elif share < 0.6:
            out.append(AnalysisIssue(
                "some_results", "medium", "impact",
                f"{len(with_results)} of {len(bullets)} achievement lines show a result; "
                "the rest describe tasks.",
                "Results turn duties into evidence of what you can do for the next team.",
                "Pick your strongest remaining lines and add the outcome you observed.",
                _examples(missing_results),
            ))
        if weak:
            out.append(AnalysisIssue(
                "weak_openings", "medium", "impact",
                f"{len(weak)} line(s) start with phrases like 'responsible for' or 'helped'.",
                "They describe a role, not what you did, and they read as passive.",
                "Start with the action you took: 'Built…', 'Reduced…', 'Led…'.",
                _examples(weak),
            ))
        if long_bullets:
            out.append(AnalysisIssue(
                "long_lines", "low", "formatting",
                f"{len(long_bullets)} achievement line(s) run past about 38 words.",
                "Reviewers skim; long lines hide the result.",
                "Split them, or keep one action and one result per line.",
                _examples(long_bullets, 1),
            ))
    elif sections["experience"]:
        out.append(AnalysisIssue(
            "no_achievements", "high", "impact",
            "Your experience section doesn't list achievements.",
            "Titles and dates alone don't show what you can do.",
            "Under each role, add 2-4 lines describing what you did and what changed as a result.",
        ))

    listed_only = [s for s in skills if not s.applied]
    if sections["skills"] and len(listed_only) >= 3 and len(listed_only) > len(skills) / 2:
        out.append(AnalysisIssue(
            "skills_without_evidence", "medium", "skills",
            f"{len(listed_only)} skills appear only in your skills list, e.g. "
            f"{', '.join(s.label for s in listed_only[:4])}.",
            "A list tells reviewers what you claim; a project or role line shows it.",
            "For the skills that matter most for your target, name where you used them in "
            "one achievement line each.",
        ))
    if not sections["skills"] and skills:
        out.append(AnalysisIssue(
            "missing_skills_section", "low", "structure",
            "There's no dedicated skills section.",
            "Many screening tools and reviewers look for one to scan quickly.",
            f"Add a short skills line with the tools you've actually used, such as "
            f"{', '.join(s.label for s in skills[:4])}.",
        ))

    if alignment and alignment.missing:
        severity: Severity = "high" if alignment.coverage < 0.5 else "medium"
        out.append(AnalysisIssue(
            "target_keywords_missing", severity, "alignment",
            f"{len(alignment.missing)} skills {alignment.target} roles often ask for aren't on "
            f"your résumé: {', '.join(alignment.missing[:5])}.",
            "Recruiters and screening tools look for these words; if you have the experience "
            "but it isn't written down, it won't count.",
            "If you've used any of them, add a line showing where. If you haven't, they're "
            "skill gaps, not wording problems: see your roadmap rather than adding them here.",
        ))

    if not sections["summary"] and sections["experience"]:
        out.append(AnalysisIssue(
            "missing_summary", "low", "structure",
            "There's no short summary at the top.",
            "Two lines on who you are and what you're aiming for frame everything below.",
            "Write two sentences from your real experience: your focus and the kind of role "
            "you want next.",
        ))
    if sections["experience"] and not _YEAR.search(text):
        out.append(AnalysisIssue(
            "missing_dates", "medium", "formatting",
            "We couldn't find dates for your roles.",
            "Reviewers use dates to understand your experience level and recency.",
            "Add start and end years (or 'Present') to each role.",
        ))
    if (page_count and page_count > 2) or words > 1300:
        out.append(AnalysisIssue(
            "too_long", "medium", "formatting",
            f"The résumé is {page_count or '?'} pages / about {words} words.",
            "Most reviewers read the first page closely and skim the rest.",
            "Aim for one page (two if you have many years of directly relevant work). "
            "Cut the oldest or least relevant lines first.",
        ))
    elif words < 180:
        out.append(AnalysisIssue(
            "too_short", "low", "structure",
            f"The résumé is short (about {words} words).",
            "There may not be enough to show your range.",
            "Add projects, coursework or volunteering that show relevant skills, if you have them.",
        ))

    return tuple(sorted(out, key=lambda i: _SEVERITY_ORDER[i.severity]))


def _strengths(
    *,
    sections: dict[str, bool],
    bullets: list[_Line],
    with_results: list[_Line],
    skills: tuple[SkillEvidence, ...],
    alignment: RoleAlignment | None,
) -> tuple[str, ...]:
    out: list[str] = []
    if bullets and len(with_results) / len(bullets) >= 0.5:
        out.append(
            f"{len(with_results)} of {len(bullets)} achievement lines show a measurable result."
        )
    applied = [s for s in skills if s.applied]
    if len(applied) >= 3:
        out.append(
            f"You show skills in action, not just in a list: "
            f"{', '.join(s.label for s in applied[:5])}."
        )
    strong_starts = [b for b in bullets if _first_word(b.text) in _STRONG_VERBS]
    if bullets and len(strong_starts) / len(bullets) >= 0.6:
        out.append("Most achievement lines open with a clear action.")
    core = ("experience", "education", "skills")
    if all(sections[s] for s in core) and sections["contact"]:
        out.append("The core sections are all there: contact, experience, education and skills.")
    if alignment and alignment.coverage >= 0.6:
        out.append(
            f"Your résumé already evidences {len(alignment.evidenced)} of "
            f"{len(alignment.evidenced) + len(alignment.missing)} skills "
            f"{alignment.target} roles ask for most."
        )
    return tuple(out)
