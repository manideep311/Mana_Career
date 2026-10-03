from __future__ import annotations

from app.core.config import Settings
from app.infra.storage.base import FileStore
from app.infra.storage.local import LocalFileStore
from app.infra.storage.supabase import SupabaseFileStore


def get_file_store(settings: Settings) -> FileStore:
    # "local": the API and worker share one mounted directory (Docker Compose).
    # "supabase": a private Storage bucket, for hosts without a shared disk.
    if settings.file_store == "supabase":
        assert settings.supabase_url and settings.supabase_service_role_key  # checked at startup
        return SupabaseFileStore(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
            settings.supabase_storage_bucket,
        )
    return LocalFileStore(settings.file_store_local_dir)
