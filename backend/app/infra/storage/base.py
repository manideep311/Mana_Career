from __future__ import annotations

from typing import Protocol


class FileStore(Protocol):
    """Protocol for file storage backends."""

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """Store data at the given key.

        Args:
            key: Storage key (e.g. "resumes/user1/file.pdf")
            data: Binary data to store
            content_type: MIME type of the data
        """
        ...

    async def get(self, key: str) -> bytes:
        """Retrieve data at the given key.

        Args:
            key: Storage key

        Returns:
            Binary data

        Raises:
            NotFoundError: If key does not exist
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete data at the given key.

        Idempotent: does not raise if key does not exist.

        Args:
            key: Storage key
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check if data exists at the given key.

        Args:
            key: Storage key

        Returns:
            True if key exists, False otherwise
        """
        ...
