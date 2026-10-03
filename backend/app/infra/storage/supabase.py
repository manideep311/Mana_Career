"""File storage in a private Supabase Storage bucket, over its HTTP API.

For hosts where the API and the worker can't share a disk (Render's free plan
has none at all). The bucket must be private: objects are only reachable with
the service-role key, which never leaves the backend.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

from app.core.errors import NotFoundError

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class StorageError(RuntimeError):
    """The storage service answered with an unexpected error."""


def _is_not_found(response: httpx.Response) -> bool:
    # Older Storage versions answer a missing object with 400 and a JSON body
    # saying 404; newer ones use 404 directly.
    if response.status_code == 404:
        return True
    if response.status_code == 400:
        try:
            body = response.json()
        except ValueError:
            return False
        return str(body.get("statusCode")) == "404" or body.get("error") == "not_found"
    return False


class SupabaseFileStore:
    def __init__(
        self,
        url: str,
        service_role_key: str,
        bucket: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = f"{url.rstrip('/')}/storage/v1"
        self._bucket = quote(bucket, safe="")
        self._headers = {"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key}
        self._transport = transport

    def _name(self, key: str) -> str:
        """The object name for a key; rejects the same keys LocalFileStore does."""
        parts = PurePosixPath(key.replace("\\", "/")).parts
        if not key or key.startswith(("/", "\\")) or ".." in parts or ":" in key:
            raise ValueError(f"Path traversal not allowed: {key}")
        return "/".join(parts)

    def _path(self, key: str) -> str:
        """The object name, URL-encoded for use in a request path."""
        return "/".join(quote(p, safe="") for p in self._name(key).split("/"))

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base, headers=self._headers, timeout=_TIMEOUT,
            transport=self._transport,
        )

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        path = self._path(key)
        async with self._client() as client:
            r = await client.post(
                f"/object/{self._bucket}/{path}", content=data,
                headers={"Content-Type": content_type, "x-upsert": "true"},
            )
        if r.status_code >= 300:
            raise StorageError(f"Upload failed ({r.status_code})")

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        async with self._client() as client:
            r = await client.get(f"/object/authenticated/{self._bucket}/{path}")
        if _is_not_found(r):
            raise NotFoundError(f"File not found: {key}", code="file_not_found")
        if r.status_code >= 300:
            raise StorageError(f"Download failed ({r.status_code})")
        return r.content

    async def delete(self, key: str) -> None:
        name = self._name(key)
        async with self._client() as client:
            # Removing by prefix succeeds (with an empty list) when nothing matches,
            # which keeps delete idempotent.
            r = await client.request(
                "DELETE", f"/object/{self._bucket}", json={"prefixes": [name]}
            )
        if r.status_code >= 300 and not _is_not_found(r):
            raise StorageError(f"Delete failed ({r.status_code})")

    async def exists(self, key: str) -> bool:
        path = self._path(key)
        async with self._client() as client:
            r = await client.head(f"/object/{self._bucket}/{path}")
        if r.status_code < 300:
            return True
        if r.status_code in (400, 404):
            return False
        raise StorageError(f"Lookup failed ({r.status_code})")
