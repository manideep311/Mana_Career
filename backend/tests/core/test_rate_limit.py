from app.core.rate_limit import check_rate_limit


class _R:
    def __init__(self) -> None:
        self.n: dict[str, int] = {}

    async def incr(self, k: str) -> int:
        self.n[k] = self.n.get(k, 0) + 1
        return self.n[k]

    async def expire(self, k: str, ttl: int) -> None:
        return None

    async def ttl(self, k: str) -> int:
        return 42


async def test_allows_up_to_limit_then_blocks():
    r = _R()
    states = [await check_rate_limit(r, key="k", limit=3) for _ in range(4)]
    assert [s.allowed for s in states] == [True, True, True, False]
    assert states[2].remaining == 0
    assert states[3].reset == 42


async def test_first_hit_sets_expiry():
    calls: list[tuple[str, int]] = []

    class _RecordingR(_R):
        async def expire(self, k: str, ttl: int) -> None:
            calls.append((k, ttl))

    r = _RecordingR()
    await check_rate_limit(r, key="k", limit=5, window_seconds=60)
    await check_rate_limit(r, key="k", limit=5, window_seconds=60)
    assert calls == [("k", 60)]


def test_bucket_classifies_uploads():
    from app.core.rate_limit import _bucket

    assert _bucket("/api/v1/resumes", "POST") == "upload"
    assert _bucket("/api/v1/jobs", "POST") == "upload"
    assert _bucket("/api/v1/resumes", "GET") == "read"
    assert _bucket("/api/v1/auth/login", "POST") == "auth"


def test_bucket_classifies_llm_tier():
    from app.core.rate_limit import _bucket

    uid = "11111111-1111-1111-1111-111111111111"
    assert _bucket(f"/api/v1/resumes/{uid}/reprocess", "POST") == "llm"
    assert _bucket(f"/api/v1/resumes/{uid}/confirm-profile", "POST") == "llm"
    assert _bucket("/api/v1/matches", "POST") == "llm"
    assert _bucket("/api/v1/matches/recompute", "POST") == "llm"
    # A GET to the same paths is not an LLM-tier call.
    assert _bucket(f"/api/v1/resumes/{uid}/reprocess", "GET") == "read"
    assert _bucket(f"/api/v1/resumes/{uid}/confirm-profile", "GET") == "read"
    assert _bucket("/api/v1/matches", "GET") == "read"
