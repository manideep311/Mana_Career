from __future__ import annotations

from app.core.config import Settings
from app.infra.storage.base import FileStore
from app.infra.storage.local import LocalFileStore


def get_file_store(settings: Settings) -> FileStore:
    # FILE_STORE only accepts "local"; API and worker share one mounted directory.
    return LocalFileStore(settings.file_store_local_dir)
