import re

from app.domain.skills.normalizer import SkillNormalizer
from app.seed import load_taxonomy

_CATEGORIES = {
    "language", "ml_framework", "ml_technique", "data", "cloud", "devops",
    "backend", "frontend", "database", "tooling", "practice",
}
_SLUG = re.compile(r"^[a-z0-9+#.-]+$")


async def test_taxonomy_is_well_formed():
    entries = await load_taxonomy()
    assert 150 <= len(entries) <= 260
    slugs = [e["slug"] for e in entries]
    assert len(slugs) == len(set(slugs)), "slugs must be unique"
    for e in entries:
        assert set(e) >= {"slug", "label", "category", "aliases"}
        assert _SLUG.match(e["slug"]), e["slug"]
        assert e["category"] in _CATEGORIES, e
        assert isinstance(e["aliases"], list)
        assert e["label"].strip()


async def test_aliases_are_globally_unambiguous():
    """Every normalised alias resolves to exactly one skill.

    Guards the two failure modes that make ``SkillNormalizer.load()``
    non-deterministic: an alias that shadows another entry's slug, and one
    alias claimed by two different slugs.
    """
    entries = await load_taxonomy()
    norm = SkillNormalizer._norm
    slug_norms = {norm(e["slug"]): e["slug"] for e in entries}

    alias_owners: dict[str, set[str]] = {}
    for e in entries:
        for alias in e["aliases"]:
            nalias = norm(alias)
            # 1. no normalised alias equals another entry's normalised slug
            assert nalias not in slug_norms or slug_norms[nalias] == e["slug"], (
                f"alias {alias!r} on {e['slug']!r} collides with slug "
                f"{slug_norms.get(nalias)!r}"
            )
            alias_owners.setdefault(nalias, set()).add(e["slug"])

    # 2. no normalised alias appears under two different slugs
    ambiguous = {a: sorted(s) for a, s in alias_owners.items() if len(s) > 1}
    assert not ambiguous, f"aliases claimed by multiple slugs: {ambiguous}"


async def test_core_ml_skills_present():
    slugs = {e["slug"] for e in await load_taxonomy()}
    for expected in {"python", "pytorch", "tensorflow", "scikit-learn", "fastapi",
                     "docker", "kubernetes", "postgresql", "react", "langchain"}:
        assert expected in slugs, expected
