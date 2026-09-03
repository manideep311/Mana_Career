from __future__ import annotations

import asyncio

import httpx

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_RETRY_STATUS = {429, 500, 502, 503, 504}


class VoyageEmbeddingsProvider:
    _BATCH = 128
    _MAX_RETRIES = 3

    def __init__(
        self, *, api_key: str, model: str, dim: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._client = client or httpx.AsyncClient(timeout=30.0)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return self._model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._BATCH):
            out.extend(await self._post(texts[i : i + self._BATCH], input_type="document"))
        return out

    async def embed_query(self, text: str) -> list[float]:
        return (await self._post([text], input_type="query"))[0]

    async def _post(self, inputs: list[str], *, input_type: str) -> list[list[float]]:
        if not inputs:
            return []
        payload = {"input": inputs, "model": self._model, "input_type": input_type}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        last_exc: Exception | None = None
        for attempt in range(self._MAX_RETRIES):
            try:
                resp = await self._client.post(VOYAGE_URL, json=payload, headers=headers)
                if resp.status_code in _RETRY_STATUS:
                    last_exc = RuntimeError(f"voyage {resp.status_code}")
                    await asyncio.sleep(0.5 * 2**attempt)
                    continue
                resp.raise_for_status()
                rows = sorted(resp.json()["data"], key=lambda d: d["index"])
                vectors: list[list[float]] = [list(map(float, r["embedding"])) for r in rows]
                if any(len(v) != self._dim for v in vectors):
                    raise RuntimeError("voyage returned a vector of the wrong dimension")
                return vectors
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * 2**attempt)
        raise RuntimeError("voyage embeddings failed after retries") from last_exc
