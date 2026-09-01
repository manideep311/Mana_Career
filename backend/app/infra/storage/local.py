from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.errors import NotFoundError


class LocalFileStore:
    """File storage backed by the local filesystem."""

    def __init__(self, root: str) -> None:
        """Initialize with root directory path.

        Args:
            root: Root directory for file storage
        """
        self._root = root

    def _resolve(self, key: str) -> Path:
        """Resolve and validate a key to a safe filesystem path.

        Raises:
            ValueError: If key contains path traversal attempts
        """
        if key.startswith("/") or ".." in Path(key).parts:
            raise ValueError(f"Path traversal not allowed: {key}")
        return Path(self._root) / key

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """Store data at the given key.

        Args:
            key: Storage key (e.g. "resumes/user1/file.pdf")
            data: Binary data to store
            content_type: MIME type of the data (not persisted for local adapter)
        """
        path = self._resolve(key)
        await asyncio.to_thread(lambda: path.parent.mkdir(parents=True, exist_ok=True))
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        """Retrieve data at the given key.

        Args:
            key: Storage key

        Returns:
            Binary data

        Raises:
            NotFoundError: If key does not exist
        """
        path = self._resolve(key)
        exists = await asyncio.to_thread(path.exists)
        if not exists:
            raise NotFoundError(f"File not found: {key}", code="file_not_found")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        """Delete data at the given key.

        Idempotent: does not raise if key does not exist.

        Args:
            key: Storage key
        """
        path = self._resolve(key)
        await asyncio.to_thread(path.unlink, True)

    async def exists(self, key: str) -> bool:
        """Check if data exists at the given key.

        Args:
            key: Storage key

        Returns:
            True if key exists, False otherwise
        """
        path = self._resolve(key)
        return await asyncio.to_thread(path.exists)
