import json

import httpx
import pytest

from app.domain.embeddings.adapters.voyage import VoyageEmbeddingsProvider


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_embed_documents_batches_and_preserves_order():
    seen: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["input"])
        data = [{"index": i, "embedding": [float(len(t))] * 4} for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"data": data})

    prov = VoyageEmbeddingsProvider(
        api_key="k", model="voyage-3-lite", dim=4, client=_client(handler)
    )
    prov._BATCH = 2  # force two batches for 3 inputs
    out = await prov.embed_documents(["a", "bb", "ccc"])
    assert [v[0] for v in out] == [1.0, 2.0, 3.0]
    assert seen == [["a", "bb"], ["ccc"]]


async def test_embed_query_returns_single_vector():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5] * 4}]})

    prov = VoyageEmbeddingsProvider(api_key="k", model="m", dim=4, client=_client(handler))
    assert await prov.embed_query("hi") == [0.5, 0.5, 0.5, 0.5]


async def test_retries_then_raises_on_persistent_5xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "unavailable"})

    prov = VoyageEmbeddingsProvider(api_key="k", model="m", dim=4, client=_client(handler))
    with pytest.raises(RuntimeError):
        await prov.embed_query("x")
    assert calls["n"] == 3


async def test_dim_mismatch_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    prov = VoyageEmbeddingsProvider(api_key="k", model="m", dim=4, client=_client(handler))
    with pytest.raises(RuntimeError):
        await prov.embed_query("x")
