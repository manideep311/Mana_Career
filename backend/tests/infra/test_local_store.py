import pytest

from app.core.errors import NotFoundError
from app.infra.storage.local import LocalFileStore


@pytest.fixture
def store(tmp_path):  # type: ignore[no-untyped-def]
    return LocalFileStore(str(tmp_path))


async def test_put_get_delete_roundtrip(store: LocalFileStore) -> None:
    await store.put("resumes/u1/r1.pdf", b"%PDF-1.7 ...", content_type="application/pdf")
    assert await store.exists("resumes/u1/r1.pdf") is True
    assert await store.get("resumes/u1/r1.pdf") == b"%PDF-1.7 ..."
    await store.delete("resumes/u1/r1.pdf")
    await store.delete("resumes/u1/r1.pdf")  # idempotent
    assert await store.exists("resumes/u1/r1.pdf") is False


async def test_get_missing_raises_not_found(store: LocalFileStore) -> None:
    with pytest.raises(NotFoundError):
        await store.get("nope/missing.pdf")


@pytest.mark.parametrize("bad", ["../escape.pdf", "/abs/path.pdf", "a/../../b.pdf"])
async def test_rejects_path_traversal(store: LocalFileStore, bad: str) -> None:
    with pytest.raises(ValueError):
        await store.put(bad, b"x", content_type="application/pdf")
