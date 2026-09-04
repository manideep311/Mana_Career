from __future__ import annotations

import hashlib

from app.domain.agents.search.provider import SearchHit

_CANNED: list[SearchHit] = [
    {
        "url": "https://example.com/acme-robotics",
        "title": "Acme Robotics - Company Overview",
        "content": (
            "Acme Robotics builds warehouse automation systems for mid-size logistics "
            "operators. The company is headquartered in a fictional tech corridor and "
            "employs roughly 400 people."
        ),
    },
    {
        "url": "https://example.com/acme-robotics/products",
        "title": "Acme Robotics Perception Stack",
        "content": (
            "The flagship product is a camera-and-lidar perception module that lets "
            "autonomous forklifts navigate crowded aisles. It ships as a bundled "
            "hardware and software subscription."
        ),
    },
    {
        "url": "https://example.org/news/acme-robotics-series-c",
        "title": "Acme Robotics raises a Series C round",
        "content": (
            "In a hypothetical funding announcement, Acme Robotics closed a Series C led "
            "by a placeholder growth fund, bringing total capital raised to a nominal "
            "nine figures."
        ),
    },
    {
        "url": "https://example.com/globex-analytics",
        "title": "Globex Analytics - What We Do",
        "content": (
            "Globex Analytics sells a self-serve business intelligence platform aimed at "
            "finance teams. Its differentiator is a natural-language query layer over "
            "warehouse data."
        ),
    },
    {
        "url": "https://example.org/profiles/initech-security",
        "title": "Initech Security Profile",
        "content": (
            "Initech Security is a fictional managed detection and response vendor that "
            "focuses on small and medium businesses. It operates a 24/7 analyst team and "
            "a lightweight endpoint agent."
        ),
    },
    {
        "url": "https://example.com/umbrella-bio",
        "title": "Umbrella Bio - About",
        "content": (
            "Umbrella Bio is an invented contract research organisation running "
            "preclinical assays for biotech startups. The company markets fast turnaround "
            "times and transparent per-study pricing."
        ),
    },
]


class FakeSearchProvider:
    """Deterministic offline search: same query -> same hits, never hits the network."""

    async def search(self, query: str, *, k: int = 5) -> list[SearchHit]:
        idx = int.from_bytes(hashlib.sha256(query.encode()).digest()[:4], "big")
        return [_CANNED[(idx + i) % len(_CANNED)] for i in range(min(k, 3))]
