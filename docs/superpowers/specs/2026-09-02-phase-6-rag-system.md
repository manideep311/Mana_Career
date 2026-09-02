# Phase 6 — RAG System — Design Addendum

Refines the master spec (`2026-08-30-mana-career-design.md` §4 `rag/`, §5.4 vector &
retrieval strategy, §5.3 `eval_runs`/`eval_results`, §6 `/eval`, §10 evaluation,
§11 prompt-injection, §9 roadmap row 6). Where this document and the master spec
disagree, this document wins for Phase 6.

**Goal:** a grounded hybrid retriever (vector + tsv + RRF → MMR → token-budgeted
context with citations and `<untrusted_data>` fencing), a real embeddings adapter,
a retrieval-eval harness that gates CI, and the matching engine's `semantic`
dimension routed through the retriever.

**Done when:** `score_match` builds its semantic input from `RagService`; the
retrieval eval suite runs in CI against a seeded DB with `fake` embeddings and the
build fails if `recall@10 < 0.75 || mrr < 0.45 || ndcg@10 < 0.55`.

---

## Global Constraints

- Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic (chain
  `…→0008_matches→0009_eval`), pgvector (`Vector`, `.cosine_distance()` / `<=>`),
  `pydantic-settings`, `structlog`, `import-linter`.
- pytest `--import-mode=importlib` (already in `backend/pyproject.toml` addopts).
- `EMBEDDINGS_PROVIDER=fake` in CI and every test. `FakeEmbeddingsProvider` =
  deterministic unit vector per exact string (sha256-seeded). The real
  `voyage` adapter is exercised only when `VOYAGE_API_KEY` is set (never in CI).
- Retrieval math (`rrf`, `mmr`, token-budget assembly, fencing) is **pure** — no
  DB, no network, no wall-clock, no randomness. `VectorStore` is the only rag
  file that runs SQL.
- `import-linter`: `app.domain.rag.*` may import `app.domain.embeddings`,
  `app.models`, `app.core` only — never `app.domain.matching`, `app.domain.jobs`,
  `app.api`, `app.worker`. Cross-domain entry is `app.domain.rag.service.RagService`.
- All money/tuning constants are module-level named constants, not literals.

---

## 1. `backend/app/domain/rag/` module

### 1.1 `types.py`
```python
from enum import Enum

class RetrievalSource(str, Enum):
    JOB_CHUNKS = "job_chunks"          # Phase 6
    # RESUME_CHUNKS = "resume_chunks"  # later
    # COMPANY_RESEARCH = "company_research"  # Phase 7
    # LEARNING_RESOURCES = "learning_resources"  # Phase 12

@dataclass(frozen=True)
class ScoredChunk:
    ref_id: str            # "<job_id>:<chunk_index>"
    source: RetrievalSource
    section: str
    content: str
    token_count: int
    embedding: tuple[float, ...] | None
    vector_rank: int | None   # 1-based; None if not in the vector list
    text_rank: int | None     # 1-based; None if not in the tsv list
    rrf_score: float
    mmr_score: float | None   # set after MMR; None before

@dataclass(frozen=True)
class Citation:
    ref_id: str
    source: str               # RetrievalSource value
    section: str
    score: float              # rrf_score (post-fusion relevance)

@dataclass(frozen=True)
class RetrievedContext:
    blocks: tuple[ScoredChunk, ...]      # final, MMR- + budget-selected, in order
    text: str                           # rendered, each block <untrusted_data>-fenced
    citations: tuple[Citation, ...]      # 1:1 with blocks, same order
    total_tokens: int
    query: str
```

### 1.2 `fusion.py` (pure)
```python
RRF_K = 60
MMR_LAMBDA = 0.7

def rrf(*ranked: list[str], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal-rank fusion. Each arg is an ordered list of ref_ids (rank 1 = best).
    Returns {ref_id: sum(1/(k + rank))}. A ref_id absent from a list contributes 0
    from that list."""

def mmr(
    candidates: list[ScoredChunk],   # already fusion-ordered (desc rrf_score)
    *,
    lambda_: float = MMR_LAMBDA,
    k: int,
) -> list[ScoredChunk]:
    """Maximal Marginal Relevance over `candidates`, using rrf_score (min-max
    normalised to [0,1] across the candidate set) as relevance and cosine of
    `embedding` as redundancy. Greedy: pick argmax [ λ·rel(d) − (1−λ)·max_{s∈S} cos(d,s) ]
    until |S| == k or candidates exhausted. A candidate with `embedding is None`
    is treated as maximally novel (redundancy term 0). Deterministic tie-break:
    higher rrf_score, then lexicographic ref_id. Sets `mmr_score` on each returned
    chunk."""
```

### 1.3 `context.py` (pure)
```python
DEFAULT_TOKEN_BUDGET = 2000
_FENCE_OPEN = '<untrusted_data source="{source}" ref="{ref}">'
_FENCE_CLOSE = "</untrusted_data>"

def _neutralize(text: str) -> str:
    """Defang any literal fence markers a chunk's content might carry, so retrieved
    text can never open or close a fence:
        text.replace("<untrusted_data", "‹untrusted_data").replace("untrusted_data>", "untrusted_data›")
    (order matters — the second call also catches the closing tag's '>' left by the
    first). Case-insensitive on the tag name. Nothing else in the content is touched."""

def assemble_context(
    chunks: list[ScoredChunk],           # MMR-ordered
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    query: str,
) -> RetrievedContext:
    """Greedily take chunks in order while running-sum(token_count) <= token_budget
    (always take at least the first chunk even if it alone exceeds the budget).
    Render `text` as the fenced blocks joined by '\n\n'. Build `citations` 1:1."""
```

Rendered `text` shape (exact):
```
<untrusted_data source="job_chunks" ref="7b3f…:2">
…neutralized chunk content…
</untrusted_data>

<untrusted_data source="job_chunks" ref="7b3f…:5">
…
</untrusted_data>
```

### 1.4 `vector_store.py` (the only rag file with SQL)
```python
VECTOR_TOP_N = 30
TEXT_TOP_N = 30

class VectorStore:
    def __init__(self, session: AsyncSession) -> None: ...

    async def vector_search(
        self, *, source: RetrievalSource, query_embedding: list[float],
        user_id: uuid.UUID, job_id: uuid.UUID | None = None, k: int = VECTOR_TOP_N,
    ) -> list[ScoredChunk]:
        """JOB_CHUNKS: SELECT … FROM job_chunks
           WHERE embedding IS NOT NULL
             AND (owner_id IS NULL OR owner_id = :user_id)
             AND (:job_id IS NULL OR job_id = :job_id)
           ORDER BY embedding <=> :qemb  LIMIT :k
           → ScoredChunk(vector_rank=1..k, text_rank=None, rrf_score=0.0)."""

    async def text_search(
        self, *, source: RetrievalSource, query_text: str,
        user_id: uuid.UUID, job_id: uuid.UUID | None = None, k: int = TEXT_TOP_N,
    ) -> list[ScoredChunk]:
        """JOB_CHUNKS: … WHERE chunk_tsv @@ websearch_to_tsquery('english', :q)
             AND (owner_id IS NULL OR owner_id = :user_id)
             AND (:job_id IS NULL OR job_id = :job_id)
           ORDER BY ts_rank_cd(chunk_tsv, websearch_to_tsquery('english', :q)) DESC
           LIMIT :k → ScoredChunk(text_rank=1..k, vector_rank=None)."""
```
`ref_id` = `f"{row.job_id}:{row.chunk_index}"`. `embedding` cast to `tuple(float, …)`
or `None`. `websearch_to_tsquery` with an empty/stopword-only query yields no rows —
`text_search` returns `[]`, never raises.

### 1.5 `reranker.py`
```python
class Reranker(Protocol):
    async def rerank(self, query: str, chunks: list[ScoredChunk]) -> list[ScoredChunk]: ...

class NoopReranker:
    async def rerank(self, query, chunks): return chunks   # identity
```
Wired into `RagService` (constructed, called) but inert. A cross-encoder is Phase 8+.

### 1.6 `service.py`
```python
class RagService:
    def __init__(
        self, session: AsyncSession, embeddings: EmbeddingsProvider,
        *, reranker: Reranker | None = None, settings: Settings | None = None,
    ) -> None: ...

    async def retrieve(
        self, query: str, *, source: RetrievalSource, user_id: uuid.UUID,
        job_id: uuid.UUID | None = None, k: int = 8,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> RetrievedContext:
        """1. qemb = await embeddings.embed_query(query)  (skip if query blank → empty ctx)
           2. vec = await store.vector_search(...);  txt = await store.text_search(...)
           3. fused_ids = rrf([c.ref_id for c in vec], [c.ref_id for c in txt])
           4. merge vec+txt by ref_id into ScoredChunk (keep both ranks + embedding),
              set rrf_score, order by rrf_score desc  → candidates
           5. candidates = await reranker.rerank(query, candidates)   (noop today)
           6. selected = mmr(candidates, k=k)
           7. return assemble_context(selected, token_budget=token_budget, query=query)
           Empty at any step → RetrievedContext(blocks=(), text="", citations=(),
           total_tokens=0, query=query)."""
```

---

## 2. Embeddings — `voyage` adapter

`backend/app/domain/embeddings/adapters/voyage.py` — `VoyageEmbeddingsProvider`
implements `EmbeddingsProvider` (`dim`, `model`, `embed_documents`, `embed_query`).

- `httpx.AsyncClient`, `POST https://api.voyageai.com/v1/embeddings`,
  `Authorization: Bearer {settings.voyage_api_key}`, body
  `{"input": [...], "model": settings.embed_model, "input_type": "document"|"query"}`.
- `embed_documents` batches at 128 inputs/request; concatenates in order.
- Retry: 3 attempts, exp backoff (0.5·2ⁿ) on 429/5xx/timeout; raise after.
- `dim` returns `settings.embed_dim` (1024 for `voyage-3` / `voyage-3-lite`);
  assert each returned vector's length == `dim`.
- Config additions (`app/core/config.py`): `voyage_api_key: str | None = None`;
  `embeddings_provider` default stays `"fake"`; `embed_model` default stays
  `"fake-embed-1"` (deploy overrides to `voyage-3-lite`).
- `factory.get_embeddings_provider`: add the `"voyage"` branch (raises a clear
  error if `voyage_api_key` is unset); `"openai"`/`"local"` still `NotImplementedError`.
- Tests: a `respx`/`httpx.MockTransport` unit test for batching + retry + dim
  assertion. No live calls.

---

## 3. Matching `semantic` → rag

- `MatchService.build_job_snapshot(job_id, *, chunk_embeddings: list[tuple[float,...]] | None = None)`
  — when `chunk_embeddings` is given, `JobSnapshot.chunk_embeddings` is built from
  it verbatim; when `None`, the existing "all chunks for this job, ordered by
  `chunk_index`" query runs (unchanged — non-worker callers, and the fallback).
- `score_match` worker, after building `profile` and before `score(...)`:
  ```python
  ctx = await RagService(session, get_embeddings_provider(settings)).retrieve(
      profile.summary_text, source=RetrievalSource.JOB_CHUNKS,
      user_id=m.user_id, job_id=m.job_id, k=8,
  ) if profile.summary_text else None
  sub = [c.embedding for c in ctx.blocks if c.embedding] if ctx else None
  job = await svc.build_job_snapshot(m.job_id, chunk_embeddings=sub or None)
  ```
  So `_dim_semantic` now cosines the profile embedding against the mean of the
  **MMR-selected** chunk subset, not a blind mean of every chunk. Scorer code
  unchanged. `inputs_hash` continues to hash the (now curated) `chunk_embeddings`
  tuple — still deterministic given the same job + profile (retrieval is pure
  given the same corpus + query).
- `RagService` used read-only here; no writes, no enqueue.
- The existing `score_match` DB test seeds one chunk; with rag in the loop it
  still resolves that chunk (tsv arm on `content="c"` may miss, but the vector
  arm returns it) → keep the test green; add one assertion that the match still
  reaches `ready` with a non-null score.

---

## 4. `eval_runs` / `eval_results` + migration `0009_eval`

Per master spec §5.3.

`backend/app/models/eval.py`:
- `EvalRun(Base, TimestampMixin)`: `id`, `suite` String(16) CHECK
  `('retrieval','generation','matching')`, `dataset_ref` String(200),
  `dataset_version` String(32), `git_sha` String(40), `provider` String(32),
  `model_ids` JSONB `'{}'`, `config` JSONB `'{}'`, `metrics` JSONB `'{}'`,
  `status` String(16) default `'running'` CHECK `('running','passed','failed','error')`,
  `started_at` timestamptz default now, `ended_at` timestamptz null.
- `EvalResult(Base, TimestampMixin)`: `id`, `eval_run_id` FK eval_runs CASCADE,
  `case_id` String(80), `input` JSONB, `expected` JSONB, `actual` JSONB,
  `scores` JSONB `'{}'`, `passed` Boolean, `judge_meta` JSONB `'{}'`.
  Index `(eval_run_id)`.
- `models/__init__.py` += `from app.models import eval as eval` (after `audit`,
  keep alpha).

Migration `0009_eval` — `revision="0009_eval"`, `down_revision="0008_matches"`.
Two tables + `updated_at` triggers (reuse `set_updated_at()`); downgrade drops
`eval_results` then `eval_runs` (trigger DROP first). No generated columns.

---

## 5. `backend/eval/` harness

```
backend/eval/
  __init__.py
  run.py                       # CLI entrypoint
  thresholds.py                # CI-tier metric floors (module constants)
  metrics.py                   # pure: recall_at_k, precision_at_k, mrr, ndcg_at_k
  suites/
    __init__.py
    retrieval.py               # the retrieval suite
  datasets/
    retrieval/
      golden_v1.jsonl          # ~18 cases
```

### 5.1 `datasets/retrieval/golden_v1.jsonl`
One JSON object per line:
```json
{"id": "py-backend-kafka", "query": "senior python backend engineer with kafka and postgres",
 "source": "job_chunks", "relevant": ["<job_key>:<chunk_index>", "..."], "notes": "…"}
```
`relevant` uses the **stable `key`** from `jobs.demo.json` (the suite resolves
`key → job_id` after seeding), joined to `chunk_index`. ~18 cases spanning the 41
seed jobs: role+stack queries, seniority queries, location/remote queries,
domain queries ("computer vision perception"), and 2 deliberate near-miss queries
whose `relevant` set is small (tests precision). Hand-labeled against the seed
corpus so the answer key is stable and reviewable.

### 5.2 `metrics.py` (pure)
`recall_at_k(retrieved: list[str], relevant: set[str], k) -> float`,
`precision_at_k(...)`, `mrr(retrieved, relevant) -> float` (1/rank of first hit,
else 0), `ndcg_at_k(retrieved, relevant, k) -> float` (binary gains, ideal DCG
over `min(len(relevant), k)`). No IO. Unit-tested with worked examples.

### 5.3 `suites/retrieval.py`
```python
async def run_retrieval_suite(
    session: AsyncSession, *, provider: str, write_db: bool, git_sha: str,
) -> EvalReport:
    # 1. ensure the seed corpus is loaded + chunked + embedded in this DB
    #    (call app.seed.seed_jobs; embed any chunk whose embedding IS NULL via the
    #     configured provider — with `fake`, deterministic).
    # 2. for each golden case: resolve keys→ids, RagService(...).retrieve(query,
    #    source=JOB_CHUNKS, user_id=<a fixed eval user>, k=10, token_budget=big),
    #    retrieved = [b.ref_id for b in ctx.blocks]
    # 3. per-case scores: recall@5, recall@10, precision@5, mrr, ndcg@10; passed =
    #    recall@10 >= THRESH.recall_at_10 (case-level gate is lenient; the suite
    #    gate is the aggregate)
    # 4. aggregate = mean of each metric across cases
    # 5. if write_db: insert EvalRun(suite="retrieval", dataset_version="v1",
    #    dataset_ref="datasets/retrieval/golden_v1.jsonl", git_sha, provider,
    #    model_ids={"embed": settings.embed_model}, metrics=aggregate,
    #    status="passed"|"failed") + one EvalResult per case.
    # 6. return EvalReport(aggregate, per_case, passed=all aggregate >= threshold)
```
`EvalReport` is a plain dataclass (not persisted) the CLI prints.

### 5.4 `thresholds.py`
```python
# CI tier — fake embeddings; the tsv arm + RRF + MMR carry these on the seed corpus.
RECALL_AT_10 = 0.75
MRR = 0.45
NDCG_AT_10 = 0.55
# Quality tier — real voyage; enforced only when a key is present.
QUALITY_RECALL_AT_10 = 0.90
QUALITY_MRR = 0.70
QUALITY_NDCG_AT_10 = 0.80
```

### 5.5 `run.py`
`python -m eval.run retrieval [--provider fake|voyage] [--write-db] [--json]`
- Builds a test DB session (reuse the app's async engine against
  `DATABASE_URL`), runs the suite, prints a table (metric | value | threshold |
  pass), and JSON when `--json`.
- Exit `0` if every aggregate metric ≥ its CI-tier threshold (or quality-tier
  when `--provider voyage` and a key is set); exit `1` otherwise.
- `--write-db` persists the run; default is read-only (CI uses `--write-db`).

---

## 6. `/eval` API — `backend/app/api/v1/eval.py`

`router = APIRouter(prefix="/eval", tags=["eval"])`, every route `Depends(get_current_admin)`.

- `POST /eval/runs` — body `EvalRunIn{suite: Literal["retrieval"]}` (only
  `retrieval` accepted in Phase 6; others → 422). Runs `run_retrieval_suite(
  session, provider=settings.embeddings_provider, write_db=True, git_sha=<from
  env or "dev">)` **inline** (deterministic, < 5 s for 18 cases), returns
  `202` + `EvalRunOut` (the persisted row). No ARQ task.
- `GET /eval/runs` — `?suite=&limit=&offset=` → `EvalRunListOut{items,total}`,
  newest first.
- `GET /eval/runs/{run_id}` → `EvalRunOut` or 404.
- `GET /eval/runs/{run_id}/results` → `list[EvalResultOut]` (per-case).
- Schemas in `app/api/v1/schemas/eval.py`, explicit mappers (no `from_attributes`),
  mirroring the `/matches` style. `EvalRunOut`: `id, suite, dataset_version,
  git_sha, provider, model_ids, metrics, status, started_at, ended_at`.
- `router.py` — add `eval` to the `from app.api.v1 import (...)` tuple and an
  `api_router.include_router(eval.router)` line, both in the alpha slot between
  `auth` and `health`.
- Rate limit: `/eval` POST is admin-only and cheap — no `_bucket` change
  (falls through to `"read"`; acceptable, admin-gated).

---

## 7. CI — new `eval` job in `.github/workflows/ci.yml`

A job mirroring `backend` (Postgres service, `uv sync`, `CREATE DATABASE
mana_test`), then:
```yaml
      - run: uv run alembic upgrade head
      - run: uv run python -m eval.run retrieval --write-db
        env:
          DATABASE_URL: postgresql+asyncpg://mana:mana@localhost/mana_test
          EMBEDDINGS_PROVIDER: fake
          LLM_PROVIDER: fake
```
An independent job — runs in parallel with `backend` and `frontend`; the workflow
is green only if all three pass. Fails the build on a threshold breach or a
suite error.

---

## 8. Frontend — admin `/eval` page

- `frontend/lib/api/endpoints.ts` — `api.eval` group: `listRuns(query)`,
  `getRun(id)`, `runResults(id)`, `createRun(suite)`.
- `frontend/lib/api/types.ts` — `EvalRun`, `EvalResult`, `EvalSuite`.
- `frontend/lib/query.ts` — `qk.evalRuns`, `qk.evalRun(id)`, `qk.evalResults(id)`.
- `frontend/app/(app)/eval/page.tsx` — a table of runs (suite · status pill ·
  `recall@10` / `mrr` / `ndcg@10` · git_sha (short) · date), a "Run retrieval
  suite" button (`createRun("retrieval")` → toast + invalidate), each row links
  to `…/eval/[id]`.
- `frontend/app/(app)/eval/[id]/page.tsx` — run header (metrics + config) + a
  per-case results table (case_id · recall@10 · mrr · ndcg@10 · passed).
- Nav: add an "Eval" link to the app shell **only when `useAuth().user?.is_admin`**.
- Tests: `endpoints.test.ts` extend (the 4 `api.eval` calls); one
  `tests/eval/eval-page.test.tsx` — renders a runs table from a mocked
  `listRuns`, asserts a metric renders and the "Run" button is present; a
  second assertion that the page renders nothing/redirects for a non-admin
  (match however the app already guards admin routes — check `app/(app)/layout`).

---

## 9. Out of scope (flag in the completion report)

- `resume_chunks`, `company_research`, `learning_resources`, `skills` retrieval
  sources (later phases) — the enum + `VectorStore` shape leave room; no wiring.
- Cross-encoder / hosted reranker — `NoopReranker` only.
- Generation eval, `/ops/tasks/failures`, the eval dashboard charts — Phase 9 / 13.
- Real `voyage` retrieval-quality thresholds in CI — quality tier is local /
  nightly, key-gated.
- `openai` / `local` embeddings adapters.
- Query rewriting / HyDE / multi-query — not in the spec's recipe.
