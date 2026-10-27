"""LocalEmbeddingsProvider with fastembed's model replaced by a recording stub."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import numpy as np
import pytest

from app.core.config import Settings
from app.domain.embeddings.adapters import local
from app.domain.embeddings.adapters.local import BGE_QUERY_INSTRUCTION, LocalEmbeddingsProvider
from app.domain.embeddings.factory import get_embeddings_provider

MODEL = "BAAI/bge-small-en-v1.5"


class StubModel:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.calls: list[tuple[list[str], int]] = []

    def embed(self, texts: Iterable[str], batch_size: int = 256) -> Iterator[np.ndarray]:
        texts = list(texts)
        self.calls.append((texts, batch_size))
        for i, _ in enumerate(texts):
            yield np.full(self.dim, i, dtype=np.float32)


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> StubModel:
    model = StubModel()
    monkeypatch.setattr(local, "load_model", lambda name, cache_dir=None: model)
    return model


async def test_queries_get_the_bge_instruction_and_passages_do_not(stub: StubModel):
    p = LocalEmbeddingsProvider(model=MODEL, dim=384)
    q = await p.embed_query("makes models smaller for phones")
    docs = await p.embed_documents(["Quantise weights to int8.", "Prune channels."])
    assert len(q) == 384 and len(docs) == 2 and docs[1][0] == 1.0
    assert stub.calls[0][0] == [BGE_QUERY_INSTRUCTION + "makes models smaller for phones"]
    assert stub.calls[1][0] == ["Quantise weights to int8.", "Prune channels."]
    assert all(batch == LocalEmbeddingsProvider._BATCH for _, batch in stub.calls)


async def test_no_texts_no_model_call(stub: StubModel):
    assert await LocalEmbeddingsProvider(model=MODEL, dim=384).embed_documents([]) == []
    assert stub.calls == []


async def test_a_wrong_sized_vector_is_an_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(local, "load_model", lambda name, cache_dir=None: StubModel(dim=12))
    with pytest.raises(RuntimeError, match="wrong dimension"):
        await LocalEmbeddingsProvider(model=MODEL, dim=384).embed_query("x")


def test_the_model_and_size_must_match():
    with pytest.raises(ValueError, match="does not make 1024-d"):
        LocalEmbeddingsProvider(model=MODEL, dim=1024)
    with pytest.raises(ValueError):
        LocalEmbeddingsProvider(model="some/other-model", dim=384)


def test_the_model_is_loaded_once_per_process(monkeypatch: pytest.MonkeyPatch):
    loads: list[str] = []

    class Loader:
        def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
            loads.append(model_name)

    import fastembed

    monkeypatch.setattr(fastembed, "TextEmbedding", Loader)
    monkeypatch.setattr(local, "_models", {})
    first = local.load_model(MODEL, "/models")
    assert local.load_model(MODEL, "/models") is first
    assert loads == [MODEL]


def test_the_factory_builds_it(monkeypatch: pytest.MonkeyPatch):
    for key, value in {
        "EMBEDDINGS_PROVIDER": "local", "EMBED_MODEL": MODEL, "EMBED_DIM": "384",
        "LOCAL_EMBED_CACHE_DIR": "/models",
    }.items():
        monkeypatch.setenv(key, value)
    p = get_embeddings_provider(Settings(_env_file=None))  # type: ignore[call-arg]
    assert isinstance(p, LocalEmbeddingsProvider)
    assert (p.model, p.dim, p._cache_dir) == (MODEL, 384, "/models")
