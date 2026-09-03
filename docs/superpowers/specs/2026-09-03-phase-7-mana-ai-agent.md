# Phase 7 — Mana AI Agent — Design Addendum

Refines the master spec (`2026-08-30-mana-career-design.md` §4 AI Agent Architecture,
§2.4 ResponseBlock, §5.3 `ai_sessions`/`messages`/`ai_actions`/`agent_steps`, §6 `/ai`,
§6.5 rate limits, §9 row 7, D11). Where this document and the master spec disagree,
this wins for Phase 7. **Split into two implementation plans:**

- **Phase 7a** — agent infrastructure + the `understand_job` ("find jobs that match my
  experience") path, backend only.
- **Phase 7b** — frontend: `ManaPanelDock`, `block-registry.ts` + `components/ai/blocks/`,
  the AI Activity page.

The `prepare_application` chain (`resume_tailoring` → `cover_letter` → `email_draft` →
`claim_validator` → `application_prep` → `human_approval` → `email_external_action`) is
**Phases 8–10** — Phase 7 builds the graph skeleton + the read-only find-jobs path.

**7a done when:** `POST /ai/sessions` → `POST /ai/sessions/{id}/messages {"content":"find
jobs that match my experience"}` opens an SSE response that emits a `text` block + N
`job_card` blocks + `step`/`action` events + `done`; `agent_steps` + `ai_actions` rows are
persisted; `ai_sessions.status == "completed"`. All LLM / search / embedding calls go
through the fake providers — deterministic, no network.

---

## Global Constraints

- Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic (chain
  `…→0009_eval→0010_ai`, single head), `pydantic-settings`, `structlog`, `import-linter`,
  ARQ + Redis.
- **New deps** (verified installed + API-checked): `langgraph==1.2.11`,
  `langgraph-checkpoint-postgres==3.1.2`, and **`psycopg[binary]`** (the postgres
  checkpointer needs libpq — the binary wheel provides it on CI's Ubuntu). `uv.lock`
  regenerated. `langgraph` ships `py.typed`; add a `[[tool.mypy.overrides]]` for
  `langgraph.*` only if `mypy` actually complains.
  **Verified LangGraph API** (spike):
  - `StateGraph(ManaState)` with a `TypedDict` state; `Annotated[list, operator.add]`
    reducers accumulate across nodes (confirmed).
  - `g.add_node(name, fn)`, `g.set_entry_point(name)`,
    `g.add_conditional_edges(name, router_fn, {label_or_END: target_or_END})`,
    `g.add_edge(name, END)`, `g.compile(checkpointer=...)`.
  - `cg.astream(input, config={"configurable": {"thread_id": run_id}}, stream_mode="updates")`
    → async-iterates `{node_name: <partial state dict>}` once per super-step.
  - `snap = await cg.aget_state(config)` → `snap.values` is the merged final state dict.
  - `MemorySaver` is `from langgraph.checkpoint.memory import MemorySaver`.
  - **The Windows dev box has no libpq** → `from langgraph.checkpoint.postgres.aio import
    AsyncPostgresSaver` raises `ImportError` at import time. `checkpointer.py` therefore
    imports `AsyncPostgresSaver` **lazily**, inside `get_checkpointer`'s non-test branch —
    `import app.domain.agents.checkpointer`, `ruff`, `mypy app`, and `pytest --collect-only`
    must all succeed without libpq. CI (Ubuntu, `psycopg[binary]`) exercises the real saver.
- `LLM_PROVIDER=fake`, `EMBEDDINGS_PROVIDER=fake`, and the new `SEARCH_PROVIDER=fake` in
  CI and every test. `FakeLLMProvider` stubs structured output to empty; a
  `FakeSearchProvider` returns a deterministic canned result list. No live LLM / search
  / embedding call ever runs in CI.
- The LangGraph checkpointer: `get_checkpointer(settings)` returns an in-memory
  `MemorySaver` when `settings.env == "test"`, else an `AsyncPostgresSaver` on its own
  asyncpg pool against `DATABASE_URL`. `ensure_checkpointer_tables()` (idempotent) runs
  once in `WorkerSettings.on_startup` and is checked by `/health/ready`. LangGraph's
  checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
  `checkpoint_migrations`) are **library-owned — never Alembic-managed** (master spec
  D11).
- The graph runs in an **ARQ worker task** `run_agent(ctx, run_id)` (verbatim
  `_session_for` seam, F3 retry guard — same pattern as `score_match` / `ingest_job`).
- Graph math (`guard()`, the tool-cache hash, budget accounting, block assembly) is
  **pure** where it can be — no wall-clock in the hashable parts, `deadline_ts` is the
  one clock read and it's captured once at run start.
- `import-linter`: `app.domain.agents.*` is a `domain`-layer orchestrator — it may import
  `app.domain.{rag,matching,jobs,profile,skills,llm,embeddings}` service modules,
  `app.models.*`, `app.core.*` — **not** `app.api`, `app.worker`. The existing "Mana
  Career layered architecture" + "domain must not import api or worker" contracts cover
  it; `agents` is explicitly **not** leaf-ward (unlike `rag`). Cross-domain entry point:
  `app.domain.agents.service.AgentService`.
- All tuning values are module-level named constants.
- `/ai/*` routes land in the `"llm"` rate-limit bucket (master spec §6.5).

---

## 1. `backend/app/domain/agents/` module

### 1.1 `state.py`
```python
import operator
from typing import Annotated, Any, Literal, TypedDict

AgentGoal = Literal["understand_job", "enrich_job", "analyze_profile", "prepare_application"]

class Budget(TypedDict):
    max_steps: int
    steps_taken: int
    max_llm_calls: int
    llm_calls_made: int
    tool_call_caps: dict[str, int]      # {"web_search": 4, "vector_search": 6}
    tool_calls_made: dict[str, int]
    deadline_ts: float
    max_cost_usd: float
    cost_usd: float

class StepEvent(TypedDict):
    step_index: int
    node: str
    status: Literal["ok", "deduped", "skipped_fresh", "error", "budget_exceeded"]
    summary: str
    detail: dict[str, Any]
    llm_calls: int
    cost_usd: float
    duration_ms: int

class ManaState(TypedDict, total=False):
    run_id: str
    session_id: str
    user_id: str
    goal: AgentGoal
    inputs: dict[str, Any]
    # understand_job slice (Phase 7)
    retrieved_jobs: list[str]           # job ids, ranked
    match_refs: list[dict[str, str]]    # [{"job_id","match_id","status"}]
    skill_gap_summary: dict[str, Any]
    research_notes: list[str]           # company_research ids
    blocks: list[dict[str, Any]]        # ResponseBlock[] built by `respond`
    # prepare_application slice (Phases 8-10 — declared, unused now)
    tailored_resume_version_id: str | None
    cover_letter_id: str | None
    email_draft_id: str | None
    application_id: str | None
    approval: dict[str, Any] | None
    revise_count: int
    # control
    budget: Budget
    tool_cache: dict[str, Any]
    step_log: Annotated[list[StepEvent], operator.add]
    stop_requested: bool
    status: Literal["running", "completed", "rejected", "halted", "error"]
    error: str | None
```

### 1.2 `blocks.py` — the `ResponseBlock` discriminated union
Pydantic v2, `Field(discriminator="kind")`. Phase 7 emits the first three; the rest are
declared so later phases add fields without a migration of the `messages.blocks` shape.
```python
class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    markdown: str

class JobCardBlock(BaseModel):
    kind: Literal["job_card"] = "job_card"
    job_id: uuid.UUID
    match_id: uuid.UUID | None = None

class InsufficientInfoBlock(BaseModel):
    kind: Literal["insufficient_info"] = "insufficient_info"
    topic: str
    missing: list[str] = Field(default_factory=list)

# stubs — declared, not emitted in Phase 7
class MatchScoreBlock(BaseModel):   kind: Literal["match_score"] = "match_score";   match_id: uuid.UUID
class SkillGapBlock(BaseModel):     kind: Literal["skill_gap"] = "skill_gap";       match_id: uuid.UUID
class CareerRecommendationBlock(BaseModel): kind: Literal["career_recommendation"] = "career_recommendation"; roadmap_id: uuid.UUID
class LearningRecommendationBlock(BaseModel): kind: Literal["learning_recommendation"] = "learning_recommendation"; roadmap_id: uuid.UUID
class ResumeSuggestionBlock(BaseModel): kind: Literal["resume_suggestion"] = "resume_suggestion"; suggestion_id: uuid.UUID
class ApplicationDraftBlock(BaseModel): kind: Literal["application_draft"] = "application_draft"; application_id: uuid.UUID
class ApprovalActionBlock(BaseModel): kind: Literal["approval_action"] = "approval_action"; approval_id: uuid.UUID

ResponseBlock = Annotated[
    TextBlock | JobCardBlock | InsufficientInfoBlock | MatchScoreBlock | SkillGapBlock
    | CareerRecommendationBlock | LearningRecommendationBlock | ResumeSuggestionBlock
    | ApplicationDraftBlock | ApprovalActionBlock,
    Field(discriminator="kind"),
]

def dump_blocks(blocks: list[BaseModel]) -> list[dict]:  # -> messages.blocks jsonb
    return [b.model_dump(mode="json") for b in blocks]
```

### 1.3 `budget.py`
```python
DEFAULT_MAX_STEPS = 24
DEFAULT_MAX_LLM_CALLS = 12
DEFAULT_TOOL_CAPS = {"web_search": 4, "vector_search": 6}
DEFAULT_DEADLINE_SECONDS = 180
DEFAULT_MAX_COST_USD = 0.75

class BudgetExceeded(Exception):
    def __init__(self, reason: str) -> None: ...   # reason ∈ {"steps","deadline","cost","tool:<name>"}

def new_budget(*, now: float) -> Budget: ...        # captures deadline_ts = now + DEFAULT_DEADLINE_SECONDS

def check_budget(budget: Budget, *, now: float, tool: str | None = None) -> None:
    """Raise BudgetExceeded when steps_taken >= max_steps, now >= deadline_ts,
    cost_usd >= max_cost_usd, or (tool given) tool_calls_made[tool] >= tool_call_caps[tool]."""

def guard(node_name: str, fn: NodeFn) -> NodeFn:
    """Wrap a node: check_budget(now) → run fn(state) → merge the returned partial →
    increment steps_taken → append a StepEvent to step_log → return the partial +
    {"budget": <updated>, "step_log": [event]}. On BudgetExceeded: return
    {"status": "halted", "error": reason, "step_log": [<budget_exceeded event>]} and the
    graph routes to `halted`. On any other node exception: return
    {"status": "error", "error": str(exc), "step_log": [<error event>]} → `halted`.
    `stop_requested` true before a node → same as a `halted` with reason "stopped"."""
```
The tool-call cost + `llm_calls_made` are incremented inside the tool / LLM wrappers, not
`guard` — `guard` only reads them for the pre-node check and snapshots them into the
`StepEvent`.

### 1.4 `tools/registry.py`
```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    side_effecting: bool
    cap_key: str | None        # budget.tool_call_caps key, or None for uncapped

def tool_key(name: str, args: dict) -> str:
    return hashlib.sha256(f"{name}:{json.dumps(args, sort_keys=True, default=str)}".encode()).hexdigest()

async def call_tool(state: ManaState, spec: ToolSpec, args: dict, fn: Callable[..., Awaitable[Any]]) -> tuple[Any, str]:
    """Returns (result, disposition) where disposition ∈ {"ok","deduped"}.
      1. key = tool_key(spec.name, args); if key in state["tool_cache"] → return (cached, "deduped")
      2. check_budget(state["budget"], now=time.time(), tool=spec.cap_key) if cap_key
      3. result = await fn(**args)
      4. state["tool_cache"][key] = result ; budget.tool_calls_made[cap_key] += 1
      5. return (result, "ok")
    Side-effecting tools are unreachable in Phase 7 (no node calls one)."""
```
Registered specs: `vector_search` (side_effecting=False, cap_key="vector_search"),
`web_search` (False, "web_search"), `parse_pdf` (False, None — not used by any Phase-7
node; declared for Phase 8).

### 1.5 `tools/vector_search.py`
Thin wrapper over `app.domain.rag.service.RagService` — `async def vector_search(*,
session, embeddings, query: str, user_id: uuid.UUID, k: int = 10) -> list[dict]` returns
`[{"ref_id","source","section","score"}]` from `RagService.retrieve(...,
source=RetrievalSource.JOB_CHUNKS).blocks`. `k` clamped ≤ 20.

### 1.6 `tools/web_search.py`
`async def web_search(*, provider: SearchProvider, session, user_id, query: str,
company_domain: str | None) -> list[dict]` — calls `provider.search(query, k=5)`, wraps
each result body in an `<untrusted_data source="web" ref="…">` fence
(`app.domain.rag.context._neutralize` + fence), inserts a `company_research` row
(`source="web_research"`, `content=<fenced>`, `citations=[{url,title}]`, embedding via the
embeddings provider, `expires_at = now + 14d`), returns
`[{"research_id","url","title","snippet"}]`. Phase 7: reachable only from `job_research`.

### 1.7 `search/`
- `provider.py` — `class SearchProvider(Protocol): async def search(self, query: str, *, k: int = 5) -> list[SearchHit]` where `SearchHit = TypedDict{"url": str, "title": str, "content": str}`.
- `adapters/fake.py` — `FakeSearchProvider`: deterministic — hash the query to pick 2–3 canned hits from a small fixed table (company-ish blurbs). No network.
- `factory.py` — `get_search_provider(settings)`: `"fake"` → `FakeSearchProvider()`; `"tavily"` / `"brave"` → `NotImplementedError("… lands later")`. Default `"fake"`.
- `config.py` gains `search_provider: Literal["fake","tavily","brave"] = "fake"` and `search_api_key: SecretStr | None = None`.

### 1.8 `nodes/` — each `async def <node>(state: ManaState) -> dict` (partial update)
| Node | Phase-7 behaviour |
|---|---|
| `supervisor` | Deterministic router. Reads `state["goal"]`. `understand_job` → `job_retrieval`. `enrich_job` → `job_research`. `analyze_profile` / `prepare_application` → immediately `{"status":"halted","error":"not available yet"}` (Phases 3/8). Returns `{}` and the graph's conditional edge reads `state["goal"]` + a `_route` key it sets. |
| `job_research` | Iterative: up to `budget.tool_call_caps["web_search"]` `web_search` calls via `call_tool`; 1 LLM call to summarise into ≤3 `research_notes` (stored `company_research` ids). Only entered for `enrich_job` or when `inputs["company"]` is set. Fake search → deterministic. |
| `job_retrieval` | Deterministic. `query = inputs.get("query") or <profile summary>`; `hits = await vector_search(query=query, user_id=…, k=12)`; map `ref_id` → `job_id` (dedupe, keep order); also union `JobService.list_(user_id, JobFilters(sort="recent", limit=12))` when the retrieval is thin (< 5). `retrieved_jobs = <top 8 job ids>`. No LLM. |
| `match_analysis` | Deterministic. For each of `retrieved_jobs[:5]`: `ref = await MatchService(session).get_or_create(user_id, job_id)` (enqueues `score_match`, returns the row). `match_refs = [{"job_id","match_id","status"}]`. No blocking on the score; the FE polls. No LLM. |
| `skill_gap` | Deterministic. Reads `skill_gaps` rows already written for the *ready* matches (usually none yet on a fresh run) → a small `skill_gap_summary = {"top": [...], "counted": n}`. No LLM. (Real per-match gap rationale is Phase 5's worker; nothing to add here.) |
| `recommendation` | **Stub.** `{"blocks": []}` — appends nothing. (The RAG roadmap planner is Phase 12.) |
| `respond` | 1 LLM call (`FakeLLMProvider` → empty → a deterministic fallback string): a 1–2-sentence `TextBlock` framing the results ("Here are N roles that line up with your background."), then one `JobCardBlock{job_id, match_id}` per `match_refs`. If `retrieved_jobs` is empty → a single `InsufficientInfoBlock{topic:"job_match", missing:["a job corpus match", "a fuller profile"]}`. Writes the assistant `messages` row (`role="assistant"`, `content=<the text>`, `blocks=dump_blocks(...)`, `token_usage`, `model_id`, `provider`). Sets `status="completed"`. |
| `halted` | Terminal. Writes an `ai_actions` row (`status="warning"`, `summary=<error>`), an assistant `messages` row with a single `TextBlock` (a plain-language "I couldn't finish that — <reason>. Try again."), sets `ai_sessions.status` accordingly. |

Every node except `supervisor`/`halted` is wrapped by `guard(name, fn)` in `graph.py`.
Each node also emits an `ai_actions` row via `AgentService._log_action(...)` for its
user-facing summary (`job_retrieval` → "Searched your job corpus", `match_analysis` →
"Lined up 5 roles against your profile", etc.).

### 1.9 `graph.py`
```python
def build_graph(deps: AgentDeps) -> CompiledStateGraph:
    g = StateGraph(ManaState)
    g.add_node("supervisor", supervisor)
    for name, fn in [("job_research", job_research), ("job_retrieval", job_retrieval),
                     ("match_analysis", match_analysis), ("skill_gap", skill_gap),
                     ("recommendation", recommendation), ("respond", respond)]:
        g.add_node(name, guard(name, partial(fn, deps=deps)))
    g.add_node("halted", partial(halted, deps=deps))
    g.set_entry_point("supervisor")
    g.add_conditional_edges("supervisor", _route_from_supervisor,
        {"job_retrieval": "job_retrieval", "job_research": "job_research", "halted": "halted"})
    g.add_conditional_edges("job_research", _halt_or("job_retrieval"))
    g.add_conditional_edges("job_retrieval", _halt_or("match_analysis"))
    g.add_conditional_edges("match_analysis", _halt_or("skill_gap"))
    g.add_conditional_edges("skill_gap", _halt_or("recommendation"))
    g.add_conditional_edges("recommendation", _halt_or("respond"))
    g.add_edge("respond", END)
    g.add_edge("halted", END)
    return g.compile(checkpointer=deps.checkpointer)
```
`_halt_or(next_node)` returns `"halted"` when `state.get("status") in {"halted","error"}`,
else `next_node`. `AgentDeps` bundles `session` (the request/worker `AsyncSession`),
`llm`, `embeddings`, `search`, `checkpointer`, `publish` (a callback that pushes an SSE
event to the run's Redis channel).

### 1.10 `checkpointer.py`
```python
from langgraph.checkpoint.memory import MemorySaver   # safe — no libpq
# NB: do NOT import AsyncPostgresSaver at module top — libpq may be absent (dev box).

_saver = None  # process singleton (BaseCheckpointSaver | AbstractAsyncContextManager)

async def get_checkpointer(settings: Settings):
    global _saver
    if _saver is not None:
        return _saver
    if settings.env == "test":
        _saver = MemorySaver()
        return _saver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver   # lazy
    # from_conn_string returns an async CM; enter it once for the process lifetime.
    _cm = AsyncPostgresSaver.from_conn_string(_psycopg_dsn(settings))
    _saver = await _cm.__aenter__()
    return _saver

async def ensure_checkpointer_tables(settings: Settings) -> None:
    if settings.env == "test":
        return
    saver = await get_checkpointer(settings)
    await saver.setup()   # idempotent — creates the checkpoints* tables if absent
```
`_psycopg_dsn(settings)` — the psycopg (v3) DSN form: `settings.database_url` with the
`+asyncpg` driver token stripped (`postgresql://…`, not `postgresql+asyncpg://…`). The
implementer confirms `from_conn_string`'s exact contract against the installed
`langgraph_checkpoint.postgres.aio` module and adjusts (it is an async context manager in
3.1.2 — enter it once and keep the entered saver as the singleton; the process never
exits it, which is fine for a long-lived worker).

### 1.11 `service.py` — `AgentService`
```python
class AgentService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None: ...

    async def create_session(self, user_id, *, kind: Literal["chat","agent_run"] = "chat",
                             context: dict | None = None) -> AiSession: ...
    async def get_session(self, user_id, session_id) -> AiSession: ...           # NotFoundError
    async def list_sessions(self, user_id, *, limit, offset) -> tuple[list[AiSession], int]: ...
    async def add_user_message(self, user_id, session_id, content: str) -> Message: ...
    async def start_run(self, user_id, session_id, *, goal: AgentGoal, inputs: dict) -> str:
        """Set a fresh run_id, ai_sessions.status='running', budget snapshot; enqueue
        run_agent(run_id, _defer_by=1.0, _job_id=f'run_agent:{run_id}'); return run_id."""
    async def infer_goal(self, content: str) -> tuple[AgentGoal, dict]:
        """Phase 7: job-search-shaped ('find'/'match'/'jobs'/'roles' … heuristic regex) →
        ('understand_job', {'query': content}); else ('understand_job', {'query': content})
        still — respond() emits the insufficient-info block when nothing retrieves. (No
        real NLU until a later phase.)"""
    async def list_actions(self, user_id, *, session_id: uuid.UUID | None, limit, offset) -> tuple[list[AiAction], int]: ...
    async def stop_run(self, user_id, session_id) -> None:
        """Publish a 'stop' control message on the run channel; the guard picks it up
        (or the worker checks a Redis stop key before each node)."""

    # internal, used by nodes via AgentDeps
    async def _log_action(self, *, user_id, session_id, run_id, node, action_key,
                          summary, detail, entity_type=None, entity_id=None,
                          status="ok", latency_ms=None, cost_usd=None) -> None: ...
    async def _write_step(self, *, session_id, run_id, step: StepEvent) -> None: ...   # agent_steps row
```

---

## 2. `backend/app/worker/tasks/agent.py`

`run_agent(ctx: dict, run_id: str) -> dict` — mirrors `score_match`:
- verbatim `_session_for` copy; `log = get_logger("worker.run_agent")`.
- Load the `AiSession` by `run_id` (`select … where run_id == run_id`); `None` →
  `record_failure` + `return {"run_id": run_id, "status": "missing"}` (no raise).
- `try:` build `AgentDeps` (`get_llm_provider`, `get_embeddings_provider`,
  `get_search_provider`, `await get_checkpointer(settings)`, `publish` = a closure that
  `await redis.publish(f"sse:ai:{run_id}", json.dumps(event))`), build the initial
  `ManaState` (`budget = new_budget(now=time.time())`, `tool_cache={}`, `step_log=[]`,
  `status="running"`, `goal`/`inputs` from the session's stashed run config),
  `graph = build_graph(deps)`.
- `async for update in graph.astream(state, config={"configurable": {"thread_id": run_id}}, stream_mode="updates"):`
  — each `update` is `{node_name: partial}`. For each: `await deps.publish({"event":"step", ...})`
  from the partial's `step_log` entry; if the partial carries `blocks`, publish one
  `{"event":"block","block":<b>}` per new block; `await svc._write_step(...)` and
  `svc._log_action(...)` as the partial dictates.
- After the stream: read the final state via `graph.aget_state(config)`; set
  `ai_session.status = final["status"]`, `totals = {"tokens": …, "cost_usd": budget["cost_usd"], "steps": budget["steps_taken"]}`,
  `ended_at = now`; `await session.commit()`;
  `await deps.publish({"event":"done","status":final["status"],"totals":…})`.
- `except Exception as exc:` — F3: `session.rollback()` → `if ctx.get("job_try",1) < MAX_TRIES: raise`
  → reload the session → `status="error"`, `error=str(exc)[:500]` → `commit` →
  `publish({"event":"error", ...})` + `publish({"event":"done","status":"error"})` →
  `record_failure(...)` → `raise`.
- Registered in `WorkerSettings.functions`; `WorkerSettings.on_startup` also calls
  `await ensure_checkpointer_tables(get_settings())`.

---

## 3. Models + migration `0010_ai`

`backend/app/models/ai.py` (mirror `app/models/match.py` idiom):

- `AiSession(Base, TimestampMixin)` — table `ai_sessions`: `id` uuid pk; `user_id` FK
  users CASCADE; `kind` String(16) CHECK `('chat','agent_run')`; `goal` String(32) null;
  `title` String(200) null; `context` JSONB `'{}'`; `status` String(20) not null default
  `'idle'` CHECK `('idle','running','awaiting_approval','completed','rejected','halted','error')`;
  `run_id` String(64) null; `run_config` JSONB `'{}'` (stashed `{goal, inputs}` for the
  worker to pick up); `budget` JSONB `'{}'`; `totals` JSONB `'{}'`; `error` Text null;
  `started_at` timestamptz null; `ended_at` timestamptz null.
  `Index("ix_ai_sessions_user", "user_id", text("created_at DESC"))`, `("ix_ai_sessions_status","status")`,
  `("ix_ai_sessions_run","run_id")`.
- `Message(Base, TimestampMixin)` — table `messages`: `id`; `ai_session_id` FK
  ai_sessions CASCADE; `user_id` FK users CASCADE; `role` String(12) CHECK
  `('user','assistant','tool','system')`; `content` Text not null default `''`; `blocks`
  JSONB `'[]'`; `tool_calls` JSONB `'[]'`; `tool_call_id` String(64) null; `citations`
  JSONB `'[]'`; `token_usage` JSONB `'{}'`; `model_id` String(80) null; `provider`
  String(32) null. `Index("ix_messages_session", "ai_session_id", text("created_at"))`.
  (No `updated_at` trigger — append-only in practice, but `TimestampMixin` is kept for
  consistency.)
- `AiAction(Base, TimestampMixin)` — table `ai_actions`: `id`; `user_id` FK users
  CASCADE; `ai_session_id` uuid null (no FK — actions may outlive a session); `run_id`
  String(64) null; `node` String(40) not null; `action_key` String(60) not null;
  `summary` Text not null; `detail` JSONB `'{}'`; `entity_type` String(40) null;
  `entity_id` uuid null; `status` String(12) not null default `'ok'` CHECK
  `('ok','warning','error')`; `latency_ms` Integer null; `cost_usd` Numeric(8,4) null;
  `occurred_at` timestamptz not null server_default `now()`.
  `Index("ix_ai_actions_user", "user_id", text("occurred_at DESC"))`.
- `AgentStep(Base, TimestampMixin)` — table `agent_steps`: `id`; `ai_session_id` FK
  ai_sessions CASCADE; `run_id` String(64) not null; `step_index` Integer not null;
  `node` String(40) not null; `input_summary` JSONB `'{}'`; `output_summary` JSONB
  `'{}'`; `llm_calls` Integer not null default `0`; `tool_calls` JSONB `'{}'`;
  `tokens_in` Integer not null default `0`; `tokens_out` Integer not null default `0`;
  `cost_usd` Numeric(8,4) not null default `0`; `status` String(16) not null CHECK
  `('ok','deduped','skipped_fresh','error','budget_exceeded')`; `error` Text null;
  `started_at` timestamptz null; `ended_at` timestamptz null; `duration_ms` Integer null.
  `Index("ix_agent_steps_run", "run_id", "step_index")`.

`models/__init__.py` += `from app.models import ai as ai` (alpha — after `audit`, before
`auth`? no: `ai` < `audit` alphabetically, so `ai` is first).

Migration `0010_ai` — `revision="0010_ai"`, `down_revision="0009_eval"`. Four
`op.create_table` + `updated_at` triggers on `ai_sessions` and `agent_steps` only
(`set_updated_at()` exists). Downgrade drops `agent_steps` → `ai_actions` → `messages` →
`ai_sessions` (triggers first). **No `sa.Computed`, no generated columns.**

---

## 4. `/ai` API — `backend/app/api/v1/ai.py`

`router = APIRouter(prefix="/ai", tags=["ai"])`, every route `Depends(get_current_user)`.
Schemas in `app/api/v1/schemas/ai.py`, explicit mappers, no `from_attributes`.

- `POST /ai/sessions` — `SessionCreateIn{kind: Literal["chat","agent_run"] = "chat", context: dict | None = None}` → 201 `SessionOut`.
- `GET /ai/sessions` — `?limit=20&offset=0` → `SessionListOut{items, total}` (newest first).
- `GET /ai/sessions/{session_id}` — `SessionOut` or `NotFoundError`. Includes the last N `messages` (as `MessageOut[]`).
- `POST /ai/sessions/{session_id}/messages` — `MessageIn{content: str}` (1–4000 chars,
  `extra="forbid"`). Body flow: `svc.add_user_message(...)` → `(goal, inputs) =
  await svc.infer_goal(content)` → `run_id = await svc.start_run(..., goal=goal, inputs=inputs)`
  → **return `EventSourceResponse(_relay(redis, f"sse:ai:{run_id}"))`** — a streaming
  response that yields `open`, then `step` / `block` / `action` / `done` / `error` events
  from the Redis channel until `done`. (`_relay` = a thin variant of
  `app.core.events.status_stream` keyed on `event == "done"` as terminal.)
- `POST /ai/sessions/{session_id}/goal` — `GoalIn{goal: AgentGoal, inputs: dict}` (`extra="forbid"`)
  → `run_id = await svc.start_run(...)` → 202 `{run_id}`. (Fire-and-forget; client then
  opens `GET …/events`.)
- `GET /ai/sessions/{session_id}/events` — `?run_id=` optional (defaults to the session's
  current `run_id`) → `EventSourceResponse` on `sse:ai:{run_id}`. For reconnects / the
  goal path.
- `POST /ai/sessions/{session_id}/stop` — `await svc.stop_run(...)` → 202.
- `GET /ai/actions` — `?session_id=&limit=30&offset=0` → `AiActionListOut{items, total}`
  (user-scoped, newest first).

`router.py` — add `ai` to the import tuple (alpha — first) + `include_router(ai.router)`
before `auth.router`.

`rate_limit.py` `_bucket` — add: `if path.startswith(f"{base}/ai"): return "llm"` (covers
every `/ai/*` method; the SSE GET is cheap but admin-free and low-volume — acceptable in
the `llm` bucket).

---

## 5. Config + CI

- `app/core/config.py`: `search_provider: Literal["fake","tavily","brave"] = "fake"`,
  `search_api_key: SecretStr | None = None`. **No checkpointer config key** — `get_checkpointer`
  keys off `settings.env == "test"` (§1.10), which conftest already sets.
- `pyproject.toml`: `langgraph` + `langgraph-checkpoint-postgres` in `[project.dependencies]`;
  `uv lock` regenerated; a `[[tool.mypy.overrides]]` for `langgraph.*` if needed.
- CI: the existing `backend` job covers the new agent tests (fake providers + `MemorySaver`
  → no new service, no live network). No new CI job.

---

## 6. Phase 7b (frontend) — summary (its own plan)

- `lib/api/types.ts` — `AiSession`, `Message`, `AiAction`, `ResponseBlock` (mirror `blocks.py`), `AgentGoal`.
- `lib/api/endpoints.ts` — `api.ai` group: `createSession`, `listSessions`, `getSession`,
  `sendMessage` (returns the `Response` for SSE parsing — mirror `authedStream`),
  `startGoal`, `stopRun`, `listActions`.
- `lib/query.ts` — `qk.aiSessions`, `qk.aiSession(id)`, `qk.aiActions(q)`.
- `components/ai/blocks/` — `TextBlockView`, `JobCardBlockView` (wraps the Phase-4/5
  `JobCard` + `MatchBadge` — polls the score), `InsufficientInfoBlockView`; + `block-registry.ts`
  (`kind → component`, unknown kind → a muted fallback).
- `components/layout/ManaPanelDock.tsx` — a right-docked collapsible panel: message list
  (user bubbles + assistant blocks), an input, a suggested-prompt chip ("find jobs that
  match my experience"). Streams via `sendMessage` → parse SSE → append blocks as they
  arrive. Mounted in `AppShell`.
- `app/(app)/activity/page.tsx` — the AI Activity feed: `useQuery(qk.aiActions({}))` →
  a timeline of `AiAction` rows (node · summary · status pill · relative time), grouped
  by session. A "Try again" on `error`/`warning` rows that re-runs the session's goal.
- Nav: an "Activity" entry (`ready: true`, not admin-only).
- Tests: `endpoints.test.ts` extend; `tests/ai/mana-panel.test.tsx` (mock `sendMessage`
  to yield a canned SSE stream → assert a text block + a job card render);
  `tests/ai/activity-page.test.tsx`.

---

## 7. Out of scope (flag in the 7a completion report)

- `analyze_profile` / `prepare_application` graph paths (Phases 3 wrap / 8–10) —
  `supervisor` routes them straight to `halted` with "not available yet".
- `human_approval` interrupt, `email_external_action`, `send_email` tool, `/approvals` — Phase 10.
- Real roadmap planner in `recommendation` — Phase 12 (stub node now).
- Real search adapter (Tavily/Brave) — `NotImplementedError`; `FakeSearchProvider` only.
- Token-level LLM streaming (`event: "token"`) — Phase 7 emits whole `text` blocks; the
  SSE contract carries a `token` event type for a later pass.
- `messages` POST with an already-running session (queue/reject) — Phase 7 assumes one
  run at a time per session; a second `POST /messages` while `status=="running"` → 409.
- OTel spans across the graph — the `agent_steps` table + `ai_actions` are the Phase-7
  trace; OTel is Phase 13.
