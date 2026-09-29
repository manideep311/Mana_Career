"""Group job titles into role families ("Senior Backend Engineer, Payments" ->
Backend Engineer) so career paths compare like with like.

Known families come from explicit keyword rules (ordered: the first match wins,
so "Machine Learning Platform Engineer" is MLOps, not ML Engineer). Anything
else falls back to the title with seniority words and specialisations removed,
so user-added roles ("Senior Data Analyst") still group sensibly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Family:
    slug: str
    title: str
    summary: str


_RULES: tuple[tuple[Family, tuple[str, ...]], ...] = (
    (Family("engineering-manager", "Engineering Manager",
            "Lead a team: hiring, delivery, technical direction and people growth."),
     ("engineering manager", "engineering lead", "head of engineering", "director of engineering")),
    (Family("mlops-engineer", "MLOps Engineer",
            "Build the platforms that train, deploy and monitor models in production."),
     ("mlops", "machine learning platform", "ml platform", "ml infrastructure")),
    (Family("machine-learning-engineer", "Machine Learning Engineer",
            "Turn models into reliable product features, from data to deployment."),
     ("machine learning engineer", "ml engineer", "ai engineer")),
    (Family("research-scientist", "Research Scientist",
            "Invent and evaluate new methods, often publishing or prototyping."),
     ("research scientist", "applied scientist", "research engineer", "applied research")),
    (Family("data-scientist", "Data Scientist",
            "Use statistics and modelling to answer business questions and guide decisions."),
     ("data scientist", "data science")),
    (Family("data-engineer", "Data Engineer",
            "Build the pipelines and stores that make data reliable and usable."),
     ("data engineer", "analytics engineer", "etl engineer")),
    (Family("data-analyst", "Data Analyst",
            "Turn data into reports, dashboards and recommendations people act on."),
     ("data analyst", "business analyst", "bi analyst", "analytics analyst", "reporting analyst")),
    (Family("full-stack-engineer", "Full-Stack Engineer",
            "Build features end to end, from the interface to the database."),
     ("full-stack", "full stack", "fullstack")),
    (Family("frontend-engineer", "Frontend Engineer",
            "Build the interfaces people use: accessible, fast and well designed."),
     ("frontend", "front-end", "front end", "ui engineer")),
    (Family("backend-engineer", "Backend Engineer",
            "Build the APIs, services and data models products run on."),
     ("backend", "back-end", "back end", "api engineer", "server engineer")),
    (Family("platform-engineer", "Platform Engineer",
            "Run the infrastructure, tooling and reliability practices teams build on."),
     ("platform engineer", "infrastructure", "site reliability", "sre", "devops",
      "cloud engineer")),
)

_SENIORITY = re.compile(
    r"\b(senior|sr|junior|jr|staff|principal|lead|head|chief|intern|internship|associate|"
    r"entry[- ]level|graduate|trainee|i{1,3}|iv)\b\.?",
    re.I,
)


_EN_DASH = chr(0x2013)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def family_for(title: str | None) -> Family:
    raw = (title or "").strip()
    lowered = raw.lower()
    for family, keywords in _RULES:
        if any(k in lowered for k in keywords):
            return family
    # Split off a specialisation after a comma, bracket, pipe or spaced dash.
    base = re.split(f"[,(|]| - | {_EN_DASH} ", raw, maxsplit=1)[0]
    base = _SENIORITY.sub(" ", base)
    base = re.sub(r"\s+", " ", base).strip(f" -{_EN_DASH}") or raw or "Other roles"
    label = base if base != base.lower() else base.title()
    return Family(_slugify(label) or "other-roles", label, "")


def family_by_slug(slug: str) -> Family | None:
    for family, _ in _RULES:
        if family.slug == slug:
            return family
    return None
