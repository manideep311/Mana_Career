import pytest

from app.core.config import get_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.skills.normalizer import SkillNormalizer
from app.models.skill import Skill


@pytest.fixture
def embeddings():
    return get_embeddings_provider(get_settings())


async def _seed(db_session, embeddings, rows):
    for slug, label, cat, aliases, embed_text in rows:
        s = Skill(slug=slug, label=label, category=cat, aliases=aliases)
        if embed_text is not None:
            s.embedding = await embeddings.embed_query(embed_text)
        db_session.add(s)
    await db_session.flush()


async def test_exact_and_alias_match(db_session, embeddings):
    await _seed(db_session, embeddings, [
        ("pytorch", "PyTorch", "ml_framework", ["torch"], None),
        ("scikit-learn", "scikit-learn", "ml_framework", ["sklearn"], None),
    ])
    n = SkillNormalizer(db_session, embeddings)
    await n.load()
    m1 = await n.normalize("  PyTorch ")
    assert m1 and m1.slug == "pytorch" and m1.method == "exact"
    m2 = await n.normalize("sklearn")
    assert m2 and m2.slug == "scikit-learn" and m2.method == "exact"
    assert await n.normalize("xyzzy-nope") is None


async def test_embedding_near_match(db_session, embeddings):
    # FakeEmbeddingsProvider is deterministic per exact string: seed the row's
    # embedding from a phrase, then query that same phrase -> cosine 1.0.
    await _seed(db_session, embeddings, [
        ("rag", "Retrieval-Augmented Generation", "ml_technique", [],
         "retrieval augmented generation pipeline over documents"),
    ])
    n = SkillNormalizer(db_session, embeddings, threshold=0.9)
    await n.load()
    m = await n.normalize("retrieval augmented generation pipeline over documents")
    assert m and m.slug == "rag" and m.method == "embedding" and m.score >= 0.9


async def test_normalize_many_dedupes(db_session, embeddings):
    await _seed(db_session, embeddings, [
        ("python", "Python", "language", ["py"], None),
    ])
    n = SkillNormalizer(db_session, embeddings)
    await n.load()
    out = await n.normalize_many(["Python", "python", "PY", "unknown"])
    assert set(out) <= {"Python", "python", "PY"}
    assert all(v.slug == "python" for v in out.values())
