"""SupabaseFileStore against a fake Storage API (httpx.MockTransport)."""
from __future__ import annotations

import json

import httpx
import pytest

from app.core.errors import NotFoundError
from app.infra.storage.supabase import StorageError, SupabaseFileStore

KEY = "service-role-key"


class FakeStorage:
    """Just enough of Supabase Storage: one private bucket in memory."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []
        self.legacy_404 = False  # older versions answer "missing" with a 400

    def _missing(self) -> httpx.Response:
        if self.legacy_404:
            return httpx.Response(400, json={"statusCode": "404", "error": "not_found"})
        return httpx.Response(404, json={"error": "not_found"})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == f"Bearer {KEY}"
        assert request.headers["apikey"] == KEY
        path = request.url.path.removeprefix("/storage/v1/object/")
        if request.method == "POST":
            name = path.removeprefix("resumes/")
            self.objects[name] = request.content
            return httpx.Response(200, json={"Key": path})
        if request.method == "GET":
            name = path.removeprefix("authenticated/resumes/")
            if name not in self.objects:
                return self._missing()
            return httpx.Response(200, content=self.objects[name])
        if request.method == "HEAD":
            name = path.removeprefix("resumes/")
            return httpx.Response(200 if name in self.objects else 404)
        if request.method == "DELETE":
            for name in json.loads(request.content)["prefixes"]:
                self.objects.pop(name, None)
            return httpx.Response(200, json=[])
        return httpx.Response(405)


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def store(storage: FakeStorage) -> SupabaseFileStore:
    return SupabaseFileStore(
        "https://proj.supabase.co/", KEY, "resumes",
        transport=httpx.MockTransport(storage.handler),
    )


async def test_round_trip(store, storage):
    await store.put("resumes/u1/a.pdf", b"%PDF-1.4", content_type="application/pdf")
    assert await store.exists("resumes/u1/a.pdf")
    assert await store.get("resumes/u1/a.pdf") == b"%PDF-1.4"
    upload = storage.requests[0]
    assert upload.url.path == "/storage/v1/object/resumes/resumes/u1/a.pdf"
    assert upload.headers["content-type"] == "application/pdf"
    assert upload.headers["x-upsert"] == "true"


async def test_missing_files_read_as_not_found_in_either_api_version(store, storage):
    with pytest.raises(NotFoundError):
        await store.get("resumes/u1/nope.pdf")
    storage.legacy_404 = True
    with pytest.raises(NotFoundError):
        await store.get("resumes/u1/nope.pdf")
    assert not await store.exists("resumes/u1/nope.pdf")


async def test_delete_is_idempotent(store, storage):
    await store.put("resumes/u1/a.pdf", b"x", content_type="application/pdf")
    await store.delete("resumes/u1/a.pdf")
    await store.delete("resumes/u1/a.pdf")  # already gone: no error
    assert storage.objects == {}
    assert json.loads(storage.requests[-1].content) == {"prefixes": ["resumes/u1/a.pdf"]}


@pytest.mark.parametrize("bad", ["", "/etc/passwd", "..\\x", "resumes/../../x", "C:/x"])
async def test_rejects_keys_that_could_escape_the_bucket_path(store, bad):
    with pytest.raises(ValueError):
        await store.get(bad)


async def test_server_errors_are_not_mistaken_for_missing_files():
    def broken(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    store = SupabaseFileStore("https://p.supabase.co", KEY, "resumes",
                              transport=httpx.MockTransport(broken))
    with pytest.raises(StorageError):
        await store.get("resumes/u1/a.pdf")
    with pytest.raises(StorageError):
        await store.exists("resumes/u1/a.pdf")
