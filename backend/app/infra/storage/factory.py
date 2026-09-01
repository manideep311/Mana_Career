from __future__ import annotations

from app.core.config import Settings
from app.infra.storage.base import FileStore
from app.infra.storage.local import LocalFileStore


def get_file_store(settings: Settings) -> FileStore:
    """Factory function to create a FileStore instance based on settings.

    Args:
        settings: Application settings

    Returns:
        FileStore implementation

    Raises:
        NotImplementedError: For unsupported storage backends
    """
    if settings.file_store == "local":
        return LocalFileStore(settings.file_store_local_dir)
    elif settings.file_store == "s3":
        raise NotImplementedError("S3 file store lands later")
    else:
        # This should never happen due to Literal type annotation, but for safety
        raise NotImplementedError(f"Unknown file store: {settings.file_store}")
