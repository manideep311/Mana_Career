import math

from app.domain.embeddings.adapters.fake import FakeEmbeddingsProvider


async def test_dim_and_determinism():
    p = FakeEmbeddingsProvider(dim=1024, model="fake-embed-1")
    v1 = await p.embed_query("machine learning")
    v2 = await p.embed_query("machine learning")
    assert len(v1) == 1024
    assert v1 == v2


async def test_normalized_and_distinct():
    p = FakeEmbeddingsProvider(dim=64, model="fake-embed-1")
    a = await p.embed_query("python")
    b = await p.embed_query("kubernetes")
    assert a != b
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-6)


async def test_embed_documents_batches():
    p = FakeEmbeddingsProvider(dim=8, model="fake-embed-1")
    out = await p.embed_documents(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == 8 for v in out)
