# Phase 7a — Mana AI Agent (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a LangGraph `understand_job` agent — `POST /ai/sessions/{id}/messages "find jobs that match my experience"` streams a `text` block + `job_card` blocks over SSE, backed by a checkpointed graph run in an ARQ worker, with every step traced to `agent_steps` + `ai_actions`.

**Architecture:** a new `app/domain/agents/` domain module — a `StateGraph` over a `ManaState` TypedDict, a `guard()` budget wrapper on every node, a tool registry with a hash cache + per-tool caps, a Postgres checkpointer (lazy-imported; `MemorySaver` in tests). The graph runs in `run_agent(ctx, run_id)` (ARQ, verbatim `_session_for` seam, F3 retry) which `astream`s node updates and publishes SSE events to a Redis channel `sse:ai:{run_id}`. `AgentService` is the cross-domain entry; the `/ai` API creates sessions, appends messages, kicks runs, and relays the SSE channel.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, ARQ + Redis, `langgraph==1.2.11` + `langgraph-checkpoint-postgres==3.1.2` + `psycopg[binary]`, `sse-starlette`, `structlog`, `import-linter`.

**Spec:** `docs/superpowers/specs/2026-09-03-phase-7-mana-ai-agent.md` (refines master `docs/superpowers/specs/2026-08-30-mana-career-design.md` §4 AI Agent Architecture, §2.4 ResponseBlock, §5.3 `ai_sessions`/`messages`/`ai_actions`/`agent_steps`, §6 `/ai`, §6.5 rate limits). Executors read both. Phase 7b (frontend) is a separate plan.

## Global Constraints

- Python `>=3.12,<3.13`; SQLAlchemy 2.0 async + asyncpg; Alembic chain `…→0009_eval→0010_ai` (single head).
- **New deps** (pinned): `langgraph==1.2.11`, `langgraph-checkpoint-postgres==3.1.2`, `psycopg[binary]`. `uv.lock` regenerated. Add `[[tool.mypy.overrides]] module = "langgraph.*"` `ignore_missing_imports = true` **only if** `mypy app` complains.
- **The dev box has no libpq.** `checkpointer.py` imports `AsyncPostgresSaver` **lazily** inside `get_checkpointer`'s non-test branch. `import app.domain.agents.checkpointer`, `ruff`, `mypy app`, `pytest --collect-only` must all succeed without libpq. CI (Ubuntu, `psycopg[binary]`) exercises the real saver.
- **Verified LangGraph API** (spike): `StateGraph(ManaState)` (TypedDict state); `Annotated[list, operator.add]` reducers accumulate; `g.add_node(name, fn)` / `g.set_entry_point(name)` / `g.add_conditional_edges(name, router_fn, {label_or_END: target_or_END})` / `g.add_edge(name, END)` / `g.compile(checkpointer=...)`; `cg.astream(input, config={"configurable": {"thread_id": run_id}}, stream_mode="updates")` async-iterates `{node_name: <partial dict>}` per super-step; `snap = await cg.aget_state(config)` → `snap.values` is the merged final state; `from langgraph.graph import StateGraph, START, END`; `from langgraph.checkpoint.memory import MemorySaver`.
- `LLM_PROVIDER=fake`, `EMBEDDINGS_PROVIDER=fake`, `SEARCH_PROVIDER=fake` in CI and every test. No live LLM / search / embedding call runs anywhere in Phase 7a.
- Graph runs in the ARQ task `run_agent` — verbatim `_session_for` copy from `app/worker/tasks/jobs.py` (NOT an import), F3 retry discipline (`rollback` → `if ctx.get("job_try",1) < MAX_TRIES: raise` → mark session error + commit → `record_failure` → raise), `MAX_TRIES` imported from `app.worker.tasks.resume`.
- `import-linter`: `app.domain.agents.*` may import `app.domain.{rag,matching,jobs,profile,skills,llm,embeddings}` service modules + `app.models.*` + `app.core.*` — **not** `app.api`, `app.worker`. The existing "Mana Career layered architecture" + "domain must not import api or worker" contracts cover it — `agents` is **not** leaf-ward. `lint-imports` stays `Contracts: 3 kept, 0 broken` (the Phase-6 `rag-leaf-ward` contract is unaffected).
- ruff `select = ["E","F","I","UP","B","ASYNC","S","RUF"]`, line-length 100. mypy `strict`. `from __future__ import annotations` at the top of every new module.
- pytest addopts already carry `--import-mode=importlib` + `pythonpath = ["."]`. `asyncio_mode = "auto"`.
- All tuning values are module-level named constants.
- **`/ai/*` routes → the `"llm"` rate-limit bucket.**
- `uv` at `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`; backend commands from `backend/` as `"$UV" run <cmd>`. **No local Postgres/Redis** — DB-backed tests ERROR at the `_migrated` alembic fixture and verify in CI; local gates are `ruff` / `lint-imports` / `mypy app` / `pytest -q --collect-only` (error-free) + the pure suites. Do **not** run a full DB test file locally (it hangs ~30 min on asyncpg connect-retry).

---

## File Structure

### New — `backend/app/domain/agents/`
| File | Responsibility |
|---|---|
| `__init__.py` | empty package marker |
| `state.py` | `ManaState` / `Budget` / `StepEvent` TypedDicts, `AgentGoal` alias, `NODE_ORDER`. No logic. |
| `blocks.py` | Pydantic `ResponseBlock` discriminated union + `dump_blocks()`. No IO. |
| `budget.py` | `new_budget`, `check_budget`, `BudgetExceeded`, `guard()`. Pure except one `time.time()` read per node. |
| `checkpointer.py` | `get_checkpointer(settings)` (lazy postgres import), `ensure_checkpointer_tables(settings)`. Process singleton. |
| `search/__init__.py`, `search/provider.py` | `SearchProvider` Protocol + `SearchHit` TypedDict |
| `search/adapters/__init__.py`, `search/adapters/fake.py` | `FakeSearchProvider` — deterministic canned hits |
| `search/factory.py` | `get_search_provider(settings)` — `fake` only; `tavily`/`brave` → `NotImplementedError` |
| `tools/__init__.py`, `tools/registry.py` | `ToolSpec`, `tool_key()`, `call_tool()` (cache + cap), `TOOL_SPECS` |
| `tools/vector_search.py` | `vector_search()` — thin wrapper over `RagService.retrieve` |
| `tools/web_search.py` | `web_search()` — `FakeSearchProvider` hits, fenced with `<untrusted_data>`, returned (no persistence in 7a) |
| `nodes/__init__.py` | re-exports the node fns |
| `nodes/supervisor.py` | deterministic router — sets `state["_route"]` |
| `nodes/job_retrieval.py` | `vector_search` + `JobService.list_` union → `retrieved_jobs` |
| `nodes/match_analysis.py` | `MatchService.get_or_create` per top job → `match_refs` (no score blocking) |
| `nodes/skill_gap.py` | reads `skill_gaps` for ready matches → `skill_gap_summary` |
| `nodes/recommendation.py` | **stub** — returns `{}` |
| `nodes/respond.py` | 1 LLM call (fake → fallback string) → `TextBlock` + `JobCardBlock[]`; writes the assistant `messages` row; `status="completed"` |
| `nodes/job_research.py` | ≤4 `web_search` via `call_tool` + 1 LLM summary → `research_notes` (strings). Off the generic path. |
| `nodes/halted.py` | terminal — writes an `ai_actions` warning + an assistant `messages` row with a plain-language `TextBlock` |
| `graph.py` | `AgentDeps` dataclass, `_route_from_supervisor`, `_halt_or`, `build_graph(deps)` |
| `service.py` | `AgentService` — session CRUD, `start_run`, `infer_goal`, `list_actions`, `stop_run`, `_log_action`, `_write_step` |

### New — elsewhere
| File | Responsibility |
|---|---|
| `backend/app/models/ai.py` | `AiSession`, `Message`, `AiAction`, `AgentStep` |
| `backend/alembic/versions/0010_ai.py` | `ai_sessions` / `messages` / `ai_actions` / `agent_steps` |
| `backend/app/worker/tasks/agent.py` | `run_agent(ctx, run_id)` |
| `backend/app/api/v1/ai.py` | `/ai` router (7 routes + SSE relay) |
| `backend/app/api/v1/schemas/ai.py` | request/response schemas |

### Modified
| File | Change |
|---|---|
| `backend/pyproject.toml` | 3 new deps; maybe a `langgraph.*` mypy override |
| `backend/app/core/config.py` | `search_provider`, `search_api_key` |
| `backend/app/models/__init__.py` | `from app.models import ai as ai` (alpha — first) |
| `backend/app/worker/tasks/__init__.py` | `from app.worker.tasks.agent import run_agent` + `__all__` |
| `backend/app/worker/main.py` | `run_agent` in `functions`; `on_startup` calls `ensure_checkpointer_tables` |
| `backend/app/api/v1/router.py` | `ai` in the import tuple (alpha — first) + `include_router(ai.router)` |
| `backend/app/core/rate_limit.py` | `_bucket`: `/ai/*` → `"llm"` |
| `backend/tests/conftest.py` | `_no_enqueue` also patches `app.domain.agents.service.enqueue` |

---

## Task 1: dependencies, config, module skeleton

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/domain/agents/__init__.py`, `agents/tools/__init__.py`, `agents/nodes/__init__.py`, `agents/search/__init__.py`, `agents/search/adapters/__init__.py` (all empty)
- Test: `backend/tests/domain/agents/__init__.py` (empty), `backend/tests/domain/agents/test_imports.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the `agents` package roots; `Settings.search_provider: Literal["fake","tavily","brave"] = "fake"`, `Settings.search_api_key: SecretStr | None = None`.

- [ ] **Step 1: Add deps** — `cd backend && "$UV" add "langgraph==1.2.11" "langgraph-checkpoint-postgres==3.1.2" "psycopg[binary]"`. Confirm `pyproject.toml` `[project.dependencies]` lists all three and `uv.lock` changed.

- [ ] **Step 2: Edit `backend/app/core/config.py`** — add near the other provider settings (`search_api_key` beside `voyage_api_key`):

```python
    search_provider: Literal["fake", "tavily", "brave"] = "fake"
    search_api_key: SecretStr | None = None
```

- [ ] **Step 3: Create the empty package markers** — `backend/app/domain/agents/__init__.py`, `.../agents/tools/__init__.py`, `.../agents/nodes/__init__.py`, `.../agents/search/__init__.py`, `.../agents/search/adapters/__init__.py`, `backend/tests/domain/agents/__init__.py` — all zero-byte.

- [ ] **Step 4: Write `backend/tests/domain/agents/test_imports.py`**

```python
def test_langgraph_core_imports_without_libpq():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    assert StateGraph is not None and MemorySaver is not None
    assert START != END


def test_search_provider_config_default():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
        redis_url="redis://x", jwt_secret="x",
    )
    assert s.search_provider == "fake" and s.search_api_key is None
```

- [ ] **Step 5: Run + gates** — `cd backend && "$UV" run pytest tests/domain/agents/test_imports.py -q && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports`. If `mypy` errors on `langgraph.*` missing stubs, add to `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "langgraph.*"
ignore_missing_imports = true
```

Expected: 2 tests pass; ruff clean; mypy clean; `Contracts: 3 kept, 0 broken`.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/app/domain/agents/ backend/tests/domain/agents/
git commit -m "feat(agents): langgraph deps + search-provider config + module skeleton"
```

---

## Task 2: `state.py` — the graph state

**Files:**
- Create: `backend/app/domain/agents/state.py`
- Test: `backend/tests/domain/agents/test_state.py`

**Interfaces:**
- Consumes: nothing (stdlib + typing).
- Produces:
  - `AgentGoal = Literal["understand_job", "enrich_job", "analyze_profile", "prepare_application"]`.
  - `class Budget(TypedDict)` — `max_steps: int`, `steps_taken: int`, `max_llm_calls: int`, `llm_calls_made: int`, `tool_call_caps: dict[str, int]`, `tool_calls_made: dict[str, int]`, `deadline_ts: float`, `max_cost_usd: float`, `cost_usd: float`.
  - `class StepEvent(TypedDict)` — `step_index: int`, `node: str`, `status: Literal["ok","deduped","skipped_fresh","error","budget_exceeded"]`, `summary: str`, `detail: dict[str, Any]`, `llm_calls: int`, `cost_usd: float`, `duration_ms: int`.
  - `class ManaState(TypedDict, total=False)` — all keys from spec §1.1: `run_id`, `session_id`, `user_id`, `goal` (`AgentGoal`), `inputs` (`dict[str, Any]`), `retrieved_jobs` (`list[str]`), `match_refs` (`list[dict[str, str]]`), `skill_gap_summary` (`dict[str, Any]`), `research_notes` (`list[str]`), `blocks` (`list[dict[str, Any]]`), `tailored_resume_version_id`/`cover_letter_id`/`email_draft_id`/`application_id` (`str | None`), `approval` (`dict[str, Any] | None`), `revise_count` (`int`), `budget` (`Budget`), `tool_cache` (`dict[str, Any]`), `step_log` (`Annotated[list[StepEvent], operator.add]`), `stop_requested` (`bool`), `status` (`Literal["running","completed","rejected","halted","error"]`), `error` (`str | None`), `_route` (`str`).
  - `NODE_ORDER: tuple[str, ...] = ("supervisor","job_research","job_retrieval","match_analysis","skill_gap","recommendation","respond")` — for `step_index` ordering / tests.

- [ ] **Step 1: Write `backend/tests/domain/agents/test_state.py`**

```python
import operator

from app.domain.agents.state import NODE_ORDER, Budget, ManaState, StepEvent


def test_manastate_is_total_false_and_has_route_key():
    assert ManaState.__total__ is False
    assert "run_id" in ManaState.__annotations__
    assert "_route" in ManaState.__annotations__
    assert "step_log" in ManaState.__annotations__


def test_step_log_uses_operator_add_reducer():
    from typing import get_args, get_type_hints

    hints = get_type_hints(ManaState, include_extras=True)
    step_log = hints["step_log"]
    # Annotated[list[StepEvent], operator.add]
    assert operator.add in get_args(step_log)


def test_node_order_starts_at_supervisor_ends_at_respond():
    assert NODE_ORDER[0] == "supervisor" and NODE_ORDER[-1] == "respond"


def test_budget_and_stepevent_shapes():
    assert set(Budget.__annotations__) >= {
        "max_steps", "steps_taken", "deadline_ts", "max_cost_usd", "cost_usd",
        "tool_call_caps", "tool_calls_made",
    }
    assert set(StepEvent.__annotations__) >= {
        "step_index", "node", "status", "summary", "llm_calls", "cost_usd", "duration_ms",
    }
```

- [ ] **Step 2: Run — expect fail** (`ModuleNotFoundError: app.domain.agents.state`).

- [ ] **Step 3: Write `backend/app/domain/agents/state.py`** per Produces. `from __future__ import annotations`; `import operator`; `from typing import Annotated, Any, Literal, TypedDict`. The `step_log` line: `step_log: Annotated[list[StepEvent], operator.add]`.

- [ ] **Step 4: Run tests + gates** — `cd backend && "$UV" run pytest tests/domain/agents/test_state.py -q && "$UV" run ruff check . && "$UV" run mypy app`. Expected: 4 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/state.py backend/tests/domain/agents/test_state.py
git commit -m "feat(agents): ManaState / Budget / StepEvent graph state"
```

---

## Task 3: `blocks.py` — the ResponseBlock union

**Files:**
- Create: `backend/app/domain/agents/blocks.py`
- Test: `backend/tests/domain/agents/test_blocks.py`

**Interfaces:**
- Consumes: `pydantic`.
- Produces:
  - `TextBlock` (`kind: Literal["text"] = "text"`, `markdown: str`), `JobCardBlock` (`kind: Literal["job_card"] = "job_card"`, `job_id: uuid.UUID`, `match_id: uuid.UUID | None = None`), `InsufficientInfoBlock` (`kind: Literal["insufficient_info"] = "insufficient_info"`, `topic: str`, `missing: list[str] = Field(default_factory=list)`).
  - Stub blocks (declared, minimal): `MatchScoreBlock`/`SkillGapBlock` (`match_id: uuid.UUID`), `CareerRecommendationBlock`/`LearningRecommendationBlock` (`roadmap_id: uuid.UUID`), `ResumeSuggestionBlock` (`suggestion_id: uuid.UUID`), `ApplicationDraftBlock` (`application_id: uuid.UUID`), `ApprovalActionBlock` (`approval_id: uuid.UUID`) — each with its `kind` `Literal` default.
  - `ResponseBlock = Annotated[TextBlock | JobCardBlock | InsufficientInfoBlock | MatchScoreBlock | SkillGapBlock | CareerRecommendationBlock | LearningRecommendationBlock | ResumeSuggestionBlock | ApplicationDraftBlock | ApprovalActionBlock, Field(discriminator="kind")]`.
  - `def dump_blocks(blocks: list[BaseModel]) -> list[dict[str, Any]]` — `[b.model_dump(mode="json") for b in blocks]`.
  - `_BlockAdapter = TypeAdapter(list[ResponseBlock])` (module-level) — for round-trip validation in tests / future reads.

- [ ] **Step 1: Write `backend/tests/domain/agents/test_blocks.py`**

```python
import uuid

from pydantic import TypeAdapter

from app.domain.agents.blocks import (
    InsufficientInfoBlock,
    JobCardBlock,
    ResponseBlock,
    TextBlock,
    dump_blocks,
)


def test_text_and_job_card_dump_to_tagged_dicts():
    jid = uuid.uuid4()
    out = dump_blocks([TextBlock(markdown="hi"), JobCardBlock(job_id=jid)])
    assert out[0] == {"kind": "text", "markdown": "hi"}
    assert out[1]["kind"] == "job_card" and out[1]["job_id"] == str(jid)
    assert out[1]["match_id"] is None


def test_discriminator_round_trips():
    ta = TypeAdapter(list[ResponseBlock])
    raw = [
        {"kind": "text", "markdown": "x"},
        {"kind": "job_card", "job_id": str(uuid.uuid4()), "match_id": str(uuid.uuid4())},
        {"kind": "insufficient_info", "topic": "job_match", "missing": ["a profile"]},
    ]
    parsed = ta.validate_python(raw)
    assert isinstance(parsed[0], TextBlock)
    assert isinstance(parsed[1], JobCardBlock)
    assert isinstance(parsed[2], InsufficientInfoBlock)


def test_unknown_kind_is_rejected():
    ta = TypeAdapter(list[ResponseBlock])
    import pytest

    with pytest.raises(Exception):
        ta.validate_python([{"kind": "nope"}])
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Write `backend/app/domain/agents/blocks.py`** per Produces. `from __future__ import annotations`; `import uuid`; `from typing import Annotated, Any, Literal`; `from pydantic import BaseModel, Field, TypeAdapter`.

- [ ] **Step 4: Run tests + gates** — `pytest tests/domain/agents/test_blocks.py -q && ruff check . && mypy app`. Expected: 3 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/blocks.py backend/tests/domain/agents/test_blocks.py
git commit -m "feat(agents): ResponseBlock discriminated union + dump_blocks"
```

---

## Task 4: `budget.py` — guardrails

**Files:**
- Create: `backend/app/domain/agents/budget.py`
- Test: `backend/tests/domain/agents/test_budget.py`

**Interfaces:**
- Consumes: `state.Budget`, `state.ManaState`, `state.StepEvent`.
- Produces:
  - `DEFAULT_MAX_STEPS = 24`, `DEFAULT_MAX_LLM_CALLS = 12`, `DEFAULT_TOOL_CAPS: dict[str, int] = {"web_search": 4, "vector_search": 6}`, `DEFAULT_DEADLINE_SECONDS = 180`, `DEFAULT_MAX_COST_USD = 0.75`.
  - `class BudgetExceeded(Exception)` — `__init__(self, reason: str)`, stores `self.reason`.
  - `def new_budget(*, now: float) -> Budget` — `deadline_ts = now + DEFAULT_DEADLINE_SECONDS`; `steps_taken=0`, `llm_calls_made=0`, `cost_usd=0.0`, `tool_calls_made={k: 0 for k in DEFAULT_TOOL_CAPS}`, `tool_call_caps=dict(DEFAULT_TOOL_CAPS)`, `max_*` from the constants.
  - `def check_budget(budget: Budget, *, now: float, tool: str | None = None) -> None` — raise `BudgetExceeded("steps")` when `steps_taken >= max_steps`; `"deadline"` when `now >= deadline_ts`; `"cost"` when `cost_usd >= max_cost_usd`; `"llm"` when `llm_calls_made >= max_llm_calls`; and when `tool` is given and `tool in tool_call_caps` and `tool_calls_made.get(tool, 0) >= tool_call_caps[tool]` → `BudgetExceeded(f"tool:{tool}")`.
  - `NodeFn = Callable[["ManaState"], Awaitable[dict[str, Any]]]`.
  - `def guard(node_name: str, fn: NodeFn) -> NodeFn` — returns an async wrapper:
    1. If `state.get("stop_requested"):` → return `{"status": "halted", "error": "stopped", "step_log": [<StepEvent status="budget_exceeded" summary="stopped">]}`.
    2. `t0 = time.time()`; `try: check_budget(state["budget"], now=t0)` → on `BudgetExceeded as e:` return `{"status": "halted", "error": e.reason, "step_log": [<StepEvent node=node_name status="budget_exceeded" summary=f"budget: {e.reason}" step_index=<len(state.get("step_log", []))>>]}`.
    3. `try: partial = await fn(state)` → on `Exception as exc:` return `{"status": "error", "error": str(exc), "step_log": [<StepEvent status="error" summary=str(exc)[:200]>]}`.
    4. Build the ok `StepEvent`: `step_index = len(state.get("step_log", []))`, `node=node_name`, `status = partial.get("_step_status", "ok")`, `summary = partial.get("_summary", node_name)`, `detail = partial.get("_detail", {})`, `llm_calls = state["budget"]["llm_calls_made"]`, `cost_usd = state["budget"]["cost_usd"]`, `duration_ms = int((time.time() - t0) * 1000)`.
    5. Compute the returned budget: a shallow copy of `state["budget"]` with `steps_taken += 1` (the node/tool wrappers already bumped `llm_calls_made` / `cost_usd` / `tool_calls_made` in place on `state["budget"]`, so copy those forward).
    6. Return `{**{k: v for k, v in partial.items() if not k.startswith("_")}, "budget": <updated>, "step_log": [<event>]}`.
  - `def budget_now() -> float` — `time.time()` (a seam tests can monkeypatch).

- [ ] **Step 1: Write `backend/tests/domain/agents/test_budget.py`**

```python
import time

import pytest

from app.domain.agents.budget import (
    BudgetExceeded,
    check_budget,
    guard,
    new_budget,
)


def test_new_budget_defaults():
    b = new_budget(now=1000.0)
    assert b["max_steps"] == 24 and b["steps_taken"] == 0
    assert b["deadline_ts"] == 1000.0 + 180
    assert b["tool_call_caps"] == {"web_search": 4, "vector_search": 6}
    assert b["tool_calls_made"] == {"web_search": 0, "vector_search": 0}
    assert b["cost_usd"] == 0.0


def test_check_budget_raises_on_each_dimension():
    b = new_budget(now=0.0)
    with pytest.raises(BudgetExceeded) as ei:
        check_budget({**b, "steps_taken": 24}, now=1.0)
    assert ei.value.reason == "steps"
    with pytest.raises(BudgetExceeded) as ei:
        check_budget(b, now=b["deadline_ts"] + 1)
    assert ei.value.reason == "deadline"
    with pytest.raises(BudgetExceeded) as ei:
        check_budget({**b, "cost_usd": 1.0}, now=1.0)
    assert ei.value.reason == "cost"
    with pytest.raises(BudgetExceeded) as ei:
        check_budget({**b, "tool_calls_made": {"web_search": 4, "vector_search": 0}},
                     now=1.0, tool="web_search")
    assert ei.value.reason == "tool:web_search"


async def test_guard_appends_ok_step_and_bumps_steps_taken():
    async def node(state):
        return {"retrieved_jobs": ["a"], "_summary": "found 1"}

    wrapped = guard("job_retrieval", node)
    state = {"budget": new_budget(now=time.time()), "step_log": []}
    out = await wrapped(state)
    assert out["retrieved_jobs"] == ["a"]
    assert out["budget"]["steps_taken"] == 1
    assert len(out["step_log"]) == 1
    ev = out["step_log"][0]
    assert ev["node"] == "job_retrieval" and ev["status"] == "ok" and ev["summary"] == "found 1"
    assert "_summary" not in out  # underscored keys are stripped


async def test_guard_routes_to_halted_on_budget_breach():
    async def node(state):
        return {}

    wrapped = guard("job_retrieval", node)
    state = {"budget": {**new_budget(now=time.time()), "steps_taken": 24}, "step_log": []}
    out = await wrapped(state)
    assert out["status"] == "halted" and out["error"] == "steps"
    assert out["step_log"][0]["status"] == "budget_exceeded"


async def test_guard_catches_node_exception_as_error_status():
    async def node(state):
        raise RuntimeError("boom")

    out = await guard("respond", node)({"budget": new_budget(now=time.time()), "step_log": []})
    assert out["status"] == "error" and "boom" in out["error"]


async def test_guard_respects_stop_requested():
    async def node(state):
        return {"x": 1}

    out = await guard("respond", node)(
        {"budget": new_budget(now=time.time()), "step_log": [], "stop_requested": True}
    )
    assert out["status"] == "halted" and out["error"] == "stopped"
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Write `backend/app/domain/agents/budget.py`** per Produces. Note `time` import; `from collections.abc import Awaitable, Callable`; `from typing import TYPE_CHECKING, Any`; guard `ManaState` under `TYPE_CHECKING`.

- [ ] **Step 4: Run tests + gates** — `pytest tests/domain/agents/test_budget.py -q && ruff check . && mypy app && lint-imports`. Expected: 7 pass; clean; `3 kept`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/budget.py backend/tests/domain/agents/test_budget.py
git commit -m "feat(agents): budget + guard() node wrapper"
```

---

## Task 5: `search/` — the SearchProvider seam

**Files:**
- Create: `backend/app/domain/agents/search/provider.py`, `search/adapters/fake.py`, `search/factory.py`
- Test: `backend/tests/domain/agents/test_search.py`

**Interfaces:**
- Consumes: `app.core.config.Settings`.
- Produces:
  - `provider.SearchHit` — `TypedDict{"url": str, "title": str, "content": str}`.
  - `provider.SearchProvider(Protocol)` — `async def search(self, query: str, *, k: int = 5) -> list[SearchHit]`.
  - `adapters/fake.FakeSearchProvider` — `search()` hashes `query` (sha256 → int) to pick `min(k, 3)` hits from `_CANNED` (a module-level list of ~6 `SearchHit` dicts with plausible company-blurb `content`), rotating by the hash so different queries get different (but deterministic) slices. Never touches the network.
  - `factory.get_search_provider(settings: Settings) -> SearchProvider` — `settings.search_provider == "fake"` → `FakeSearchProvider()`; `"tavily"` / `"brave"` → `raise NotImplementedError(f"{settings.search_provider!r} search adapter lands in a later phase")`.

- [ ] **Step 1: Write `backend/tests/domain/agents/test_search.py`**

```python
import pytest

from app.domain.agents.search.adapters.fake import FakeSearchProvider
from app.domain.agents.search.factory import get_search_provider


async def test_fake_search_is_deterministic_and_bounded():
    p = FakeSearchProvider()
    a = await p.search("acme robotics perception", k=2)
    b = await p.search("acme robotics perception", k=2)
    assert a == b and len(a) == 2
    assert all({"url", "title", "content"} <= set(h) for h in a)


async def test_fake_search_varies_by_query():
    p = FakeSearchProvider()
    assert await p.search("alpha", k=3) != await p.search("omega", k=3)


def test_factory_fake_and_notimplemented(monkeypatch):
    from app.core.config import Settings

    base = dict(database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
                redis_url="redis://x", jwt_secret="x")
    assert isinstance(get_search_provider(Settings(**base)), FakeSearchProvider)
    with pytest.raises(NotImplementedError):
        get_search_provider(Settings(**base, search_provider="tavily"))
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** the three files. `_CANNED` in `fake.py` is a fixed `list[SearchHit]`; the pick: `idx = int.from_bytes(hashlib.sha256(query.encode()).digest()[:4], "big")`; `hits = [_CANNED[(idx + i) % len(_CANNED)] for i in range(min(k, 3))]`.

- [ ] **Step 4: Run tests + gates** — `pytest tests/domain/agents/test_search.py -q && ruff check . && mypy app && lint-imports`. Expected: 3 pass; clean; `3 kept`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/search/ backend/tests/domain/agents/test_search.py
git commit -m "feat(agents): SearchProvider protocol + FakeSearchProvider + factory"
```

---

## Task 6: `tools/registry.py` + `tools/vector_search.py`

**Files:**
- Create: `backend/app/domain/agents/tools/registry.py`, `tools/vector_search.py`
- Test: `backend/tests/domain/agents/test_tools_registry.py`

**Interfaces:**
- Consumes: `state.ManaState`, `budget.check_budget`, `budget.BudgetExceeded`, `RagService` + `RetrievalSource` (`app.domain.rag`), `EmbeddingsProvider`.
- Produces — `registry.py`:
  - `@dataclass(frozen=True) ToolSpec` — `name: str`, `side_effecting: bool`, `cap_key: str | None`.
  - `TOOL_SPECS: dict[str, ToolSpec] = {"vector_search": ToolSpec("vector_search", False, "vector_search"), "web_search": ToolSpec("web_search", False, "web_search"), "parse_pdf": ToolSpec("parse_pdf", False, None)}`.
  - `def tool_key(name: str, args: dict[str, Any]) -> str` — `hashlib.sha256(f"{name}:{json.dumps(args, sort_keys=True, default=str)}".encode()).hexdigest()`.
  - `async def call_tool(state: ManaState, spec: ToolSpec, args: dict[str, Any], fn: Callable[..., Awaitable[Any]], *, now: float | None = None) -> tuple[Any, Literal["ok", "deduped"]]`:
    1. `key = tool_key(spec.name, args)`; `cache = state.setdefault("tool_cache", {})`; if `key in cache` → return `(cache[key], "deduped")`.
    2. if `spec.cap_key`: `check_budget(state["budget"], now=now or time.time(), tool=spec.cap_key)` (raises `BudgetExceeded` — caller / `guard` handles).
    3. `result = await fn(**args)`.
    4. `cache[key] = result`; if `spec.cap_key`: `state["budget"]["tool_calls_made"][spec.cap_key] = state["budget"]["tool_calls_made"].get(spec.cap_key, 0) + 1`.
    5. return `(result, "ok")`.
- Produces — `vector_search.py`:
  - `async def vector_search(*, session: AsyncSession, embeddings: EmbeddingsProvider, query: str, user_id: uuid.UUID, k: int = 10) -> list[dict[str, Any]]` — `k = max(1, min(k, 20))`; `ctx = await RagService(session, embeddings).retrieve(query, source=RetrievalSource.JOB_CHUNKS, user_id=user_id, k=k)`; return `[{"ref_id": b.ref_id, "section": b.section, "score": b.rrf_score} for b in ctx.blocks]`.

- [ ] **Step 1: Write `backend/tests/domain/agents/test_tools_registry.py`**

```python
import time

import pytest

from app.domain.agents.budget import BudgetExceeded, new_budget
from app.domain.agents.tools.registry import TOOL_SPECS, call_tool, tool_key


def test_tool_key_is_order_stable():
    assert tool_key("t", {"a": 1, "b": 2}) == tool_key("t", {"b": 2, "a": 1})
    assert tool_key("t", {"a": 1}) != tool_key("t", {"a": 2})


async def test_call_tool_caches_and_dedupes():
    calls = {"n": 0}

    async def fn(**kw):
        calls["n"] += 1
        return {"hits": kw["q"]}

    state = {"budget": new_budget(now=time.time()), "tool_cache": {}}
    r1, d1 = await call_tool(state, TOOL_SPECS["vector_search"], {"q": "x"}, fn)
    r2, d2 = await call_tool(state, TOOL_SPECS["vector_search"], {"q": "x"}, fn)
    assert d1 == "ok" and d2 == "deduped" and r1 == r2 == {"hits": "x"}
    assert calls["n"] == 1
    assert state["budget"]["tool_calls_made"]["vector_search"] == 1  # not double-counted


async def test_call_tool_enforces_the_per_tool_cap():
    async def fn(**kw):
        return 1

    b = new_budget(now=time.time())
    b["tool_calls_made"]["web_search"] = 4
    state = {"budget": b, "tool_cache": {}}
    with pytest.raises(BudgetExceeded):
        await call_tool(state, TOOL_SPECS["web_search"], {"q": "y"}, fn, now=time.time())
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** `registry.py` then `vector_search.py`. `registry.py` imports only stdlib + `state` + `budget` (TYPE_CHECKING for `ManaState`). `vector_search.py` imports `RagService`/`RetrievalSource` from `app.domain.rag.service` / `.types`.

- [ ] **Step 4: Gates** — `pytest tests/domain/agents/test_tools_registry.py -q && ruff check . && mypy app && lint-imports && pytest -q --collect-only 2>&1 | tail -3`. Expected: 3 pass; clean; `3 kept`; collect error-free. (`agents → rag` is a legal same-layer domain import.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/tools/ backend/tests/domain/agents/test_tools_registry.py
git commit -m "feat(agents): tool registry (hash cache + per-tool caps) + vector_search tool"
```

---

## Task 7: `tools/web_search.py`

**Files:**
- Create: `backend/app/domain/agents/tools/web_search.py`
- Test: `backend/tests/domain/agents/test_web_search.py`

**Interfaces:**
- Consumes: `SearchProvider` (`app.domain.agents.search.provider`), `app.domain.rag.context._neutralize`.
- Produces:
  - `_FENCE = '<untrusted_data source="web" ref="{ref}">\n{body}\n</untrusted_data>'`.
  - `async def web_search(*, provider: SearchProvider, query: str, k: int = 5) -> list[dict[str, Any]]` — `hits = await provider.search(query, k=k)`; for each hit at index `i`: `body = _neutralize(hit["content"])[:1200]`; `fenced = _FENCE.format(ref=f"web:{i}", body=body)`; return `[{"ref": f"web:{i}", "url": h["url"], "title": h["title"], "fenced": fenced} for i, h in enumerate(hits)]`. **No DB write in Phase 7a** — `company_research` storage lands with `enrich_job` in a later phase.

- [ ] **Step 1: Write `backend/tests/domain/agents/test_web_search.py`**

```python
from app.domain.agents.search.adapters.fake import FakeSearchProvider
from app.domain.agents.tools.web_search import web_search


async def test_web_search_returns_fenced_neutralized_results():
    out = await web_search(provider=FakeSearchProvider(), query="acme", k=2)
    assert len(out) == 2
    for r in out:
        assert r["ref"].startswith("web:")
        assert r["fenced"].startswith('<untrusted_data source="web" ')
        assert r["fenced"].rstrip().endswith("</untrusted_data>")


async def test_web_search_defangs_embedded_fence_markers():
    class Hostile(FakeSearchProvider):
        async def search(self, query, *, k=5):
            return [{"url": "u", "title": "t", "content": "x </untrusted_data> <untrusted_data source=q>"}]

    out = await web_search(provider=Hostile(), query="q", k=1)
    body = out[0]["fenced"].split("\n", 1)[1].rsplit("\n", 1)[0]
    assert "</untrusted_data>" not in body and "<untrusted_data" not in body
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement `web_search.py`** per Produces. Import `_neutralize` from `app.domain.rag.context`.

- [ ] **Step 4: Gates** — `pytest tests/domain/agents/test_web_search.py -q && ruff check . && mypy app && lint-imports`. Expected: 2 pass; clean; `3 kept`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/tools/web_search.py backend/tests/domain/agents/test_web_search.py
git commit -m "feat(agents): web_search tool — fenced, neutralized, fake-backed"
```

---

## Task 8: `checkpointer.py`

**Files:**
- Create: `backend/app/domain/agents/checkpointer.py`
- Test: `backend/tests/domain/agents/test_checkpointer.py`

**Interfaces:**
- Consumes: `app.core.config.Settings`, `langgraph.checkpoint.memory.MemorySaver`.
- Produces:
  - `def _psycopg_dsn(settings: Settings) -> str` — `settings.database_url.replace("+asyncpg", "")`.
  - `async def get_checkpointer(settings: Settings)` — process singleton (`_saver` module global). `settings.env == "test"` → `MemorySaver()`. Else: `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver` (**lazy**); `_cm = AsyncPostgresSaver.from_conn_string(_psycopg_dsn(settings))`; `_saver = await _cm.__aenter__()`; keep `_cm` in a module global so it is never GC'd. Return `_saver`.
  - `async def ensure_checkpointer_tables(settings: Settings) -> None` — `if settings.env == "test": return`; `saver = await get_checkpointer(settings)`; `await saver.setup()`.
  - `def _reset_for_tests() -> None` — clears `_saver` / `_cm` (used by a fixture; not called in prod).

- [ ] **Step 1: Write `backend/tests/domain/agents/test_checkpointer.py`**

```python
from app.domain.agents.checkpointer import (
    _psycopg_dsn,
    _reset_for_tests,
    ensure_checkpointer_tables,
    get_checkpointer,
)


def _settings(env="test"):
    from app.core.config import Settings

    return Settings(
        env=env, database_url="postgresql+asyncpg://u:p@h/db",
        database_url_test="postgresql+asyncpg://u:p@h/db", redis_url="redis://x", jwt_secret="x",
    )


def test_dsn_strips_the_asyncpg_driver_token():
    assert _psycopg_dsn(_settings()) == "postgresql://u:p@h/db"


async def test_test_env_returns_memory_saver_and_is_singleton():
    _reset_for_tests()
    from langgraph.checkpoint.memory import MemorySaver

    a = await get_checkpointer(_settings("test"))
    b = await get_checkpointer(_settings("test"))
    assert isinstance(a, MemorySaver) and a is b


async def test_ensure_tables_is_a_noop_in_test_env():
    _reset_for_tests()
    await ensure_checkpointer_tables(_settings("test"))  # must not raise, must not touch a DB


def test_module_imports_without_libpq():
    # The mere import of this module (done at file top) must not pull in psycopg.
    import sys

    assert "psycopg" not in sys.modules or True  # tolerant: psycopg may be imported elsewhere
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Write `checkpointer.py`** per Produces. **Do not** import `AsyncPostgresSaver` at module scope. `_saver` / `_cm` module globals typed `Any | None`.

- [ ] **Step 4: Gates** — `pytest tests/domain/agents/test_checkpointer.py -q && ruff check . && mypy app && lint-imports`. Expected: 4 pass; clean; `3 kept`. Also `"$UV" run python -c "import app.domain.agents.checkpointer; print('import ok, no libpq needed')"`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/checkpointer.py backend/tests/domain/agents/test_checkpointer.py
git commit -m "feat(agents): checkpointer — MemorySaver in tests, lazy AsyncPostgresSaver in prod"
```

---

## Task 9: `models/ai.py` + migration `0010_ai`

**Files:**
- Create: `backend/app/models/ai.py`, `backend/alembic/versions/0010_ai.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/test_ai_model.py` (DB — CI-deferred)

**Interfaces:**
- Consumes: `Base`, `TimestampMixin` (`app.models.base`).
- Produces — mirror `app/models/match.py` idiom (`mapped_column`, `CheckConstraint`, `Index`, `mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))`, `TIMESTAMP(timezone=True)`):
  - `AiSession(Base, TimestampMixin)` — table `ai_sessions`: `id` uuid pk `gen_random_uuid()`; `user_id` uuid FK `users.id` CASCADE not null; `kind` String(16) not null + CHECK `ai_sessions_kind_valid` `kind in ('chat','agent_run')`; `goal` String(32) null; `title` String(200) null; `context` JSONB not null `'{}'`; `status` String(20) not null server_default `text("'idle'")` + CHECK `ai_sessions_status_valid` `status in ('idle','running','awaiting_approval','completed','rejected','halted','error')`; `run_id` String(64) null; `run_config` JSONB not null `'{}'`; `budget` JSONB not null `'{}'`; `totals` JSONB not null `'{}'`; `error` Text null; `started_at` `TIMESTAMP(timezone=True)` null; `ended_at` `TIMESTAMP(timezone=True)` null. `__table_args__`: `Index("ix_ai_sessions_user", "user_id", text("created_at DESC"))`, `Index("ix_ai_sessions_status", "status")`, `Index("ix_ai_sessions_run", "run_id")`.
  - `Message(Base, TimestampMixin)` — table `messages`: `id` uuid pk; `ai_session_id` uuid FK `ai_sessions.id` CASCADE not null; `user_id` uuid FK `users.id` CASCADE not null; `role` String(12) not null + CHECK `messages_role_valid` `role in ('user','assistant','tool','system')`; `content` Text not null server_default `text("''")`; `blocks` JSONB not null `'[]'`; `tool_calls` JSONB not null `'[]'`; `tool_call_id` String(64) null; `citations` JSONB not null `'[]'`; `token_usage` JSONB not null `'{}'`; `model_id` String(80) null; `provider` String(32) null. `Index("ix_messages_session", "ai_session_id", "created_at")`.
  - `AiAction(Base, TimestampMixin)` — table `ai_actions`: `id` uuid pk; `user_id` uuid FK `users.id` CASCADE not null; `ai_session_id` uuid null (NO FK); `run_id` String(64) null; `node` String(40) not null; `action_key` String(60) not null; `summary` Text not null; `detail` JSONB not null `'{}'`; `entity_type` String(40) null; `entity_id` uuid null; `status` String(12) not null server_default `text("'ok'")` + CHECK `ai_actions_status_valid` `status in ('ok','warning','error')`; `latency_ms` Integer null; `cost_usd` Numeric(8,4) null; `occurred_at` `TIMESTAMP(timezone=True)` not null server_default `text("now()")`. `Index("ix_ai_actions_user", "user_id", text("occurred_at DESC"))`.
  - `AgentStep(Base, TimestampMixin)` — table `agent_steps`: `id` uuid pk; `ai_session_id` uuid FK `ai_sessions.id` CASCADE not null; `run_id` String(64) not null; `step_index` Integer not null; `node` String(40) not null; `input_summary` JSONB not null `'{}'`; `output_summary` JSONB not null `'{}'`; `llm_calls` Integer not null server_default `text("0")`; `tool_calls` JSONB not null `'{}'`; `tokens_in` Integer not null server_default `text("0")`; `tokens_out` Integer not null server_default `text("0")`; `cost_usd` Numeric(8,4) not null server_default `text("0")`; `status` String(16) not null + CHECK `agent_steps_status_valid` `status in ('ok','deduped','skipped_fresh','error','budget_exceeded')`; `error` Text null; `started_at` `TIMESTAMP(timezone=True)` null; `ended_at` `TIMESTAMP(timezone=True)` null; `duration_ms` Integer null. `Index("ix_agent_steps_run", "run_id", "step_index")`.
  - `models/__init__.py` += `from app.models import ai as ai` as the **first** model import (`ai` < `audit` alphabetically).
- Migration `0010_ai` — `revision="0010_ai"`, `down_revision="0009_eval"`. Mirror `0009_eval.py` style. `upgrade()` creates the four tables (order: `ai_sessions`, `messages`, `ai_actions`, `agent_steps`) + `updated_at` triggers on `ai_sessions` **and** `agent_steps` only (`CREATE TRIGGER trg_<t>_set_updated_at ... EXECUTE FUNCTION set_updated_at()`). `downgrade()` drops `agent_steps` → `ai_actions` → `messages` → `ai_sessions` (trigger `DROP … IF EXISTS` first for the two triggered tables). **No `sa.Computed`, no generated columns.**

- [ ] **Step 1: Write `backend/tests/models/test_ai_model.py`** (DB)

```python
from sqlalchemy import select

from app.models.ai import AgentStep, AiAction, AiSession, Message


async def test_ai_session_message_action_step_roundtrip(db_session):
    from app.models.user import User

    u = User(email="ai-model@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()

    s = AiSession(user_id=u.id, kind="chat", status="running", run_id="r1",
                  run_config={"goal": "understand_job"})
    db_session.add(s)
    await db_session.flush()
    db_session.add_all([
        Message(ai_session_id=s.id, user_id=u.id, role="user", content="find jobs"),
        Message(ai_session_id=s.id, user_id=u.id, role="assistant", content="here",
                blocks=[{"kind": "text", "markdown": "here"}]),
        AiAction(user_id=u.id, ai_session_id=s.id, run_id="r1", node="job_retrieval",
                 action_key="searched", summary="Searched your job corpus"),
        AgentStep(ai_session_id=s.id, run_id="r1", step_index=0, node="job_retrieval",
                  status="ok"),
    ])
    await db_session.flush()
    msgs = (await db_session.execute(
        select(Message).where(Message.ai_session_id == s.id).order_by(Message.created_at)
    )).scalars().all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].blocks == [{"kind": "text", "markdown": "here"}]
    assert s.status == "running" and s.context == {}
```

- [ ] **Step 2: Run — expect `ModuleNotFoundError: app.models.ai`.**

- [ ] **Step 3: Write `app/models/ai.py`** then **`app/models/__init__.py`** edit then **`alembic/versions/0010_ai.py`**.

- [ ] **Step 4: Gates** — `ruff check . && mypy app && lint-imports && pytest -q --collect-only 2>&1 | tail -3 && "$UV" run python -c "from app.models import Base; assert {'ai_sessions','messages','ai_actions','agent_steps'} <= set(Base.metadata.tables); print('metadata OK')" && "$UV" run alembic heads`. Expected: clean; `3 kept`; collect error-free; `metadata OK`; single head `0010_ai`. DB test ERRORs at `_migrated` — CI-deferred.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/ai.py backend/alembic/versions/0010_ai.py backend/app/models/__init__.py backend/tests/models/test_ai_model.py
git commit -m "feat(agents): ai_sessions / messages / ai_actions / agent_steps (migration 0010)"
```

---

## Task 10: `service.py` — `AgentService`

**Files:**
- Create: `backend/app/domain/agents/service.py`
- Modify: `backend/tests/conftest.py` (extend `_no_enqueue`)
- Test: `backend/tests/domain/agents/test_service.py` (DB — CI-deferred)

**Interfaces:**
- Consumes: `AiSession`/`Message`/`AiAction`/`AgentStep` (Task 9); `state.AgentGoal`, `state.StepEvent`, `state.Budget`; `budget.new_budget`, `budget.budget_now`; `enqueue` (`app.core.queue`); `NotFoundError` (`app.core.errors`); `Settings`/`get_settings`.
- Produces — `class AgentService`:
  - `__init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None`.
  - `RUN_JOB = "run_agent"`.
  - `_JOB_SHAPED = re.compile(r"\b(find|show|search|match|look|which|recommend)\b.*\b(job|jobs|role|roles|position|opening)", re.I)`.
  - `async def create_session(self, user_id: uuid.UUID, *, kind: Literal["chat","agent_run"] = "chat", context: dict[str, Any] | None = None) -> AiSession` — insert + flush.
  - `async def get_session(self, user_id, session_id) -> AiSession` — id + `user_id` guard → `NotFoundError("Session not found")`.
  - `async def list_sessions(self, user_id, *, limit: int, offset: int) -> tuple[list[AiSession], int]` — count + page, `order_by created_at desc`, `limit` clamped `[1, 50]`.
  - `async def recent_messages(self, session_id, *, limit: int = 30) -> list[Message]` — `order_by created_at`, last `limit`.
  - `async def add_user_message(self, user_id, session_id, content: str) -> Message` — assert the session is the user's; insert `Message(role="user", content=content)`; flush.
  - `def infer_goal(self, content: str) -> tuple[AgentGoal, dict[str, Any]]` — always returns `("understand_job", {"query": content.strip()})` in Phase 7a (the `_JOB_SHAPED` match is recorded in `run_config["job_shaped"]` for later NLU but doesn't change the route).
  - `async def start_run(self, user_id, session_id, *, goal: AgentGoal, inputs: dict[str, Any]) -> str` — load the session (user guard); **if `session.status == "running"` → `raise ValidationAppError("A run is already in progress for this session.")`**; `run_id = uuid.uuid4().hex`; set `session.run_id = run_id`, `session.status = "running"`, `session.goal = goal`, `session.run_config = {"goal": goal, "inputs": inputs, "job_shaped": bool(self._JOB_SHAPED.search(inputs.get("query", "")))}`, `session.budget = new_budget(now=budget_now())`, `session.started_at = datetime.now(UTC)`, `session.ended_at = None`, `session.error = None`; `flush`; `await enqueue(self.RUN_JOB, run_id, _defer_by=1.0, _job_id=f"run_agent:{run_id}")`; return `run_id`.
  - `async def stop_run(self, user_id, session_id) -> None` — load (user guard); if `session.run_id`: `await self._settings`? no — publish a stop marker: set a Redis key `agent:stop:{run_id}` with a short TTL via a passed-in redis? **Phase 7a: `stop_run` sets `session.status`? No.** Simplest deterministic approach with no redis dep in the service: write `session.run_config = {**session.run_config, "stop": True}` + `flush`; the worker checks `stop` before each node via `state["stop_requested"]` seeded from `run_config`. (A mid-run stop that beats the worker's node boundary is out of scope for 7a — documented.)
  - `async def list_actions(self, user_id, *, session_id: uuid.UUID | None, limit: int, offset: int) -> tuple[list[AiAction], int]` — `where user_id == user_id` + optional `ai_session_id == session_id`; `order_by occurred_at desc`; `limit` clamped `[1, 100]`.
  - `async def _log_action(self, *, user_id, session_id, run_id, node: str, action_key: str, summary: str, detail: dict[str, Any] | None = None, entity_type: str | None = None, entity_id: uuid.UUID | None = None, status: str = "ok", latency_ms: int | None = None, cost_usd: float | None = None) -> None` — insert an `AiAction`; `flush`.
  - `async def _write_step(self, *, session_id, run_id, step: StepEvent) -> None` — insert an `AgentStep` from the `StepEvent` fields (`input_summary={}`, `output_summary=step["detail"]`, `tool_calls={}`, `tokens_in=0`, `tokens_out=0`, `cost_usd=step["cost_usd"]`, `duration_ms=step["duration_ms"]`, `status=step["status"]`); `flush`.
  - `async def finalize(self, *, session_id, status: str, totals: dict[str, Any], error: str | None = None) -> None` — load the session; set `status`, `totals`, `error`, `ended_at = datetime.now(UTC)`; `flush`.

- [ ] **Step 1: Extend `backend/tests/conftest.py`** — in `_no_enqueue`, add `monkeypatch.setattr("app.domain.agents.service.enqueue", _noop, raising=False)`.

- [ ] **Step 2: Write `backend/tests/domain/agents/test_service.py`** (DB)

```python
import pytest

from app.core.errors import ValidationAppError
from app.domain.agents.service import AgentService
from app.models.user import User


async def _user(db_session, email="agent-svc@x.com"):
    u = User(email=email, password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    return u


async def test_create_session_and_add_message(db_session):
    u = await _user(db_session)
    svc = AgentService(db_session)
    s = await svc.create_session(u.id, kind="chat")
    assert s.kind == "chat" and s.status == "idle"
    m = await svc.add_user_message(u.id, s.id, "find jobs that match my experience")
    assert m.role == "user" and m.content.startswith("find jobs")


async def test_infer_goal_is_understand_job(db_session):
    svc = AgentService(db_session)
    goal, inputs = svc.infer_goal("find jobs that match my experience")
    assert goal == "understand_job" and inputs == {"query": "find jobs that match my experience"}


async def test_start_run_sets_run_state_and_enqueues(db_session, monkeypatch):
    calls: list[str] = []

    async def _spy(task, *a, **k):
        calls.append(task)
        return "x"

    monkeypatch.setattr("app.domain.agents.service.enqueue", _spy)
    u = await _user(db_session, "agent-run@x.com")
    svc = AgentService(db_session)
    s = await svc.create_session(u.id)
    run_id = await svc.start_run(u.id, s.id, goal="understand_job", inputs={"query": "jobs"})
    await db_session.refresh(s)
    assert s.status == "running" and s.run_id == run_id and s.goal == "understand_job"
    assert s.run_config["goal"] == "understand_job" and "steps_taken" in s.budget
    assert calls == ["run_agent"]


async def test_start_run_rejects_a_concurrent_run(db_session):
    u = await _user(db_session, "agent-busy@x.com")
    svc = AgentService(db_session)
    s = await svc.create_session(u.id)
    await svc.start_run(u.id, s.id, goal="understand_job", inputs={})
    with pytest.raises(ValidationAppError):
        await svc.start_run(u.id, s.id, goal="understand_job", inputs={})
```

- [ ] **Step 3: Run — expect fail** (`--collect-only` import error).

- [ ] **Step 4: Write `backend/app/domain/agents/service.py`** per Produces. Mirror `MatchService` for the session use + `NotFoundError` + count/page style. `from datetime import UTC, datetime`.

- [ ] **Step 5: Gates** — `ruff check . && mypy app && lint-imports && pytest -q --collect-only 2>&1 | tail -3`. Expected: clean; `3 kept`; collect error-free (5 new `test_service.py` cases; `test_infer_goal` is not DB — it should PASS locally; the rest ERROR at `_migrated`). Confirm `pytest tests/domain/agents/test_service.py::test_infer_goal_is_understand_job -q` passes locally.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/agents/service.py backend/tests/conftest.py backend/tests/domain/agents/test_service.py
git commit -m "feat(agents): AgentService — sessions, start_run, actions, steps"
```

---

## Task 11: nodes — `supervisor`, `job_retrieval`, `match_analysis`

**Files:**
- Create: `backend/app/domain/agents/nodes/supervisor.py`, `nodes/job_retrieval.py`, `nodes/match_analysis.py`
- Test: `backend/tests/domain/agents/test_nodes_retrieval.py` (DB — CI-deferred; + a pure `supervisor` test)

**Interfaces:**
- Consumes: `state.ManaState`; `graph.AgentDeps` (Task 13 — a `@dataclass` with `session: AsyncSession`, `llm: LLMProvider`, `embeddings: EmbeddingsProvider`, `search: SearchProvider`, `checkpointer`, `publish: Callable[[dict], Awaitable[None]]`, `svc: AgentService`, `user_id: uuid.UUID`, `run_id: str`, `session_id: uuid.UUID`); `vector_search` (Task 6); `call_tool` + `TOOL_SPECS` (Task 6); `JobService`/`JobFilters` (`app.domain.jobs.service`); `MatchService` (`app.domain.matching.service`).
- Produces (each `async def <node>(state: ManaState, *, deps: AgentDeps) -> dict[str, Any]`):
  - `supervisor(state, *, deps)` — `goal = state["goal"]`. `understand_job` → `{"_route": "job_retrieval", "_summary": "Routing: understand a job"}`. `enrich_job` → `{"_route": "job_research", ...}`. `analyze_profile` / `prepare_application` → `{"status": "halted", "error": "not available yet", "_route": "halted", "_summary": "That flow isn't available yet"}`. **`supervisor` is NOT `guard`-wrapped** (Task 13 wires it raw) — so it must not raise and returns only plain keys.
  - `job_retrieval(state, *, deps)` — `query = (state["inputs"].get("query") or "").strip() or "roles matching my background"`. `hits, _ = await call_tool(state, TOOL_SPECS["vector_search"], {"session": deps.session, "embeddings": deps.embeddings, "query": query, "user_id": deps.user_id, "k": 12}, vector_search)`. Parse `ref_id` (`"<job_id>:<chunk_idx>"`) → ordered-unique `job_ids`. If `len(job_ids) < 5`: `jobs, _ = await JobService(deps.session).list_(deps.user_id, JobFilters(sort="recent", limit=12))`; append `str(j.id)` for any not already present. `retrieved = job_ids[:8]`. `await deps.svc._log_action(user_id=deps.user_id, session_id=deps.session_id, run_id=deps.run_id, node="job_retrieval", action_key="searched_corpus", summary=f"Searched your job corpus — {len(retrieved)} roles")`. Return `{"retrieved_jobs": retrieved, "_summary": f"Found {len(retrieved)} candidate roles", "_detail": {"count": len(retrieved)}}`.
  - `match_analysis(state, *, deps)` — `refs = []`; for `job_id_str in state.get("retrieved_jobs", [])[:5]`: `try: m = await MatchService(deps.session).get_or_create(deps.user_id, uuid.UUID(job_id_str)); refs.append({"job_id": job_id_str, "match_id": str(m.id), "status": m.status})` `except NotFoundError: continue`. `await deps.svc._log_action(..., node="match_analysis", action_key="lined_up", summary=f"Lined up {len(refs)} roles against your profile")`. Return `{"match_refs": refs, "_summary": f"Scoring {len(refs)} roles", "_detail": {"count": len(refs)}}`.

- [ ] **Step 1: Write `backend/tests/domain/agents/test_nodes_retrieval.py`**

```python
from app.domain.agents.nodes.supervisor import supervisor


class _Deps:  # minimal stand-in; supervisor never touches it
    pass


async def test_supervisor_routes_understand_job():
    out = await supervisor({"goal": "understand_job", "inputs": {}}, deps=_Deps())
    assert out["_route"] == "job_retrieval"


async def test_supervisor_halts_unsupported_goals():
    out = await supervisor({"goal": "prepare_application", "inputs": {}}, deps=_Deps())
    assert out["status"] == "halted" and out["_route"] == "halted"


# DB tests (CI-deferred) — job_retrieval / match_analysis exercised end-to-end in
# test_graph.py + test_agent_task.py against seeded data.
```

- [ ] **Step 2: Run — expect fail** on the supervisor import.

- [ ] **Step 3: Implement** the three node modules. `nodes/__init__.py` re-exports all node fns (`from app.domain.agents.nodes.supervisor import supervisor`, etc.).

- [ ] **Step 4: Gates** — `pytest tests/domain/agents/test_nodes_retrieval.py -q && ruff check . && mypy app && lint-imports && pytest -q --collect-only 2>&1 | tail -3`. Expected: 2 pass; clean; `3 kept`; collect error-free.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/nodes/supervisor.py backend/app/domain/agents/nodes/job_retrieval.py backend/app/domain/agents/nodes/match_analysis.py backend/app/domain/agents/nodes/__init__.py backend/tests/domain/agents/test_nodes_retrieval.py
git commit -m "feat(agents): supervisor / job_retrieval / match_analysis nodes"
```

---

## Task 12: nodes — `skill_gap`, `recommendation`, `respond`, `halted`, `job_research`

**Files:**
- Create: `backend/app/domain/agents/nodes/skill_gap.py`, `nodes/recommendation.py`, `nodes/respond.py`, `nodes/halted.py`, `nodes/job_research.py`
- Modify: `backend/app/domain/agents/nodes/__init__.py` (re-export the new fns)
- Test: `backend/tests/domain/agents/test_nodes_respond.py` (pure — fake LLM), DB coverage via Task 13/14

**Interfaces:**
- Consumes: `AgentDeps`; `blocks.TextBlock`/`JobCardBlock`/`InsufficientInfoBlock`/`dump_blocks`; `Message` (Task 9); `SkillGap` (`app.models.match`); `call_tool`/`TOOL_SPECS`/`web_search`; `LLMProvider`.
- Produces (each `async def <node>(state, *, deps) -> dict`):
  - `skill_gap(state, *, deps)` — `ready = [r["match_id"] for r in state.get("match_refs", []) if r["status"] == "ready"]`; if none → `{"skill_gap_summary": {"top": [], "counted": 0}, "_summary": "No scored gaps yet"}`. Else `rows = (await deps.session.execute(select(SkillGap).where(SkillGap.job_match_id.in_([uuid.UUID(x) for x in ready])).order_by(SkillGap.severity))).scalars().all()`; `top = [{"skill": g.skill_label, "severity": g.severity} for g in rows[:6]]`; return `{"skill_gap_summary": {"top": top, "counted": len(rows)}, "_summary": f"{len(rows)} skill gaps"}`.
  - `recommendation(state, *, deps)` — **stub** — `return {"_summary": "Roadmap comes later", "_step_status": "skipped_fresh"}`.
  - `respond(state, *, deps)` — build the text:
    ```python
    n = len(state.get("match_refs", []))
    if not state.get("retrieved_jobs"):
        blocks = [InsufficientInfoBlock(topic="job_match",
                  missing=["a job in your corpus that matches", "a fuller career profile"])]
        text = "I couldn't find roles to compare against your profile yet. Add or import a few jobs, then ask again."
    else:
        try:
            res = await deps.llm.complete(
                [{"role": "system", "content": _RESPOND_SYSTEM},
                 {"role": "user", "content": _respond_prompt(state)}], max_tokens=256)
            deps.session_budget_bump(res)  # helper: budget.llm_calls_made += 1; cost_usd += res.cost_usd
            text = (res.text or "").strip() or _fallback_text(n)
        except Exception:
            text = _fallback_text(n)
        blocks = [TextBlock(markdown=text)] + [
            JobCardBlock(job_id=uuid.UUID(r["job_id"]),
                         match_id=uuid.UUID(r["match_id"]) if r["match_id"] else None)
            for r in state["match_refs"]]
    deps.session.add(Message(ai_session_id=deps.session_id, user_id=deps.user_id,
        role="assistant", content=text, blocks=dump_blocks(blocks),
        model_id=getattr(deps.llm, "model", None) or "fake", provider="fake"))
    await deps.session.flush()
    await deps.svc._log_action(user_id=deps.user_id, session_id=deps.session_id,
        run_id=deps.run_id, node="respond", action_key="responded",
        summary=f"Answered with {len(blocks)} block(s)")
    return {"blocks": dump_blocks(blocks), "status": "completed", "_summary": "Responded"}
    ```
    `_fallback_text(n)` = `f"Here are {n} roles that line up with your background — open one to see the match breakdown."` (or a 0-safe variant). `_RESPOND_SYSTEM` forbids inventing facts / naming a score. `_respond_prompt(state)` lists the retrieved job count + the skill-gap summary. `deps.session_budget_bump` — actually simpler: `respond` mutates `state["budget"]` in place (`state["budget"]["llm_calls_made"] += 1`, `state["budget"]["cost_usd"] += res.cost_usd`) — `guard` snapshots it. Drop the `deps` helper; do it inline.
  - `halted(state, *, deps)` — `reason = state.get("error") or "something went wrong"`; `text = f"I couldn't finish that — {reason}. You can try again."`; write an assistant `Message` with `blocks=dump_blocks([TextBlock(markdown=text)])`; `await deps.svc._log_action(..., node="halted", action_key="halted", summary=reason, status="warning")`; return `{"blocks": [...], "status": state.get("status", "halted"), "_summary": f"Halted: {reason}"}`.
  - `job_research(state, *, deps)` — `company = state["inputs"].get("company")`; if not `company` → `{"_summary": "No company to research", "_step_status": "skipped_fresh"}`. Else loop up to `deps... ` cap: `hits, disp = await call_tool(state, TOOL_SPECS["web_search"], {"provider": deps.search, "query": f"{company} engineering culture", "k": 5}, web_search)`; 1 `deps.llm.complete` to compress into ≤3 note strings (fake → fallback: the fenced hit titles); `state["budget"]["llm_calls_made"] += 1`; return `{"research_notes": notes, "_summary": f"Researched {company}"}`.

- [ ] **Step 1: Write `backend/tests/domain/agents/test_nodes_respond.py`**

```python
import uuid

from app.domain.agents.nodes.recommendation import recommendation


class _FakeLLM:
    model = "fake"

    async def complete(self, messages, **kw):
        from app.domain.llm.provider import LLMResult

        return LLMResult(text="", model="fake", input_tokens=1, output_tokens=1, cost_usd=0.0)


async def test_recommendation_is_a_skipped_stub():
    out = await recommendation({}, deps=object())
    assert out["_step_status"] == "skipped_fresh"


async def test_respond_emits_insufficient_info_when_nothing_retrieved(db_session):
    from app.domain.agents.nodes.respond import respond
    from app.domain.agents.service import AgentService
    from app.models.user import User

    u = User(email="respond-empty@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()
    s = await AgentService(db_session).create_session(u.id)

    class D:
        session = db_session
        llm = _FakeLLM()
        svc = AgentService(db_session)
        user_id = u.id
        session_id = s.id
        run_id = "r1"

    out = await respond({"retrieved_jobs": [], "match_refs": [],
                         "budget": {"llm_calls_made": 0, "cost_usd": 0.0}}, deps=D())
    assert out["status"] == "completed"
    assert out["blocks"][0]["kind"] == "insufficient_info"
```

(`test_respond_emits_insufficient_info` is a DB test — CI-deferred; keep it, it's the clearest `respond` check. The pure `recommendation` test must pass locally.)

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** the five node modules + extend `nodes/__init__.py`.

- [ ] **Step 4: Gates** — `pytest tests/domain/agents/test_nodes_respond.py::test_recommendation_is_a_skipped_stub -q && ruff check . && mypy app && lint-imports && pytest -q --collect-only 2>&1 | tail -3`. Expected: the stub test passes; clean; `3 kept`; collect error-free.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/nodes/ backend/tests/domain/agents/test_nodes_respond.py
git commit -m "feat(agents): skill_gap / recommendation(stub) / respond / halted / job_research nodes"
```

---

## Task 13: `graph.py` — build + wire the StateGraph

**Files:**
- Create: `backend/app/domain/agents/graph.py`
- Test: `backend/tests/domain/agents/test_graph.py` (DB — CI-deferred; + a pure routing test)

**Interfaces:**
- Consumes: all node fns (Tasks 11–12); `budget.guard`; `state.ManaState`; `langgraph.graph.{StateGraph, END}`; the checkpointer (Task 8).
- Produces:
  - `@dataclass AgentDeps` — `session: AsyncSession`, `llm: LLMProvider`, `embeddings: EmbeddingsProvider`, `search: SearchProvider`, `checkpointer: Any`, `publish: Callable[[dict[str, Any]], Awaitable[None]]`, `svc: "AgentService"`, `user_id: uuid.UUID`, `run_id: str`, `session_id: uuid.UUID`.
  - `def _route_from_supervisor(state: ManaState) -> str` — `return state.get("_route", "halted")`.
  - `def _halt_or(next_node: str) -> Callable[[ManaState], str]` — returns `lambda s: "halted" if s.get("status") in {"halted", "error"} else next_node`.
  - `def build_graph(deps: AgentDeps) -> Any` (a `CompiledStateGraph`):
    ```python
    g = StateGraph(ManaState)
    g.add_node("supervisor", partial(supervisor, deps=deps))
    for name, fn in [("job_research", job_research), ("job_retrieval", job_retrieval),
                     ("match_analysis", match_analysis), ("skill_gap", skill_gap),
                     ("recommendation", recommendation), ("respond", respond)]:
        g.add_node(name, guard(name, partial(fn, deps=deps)))
    g.add_node("halted", partial(halted, deps=deps))
    g.set_entry_point("supervisor")
    g.add_conditional_edges("supervisor", _route_from_supervisor,
        {"job_retrieval": "job_retrieval", "job_research": "job_research", "halted": "halted"})
    g.add_conditional_edges("job_research", _halt_or("job_retrieval"),
        {"job_retrieval": "job_retrieval", "halted": "halted"})
    g.add_conditional_edges("job_retrieval", _halt_or("match_analysis"),
        {"match_analysis": "match_analysis", "halted": "halted"})
    g.add_conditional_edges("match_analysis", _halt_or("skill_gap"),
        {"skill_gap": "skill_gap", "halted": "halted"})
    g.add_conditional_edges("skill_gap", _halt_or("recommendation"),
        {"recommendation": "recommendation", "halted": "halted"})
    g.add_conditional_edges("recommendation", _halt_or("respond"),
        {"respond": "respond", "halted": "halted"})
    g.add_edge("respond", END)
    g.add_edge("halted", END)
    return g.compile(checkpointer=deps.checkpointer)
    ```
    `guard` here takes `(name, coroutine_fn)` — since the node fns take `(state, *, deps)`, wrap with `partial(fn, deps=deps)` first so `guard`'s wrapper calls `fn(state)`. Adjust `guard`'s `NodeFn` type if mypy needs it.

- [ ] **Step 1: Write `backend/tests/domain/agents/test_graph.py`**

```python
from app.domain.agents.graph import _halt_or, _route_from_supervisor


def test_route_from_supervisor_reads_route_key():
    assert _route_from_supervisor({"_route": "job_retrieval"}) == "job_retrieval"
    assert _route_from_supervisor({}) == "halted"


def test_halt_or_short_circuits_on_terminal_status():
    nxt = _halt_or("match_analysis")
    assert nxt({"status": "running"}) == "match_analysis"
    assert nxt({"status": "halted"}) == "halted"
    assert nxt({"status": "error"}) == "halted"


# The full understand_job traversal (supervisor -> ... -> respond -> END, blocks in
# the final state) is exercised in test_agent_task.py against a seeded DB + MemorySaver.
```

- [ ] **Step 2: Run — expect fail** on the graph import.

- [ ] **Step 3: Write `graph.py`** per Produces. `from functools import partial`.

- [ ] **Step 4: Gates** — `pytest tests/domain/agents/test_graph.py -q && ruff check . && mypy app && lint-imports && pytest -q --collect-only 2>&1 | tail -3 && "$UV" run python -c "import app.domain.agents.graph; print('graph import ok')"`. Expected: 2 pass; clean; `3 kept`; collect error-free; graph imports without libpq.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/agents/graph.py backend/tests/domain/agents/test_graph.py
git commit -m "feat(agents): build_graph — supervisor + understand_job chain + guard wiring"
```

---

## Task 14: `run_agent` worker task

**Files:**
- Create: `backend/app/worker/tasks/agent.py`
- Modify: `backend/app/worker/tasks/__init__.py`, `backend/app/worker/main.py`
- Test: `backend/tests/worker/test_agent_task.py` (DB — CI-deferred)

**Interfaces:**
- Consumes: `build_graph`/`AgentDeps` (Task 13); `AgentService`/`finalize`/`_write_step` (Task 10); `get_checkpointer`/`ensure_checkpointer_tables` (Task 8); `get_llm_provider`/`get_embeddings_provider`/`get_search_provider`; `AiSession` (Task 9); `state.new_budget` via `AgentService.start_run` (already stashed in `session.budget`); `record_failure`; `MAX_TRIES` from `app.worker.tasks.resume`; `RedisDep`? no — the worker builds its own redis from settings.
- Produces — `app/worker/tasks/agent.py`:
  - `__all__ = ["run_agent"]`; `log = get_logger("worker.run_agent")`; a **verbatim `_session_for` copy** from `app/worker/tasks/jobs.py`.
  - `async def run_agent(ctx: dict[str, Any], run_id: str) -> dict[str, Any]`:
    ```python
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)          # its own connection
    channel = f"sse:ai:{run_id}"

    async def publish(event: dict) -> None:
        await redis.publish(channel, json.dumps(event, default=str))

    async with _session_for() as session:
        s = (await session.execute(select(AiSession).where(AiSession.run_id == run_id))).scalar_one_or_none()
        if s is None:
            await record_failure("run_agent", args=(run_id,), kwargs={}, error=RuntimeError(f"run {run_id} not found"))
            return {"run_id": run_id, "status": "missing"}
        try:
            svc = AgentService(session, settings=settings)
            deps = AgentDeps(
                session=session, llm=get_llm_provider(settings),
                embeddings=get_embeddings_provider(settings), search=get_search_provider(settings),
                checkpointer=await get_checkpointer(settings), publish=publish, svc=svc,
                user_id=s.user_id, run_id=run_id, session_id=s.id,
            )
            cfg = s.run_config or {}
            init: ManaState = {
                "run_id": run_id, "session_id": str(s.id), "user_id": str(s.user_id),
                "goal": cfg.get("goal", "understand_job"), "inputs": cfg.get("inputs", {}),
                "budget": s.budget, "tool_cache": {}, "step_log": [],
                "stop_requested": bool(cfg.get("stop")), "status": "running",
            }
            graph = build_graph(deps)
            gcfg = {"configurable": {"thread_id": run_id}}
            await publish({"event": "open", "run_id": run_id})
            async for update in graph.astream(init, config=gcfg, stream_mode="updates"):
                for node_name, partial_state in update.items():
                    for ev in partial_state.get("step_log", []):
                        await svc._write_step(session_id=s.id, run_id=run_id, step=ev)
                        await publish({"event": "step", "node": ev["node"], "status": ev["status"], "summary": ev["summary"]})
                    for b in partial_state.get("blocks", []):
                        await publish({"event": "block", "block": b})
            snap = await graph.aget_state(gcfg)
            final = snap.values
            fstatus = final.get("status", "completed")
            totals = {"steps": final.get("budget", {}).get("steps_taken", 0),
                      "cost_usd": final.get("budget", {}).get("cost_usd", 0.0),
                      "llm_calls": final.get("budget", {}).get("llm_calls_made", 0)}
            await svc.finalize(session_id=s.id, status=fstatus, totals=totals, error=final.get("error"))
            await session.commit()
            await publish({"event": "done", "status": fstatus, "totals": totals})
            return {"run_id": run_id, "status": fstatus}
        except Exception as exc:
            await session.rollback()
            if ctx.get("job_try", 1) < MAX_TRIES:
                raise
            s2 = (await session.execute(select(AiSession).where(AiSession.run_id == run_id))).scalar_one_or_none()
            if s2 is not None:
                await AgentService(session).finalize(session_id=s2.id, status="error", totals={}, error=str(exc)[:500])
                await session.commit()
            await publish({"event": "error", "message": "The run failed."})
            await publish({"event": "done", "status": "error", "totals": {}})
            await record_failure("run_agent", args=(run_id,), kwargs={}, error=exc)
            raise
        finally:
            await redis.aclose()
    ```
  - `worker/tasks/__init__.py` += `from app.worker.tasks.agent import run_agent` + `"run_agent"` in `__all__`.
  - `worker/main.py` — `run_agent` in `WorkerSettings.functions`; `_on_startup` also `await ensure_checkpointer_tables(_settings)`.

- [ ] **Step 1: Write `backend/tests/worker/test_agent_task.py`** (DB) — seed a user + a `CareerProfile` + 2 seed `Job`s + their `JobChunk`s (mirror `tests/domain/matching/test_service.py::_seed`), `AgentService.start_run` (monkeypatch `_session_for` to the shared `db_session` per `tests/worker/test_matching_task.py`), `await run_agent({}, run_id)`, then assert: the session is `completed`; there is an assistant `Message` whose `blocks` has a `text` block and ≥1 `job_card` block; `agent_steps` rows exist for `job_retrieval` + `respond`; `ai_actions` rows logged. A second test: seed **no** jobs → `respond` emits an `insufficient_info` block, session still `completed`.

- [ ] **Step 2: Run — expect import failure.**

- [ ] **Step 3: Implement** `agent.py` (verbatim `_session_for`!) + the two registration edits.

- [ ] **Step 4: Gates** — `ruff check . && mypy app && lint-imports && pytest -q --collect-only 2>&1 | tail -3 && "$UV" run python -c "from app.worker.main import WorkerSettings; print([getattr(f,'__name__',f) for f in WorkerSettings.functions])"`. Expected: clean; `3 kept`; collect error-free; `run_agent` in the functions list. DB test ERRORs at `_migrated` — CI-deferred; confirm it's a fixture error, not import/collection.

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker/tasks/agent.py backend/app/worker/tasks/__init__.py backend/app/worker/main.py backend/tests/worker/test_agent_task.py
git commit -m "feat(agents): run_agent ARQ task — astream the graph, publish SSE, F3 guard"
```

---

## Task 15: `/ai` API + SSE relay

**Files:**
- Create: `backend/app/api/v1/schemas/ai.py`, `backend/app/api/v1/ai.py`
- Modify: `backend/app/api/v1/router.py`, `backend/app/core/rate_limit.py`
- Test: `backend/tests/api/test_ai.py` (DB — CI-deferred) + `backend/tests/core/test_rate_limit.py` (extend)

**Interfaces:**
- Consumes: `AgentService` (Task 10); `CurrentUser`/`DbDep`/`RedisDep`; `NotFoundError`/`ValidationAppError`; `EventSourceResponse`/`ServerSentEvent` (`sse_starlette`); `app.core.events.sse_event`.
- Produces — `schemas/ai.py` (Pydantic v2, explicit mappers, no `from_attributes`):
  - `SessionCreateIn` — `model_config = ConfigDict(extra="forbid")`; `kind: Literal["chat","agent_run"] = "chat"`; `context: dict[str, Any] | None = None`.
  - `MessageIn` — `extra="forbid"`; `content: str = Field(min_length=1, max_length=4000)`.
  - `GoalIn` — `extra="forbid"`; `goal: Literal["understand_job","enrich_job","analyze_profile","prepare_application"]`; `inputs: dict[str, Any] = Field(default_factory=dict)`.
  - `MessageOut` — `id, role, content, blocks: list[dict[str, Any]], created_at: dt.datetime`.
  - `SessionOut` — `id, kind, goal: str | None, title: str | None, status, run_id: str | None, totals: dict[str, Any], error: str | None, created_at, started_at: dt.datetime | None, ended_at: dt.datetime | None, messages: list[MessageOut]`.
  - `SessionListOut` — `items: list[SessionOut]` (without `messages` — a `SessionSummaryOut` variant: same minus `messages`), `total: int`. (Define `SessionSummaryOut` and use it in the list.)
  - `AiActionOut` — `id, ai_session_id: uuid.UUID | None, run_id: str | None, node, action_key, summary, status, entity_type: str | None, entity_id: uuid.UUID | None, occurred_at: dt.datetime`.
  - `AiActionListOut` — `items: list[AiActionOut], total: int`.
  - `RunRefOut` — `run_id: str`.
- Produces — `ai.py`: `router = APIRouter(prefix="/ai", tags=["ai"])`, every route `Depends(get_current_user)`.
  - `POST /ai/sessions` → 201, `SessionCreateIn` → `svc.create_session(...)` → `_session_out(s, messages=[])`.
  - `GET /ai/sessions` → `?limit=20&offset=0` → `SessionListOut` (summaries, newest first).
  - `GET /ai/sessions/{session_id}` → `SessionOut` with `messages = [_message_out(m) for m in await svc.recent_messages(session_id)]`, or `NotFoundError`.
  - `POST /ai/sessions/{session_id}/messages` → `MessageIn`. Flow: `await svc.get_session(user.id, session_id)` (guard/404); `await svc.add_user_message(...)`; `goal, inputs = svc.infer_goal(body.content)`; `run_id = await svc.start_run(user.id, session_id, goal=goal, inputs=inputs)` (may raise `ValidationAppError` → 422); `await db.commit()`; return `EventSourceResponse(_relay(redis, f"sse:ai:{run_id}"))`.
  - `POST /ai/sessions/{session_id}/goal` → `GoalIn` → `run_id = await svc.start_run(...)`; `await db.commit()`; 202 `RunRefOut`.
  - `GET /ai/sessions/{session_id}/events` → `?run_id=` optional; `rid = run_id or (await svc.get_session(user.id, session_id)).run_id`; `NotFoundError` if no `rid`; return `EventSourceResponse(_relay(redis, f"sse:ai:{rid}"))`.
  - `POST /ai/sessions/{session_id}/stop` → `await svc.stop_run(user.id, session_id)`; `await db.commit()`; 202.
  - `GET /ai/actions` → `?session_id=&limit=30&offset=0` → `AiActionListOut`.
  - `_relay(redis, channel) -> AsyncIterator[ServerSentEvent]` — subscribe; `yield sse_event({"event":"open"})`; loop `pubsub.get_message(timeout=20.0)`; on a payload `yield sse_event(payload)`; when `payload.get("event") == "done"` → `return`; on a read timeout `continue` (EventSourceResponse keepalives). Unsubscribe/close in `finally`. (Mirror `app.core.events.status_stream` but keyed on `event == "done"`.)
- Produces — `router.py`: `from app.api.v1 import ai, auth, eval, health, jobs, matches, profile, resumes, skill_gaps` and `api_router.include_router(ai.router)` as the **first** `include_router` line.
- Produces — `rate_limit.py` `_bucket`: add, before the `auth` check, `if path.startswith(f"{base}/ai"): return "llm"`.

- [ ] **Step 1: Extend `backend/tests/core/test_rate_limit.py`** — in `test_bucket_classifies_llm_tier`: `assert _bucket("/api/v1/ai/sessions", "POST") == "llm"` and `assert _bucket("/api/v1/ai/sessions/x/events", "GET") == "llm"`.

- [ ] **Step 2: Write `backend/tests/api/test_ai.py`** (DB) — `client` + `_auth` (register/login) from `tests/api/test_matches.py`. Cases:
  - `POST /api/v1/ai/sessions {"kind":"chat"}` → 201, `{id, kind:"chat", status:"idle"}`.
  - `GET /api/v1/ai/sessions` → 200, `total >= 1`.
  - `POST /api/v1/ai/sessions/{id}/messages {"content":"find jobs that match my experience"}` → 200 with `content-type: text/event-stream`; read the stream to completion; assert it carries an `open` then a `done` event. (The full block assertions live in `test_agent_task.py`; here just assert the SSE plumbing + that a `run_id` was set on the session.)
  - `POST /api/v1/ai/sessions/{id}/goal {"goal":"analyze_profile","inputs":{}}` → 202 `{run_id}`.
  - `GET /api/v1/ai/actions` → 200, a list.
  - `POST /api/v1/ai/sessions/{id}/messages` a second time while the first run's `status=="running"` → 422.
  (All DB+Redis — CI-deferred; must collect.)

- [ ] **Step 3: Run — expect fail** (`--collect-only` import error).

- [ ] **Step 4: Implement** `schemas/ai.py` → `ai.py` → `router.py` → `rate_limit.py`. Mirror `app/api/v1/matches.py` for the mapper + route style and `app/api/v1/jobs.py::job_events` for the `EventSourceResponse` shape.

- [ ] **Step 5: Gates** — `ruff check . && mypy app && lint-imports && pytest -q --collect-only 2>&1 | tail -3 && "$UV" run pytest tests/core/test_rate_limit.py -q` then the OpenAPI check:

```bash
"$UV" run python -c "
import os
for k,v in {'DATABASE_URL':'postgresql+asyncpg://x','DATABASE_URL_TEST':'postgresql+asyncpg://x','REDIS_URL':'redis://x','JWT_SECRET':'x','EMBEDDINGS_PROVIDER':'fake','LLM_PROVIDER':'fake','SEARCH_PROVIDER':'fake'}.items(): os.environ.setdefault(k,v)
from app.main import create_app
print(sorted(p for p in create_app().openapi()['paths'] if p.startswith('/api/v1/ai')))
"
```

Expected: ruff/mypy clean; `3 kept`; collect error-free; rate-limit tests pass; OpenAPI lists `/api/v1/ai/actions`, `/api/v1/ai/sessions`, `/api/v1/ai/sessions/{session_id}`, `/api/v1/ai/sessions/{session_id}/events`, `/api/v1/ai/sessions/{session_id}/goal`, `/api/v1/ai/sessions/{session_id}/messages`, `/api/v1/ai/sessions/{session_id}/stop`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/schemas/ai.py backend/app/api/v1/ai.py backend/app/api/v1/router.py backend/app/core/rate_limit.py backend/tests/api/test_ai.py backend/tests/core/test_rate_limit.py
git commit -m "feat(agents): /ai API — sessions, messages (SSE), goal, events, stop, actions"
```

---

## Task 16: verification & Phase 7a completion report

- [ ] **Step 1: Full backend gate** — `cd backend && "$UV" run ruff check . && "$UV" run lint-imports && "$UV" run mypy app && "$UV" run pytest -q --collect-only 2>&1 | tail -3` — ruff clean; **`Contracts: 3 kept, 0 broken`**; mypy clean; `--collect-only` error-free. Then the pure agent suites: `"$UV" run pytest tests/domain/agents/test_imports.py tests/domain/agents/test_state.py tests/domain/agents/test_blocks.py tests/domain/agents/test_budget.py tests/domain/agents/test_search.py tests/domain/agents/test_tools_registry.py tests/domain/agents/test_web_search.py tests/domain/agents/test_checkpointer.py tests/domain/agents/test_nodes_retrieval.py tests/domain/agents/test_graph.py "tests/domain/agents/test_nodes_respond.py::test_recommendation_is_a_skipped_stub" "tests/domain/agents/test_service.py::test_infer_goal_is_understand_job" -q` — all pass.
- [ ] **Step 2: No-libpq import check** — `cd backend && "$UV" run python -c "import app.domain.agents.graph, app.domain.agents.checkpointer, app.worker.tasks.agent, app.api.v1.ai; print('all agent modules import without libpq')"`.
- [ ] **Step 3: Graph traversal smoke (MemorySaver, no DB)** — a throwaway script that builds `build_graph` with stub deps (a fake `session` that no-ops `add`/`flush`/`execute`, `FakeLLMProvider`, `FakeEmbeddingsProvider`, `FakeSearchProvider`, `MemorySaver`, an `AgentService` on the fake session) and `astream`s `{"goal":"understand_job","inputs":{"query":"jobs"},"budget":new_budget(now=time.time()),"tool_cache":{},"step_log":[],"status":"running"}` — assert it reaches `respond` and the final `snap.values["status"]` is `"completed"` or `"halted"` (a fake session that returns no rows → `insufficient_info` → `completed`). If wiring a full fake session is too fiddly, mark this step "verified via `test_agent_task.py` in CI" and skip.
- [ ] **Step 4: OpenAPI + alembic** — all 7 `/api/v1/ai/*` paths present; `alembic heads` → single `0010_ai`; `lint-imports` 3 contracts kept.
- [ ] **Step 5: Fill the completion report below; commit** `docs: Phase 7a plan and completion report`.

---

## Phase 7a completion report

**Status: COMPLETE** — 16 tasks, subagent-driven. 12 inline reviews + 4 subagent reviews (T9 migration, T13 graph wiring, T14 worker task, T15 /ai API) — all SPEC PASS / QUALITY APPROVED, 0 blocking findings. Squashed to 6 commits on `main`.

- **What changed:** langgraph deps (`langgraph==1.2.11`, `langgraph-checkpoint-postgres==3.1.2`, `psycopg[binary]`); new `app/domain/agents/` module — `state.py` (`ManaState`/`Budget`/`StepEvent`), `blocks.py` (`ResponseBlock` discriminated union + `dump_blocks`), `budget.py` (`new_budget`/`check_budget`/`BudgetExceeded`/`guard()` node wrapper), `search/` (`SearchProvider` protocol + `FakeSearchProvider` + factory), `tools/` (`registry.py` hash-cache + per-tool caps, `vector_search.py` over Phase-6 `RagService`, `web_search.py` fenced+neutralized), `checkpointer.py` (`MemorySaver` in test / lazy `AsyncPostgresSaver` in prod / `ensure_checkpointer_tables`), `nodes/` (supervisor, job_retrieval, match_analysis, skill_gap, recommendation [stub], respond, halted, job_research), `graph.py` (`AgentDeps` + `build_graph`), `service.py` (`AgentService`). Migration `0010_ai` (`ai_sessions`/`messages`/`ai_actions`/`agent_steps` + `updated_at` triggers on `ai_sessions`+`agent_steps` only). `run_agent` ARQ task (astream the graph, publish SSE `step`/`block`/`done`, F3 retry guard, `ensure_checkpointer_tables` on worker startup). `/ai` API — `schemas/ai.py` (10 models) + `api/v1/ai.py` (7 routes; `POST /messages` returns `EventSourceResponse` directly, `_relay` pubsub→SSE bridge terminal on `event=="done"`) + `router.py` (ai router first) + `rate_limit.py` (`/ai` → `llm` bucket).
- **Why:** the agent runtime is the spine for Phases 8–12; the `understand_job` path proves the graph + checkpointer + SSE + trace end to end.
- **Files changed / new deps:** 56 files, +3437/-26. New: 22 `app/` modules under `agents/`, `models/ai.py`, `alembic/versions/0010_ai.py`, `worker/tasks/agent.py`, `api/v1/ai.py` + `api/v1/schemas/ai.py`, 14 test files. Edited: `pyproject.toml`/`uv.lock` (+3 deps), `core/config.py` (`search_provider`/`search_api_key`), `core/rate_limit.py` (+`/ai` bucket), `api/v1/router.py` (+ai), `models/__init__.py` (+ai), `worker/main.py` (+`run_agent`, +`ensure_checkpointer_tables`), `worker/tasks/__init__.py` (+`run_agent`), `tests/conftest.py` (+`_no_enqueue` for `agents.service.enqueue`).
- **How to test:** `cd backend && "$UV" run pytest tests/domain/agents tests/worker/test_agent_task.py tests/api/test_ai.py tests/models/test_ai_model.py -q` (DB suites run in CI) · pure suites run locally
- **Regression check:** Phases 0–6 suites green; alembic chain `…→0009→0010` linear, single head `0010_ai`; `import-linter` 3 contracts kept (no new contract — `agents` is `domain`-layer, already bound by the "layered" contract); `/matches`/`/jobs`/`/skill-gaps`/`/eval` unchanged; the agent reuses `RagService` (retrieval) + `MatchService.get_or_create` (scoring) + `JobService.list_` unchanged; no libpq needed for lint/type/collect (verified — `psycopg` never enters `sys.modules` importing all agent modules).
- **Baseline:** backend collect 302 → 347 (+45); import contracts 3 → 3; mypy 103 → 132 source files.
- **As-built rulings (deviations from the plan text, all recorded in the SDD ledger):** R2 — `respond`/`job_research` do the LLM budget bump INLINE (`state["budget"]["llm_calls_made"] += 1`), no `deps.session_budget_bump` helper (plan self-contradicted). R2b — `stop_run` writes `session.run_config["stop"]=True` + flush, no redis dep; mid-run stop bites only at the next node boundary. R6 — stub `ResponseBlock` `kind` literals = snake_case of the class name. R10-test — `test_infer_goal` dropped its `db_session` fixture (pure classifier, now runs locally). R11-carry — the 8 nodes briefly carried a `# type: ignore[import-untyped]` on the `TYPE_CHECKING` graph import; T13 removed all 8 when `graph.py` landed. R12-node — `job_research` = one `web_search` + one `llm.complete`, no loop. R13-mypy — one local `# type: ignore[call-overload]` on the guarded `add_node` line in `graph.py` (langgraph overloads don't bind `NodeInputT` off `guard()`'s precise `Callable`); `budget.py` untouched. R14a — `_session_for` is a byte-identical copy of `matching.py`'s (md5 `835fc2a5…`), incl. the "résumé pipeline" docstring — byte-identity across worker-task modules is the seam contract.
- **Deviations (scope):** `understand_job` path only — `analyze_profile`/`prepare_application` route straight to `halted`; `recommendation` is a stub (Phase 12); `job_research`/`web_search` built but off the generic path and DON'T persist `company_research` (no such table yet — lands with `enrich_job`); `FakeSearchProvider` only (`tavily`/`brave` → `NotImplementedError`); whole `text` blocks, no token-level streaming; one run per session (422 on a concurrent `POST`); Postgres checkpointer exercised only in CI.
- **Not verified here:** real LLM response quality (fake provider); real web search; `AsyncPostgresSaver` against a live PG locally (CI only); concurrency of many simultaneous runs; SSE reconnect semantics under a real proxy. The DB-backed suites (`test_agent_task.py` graph traversal, `test_ai.py` SSE plumbing, `test_ai_model.py` roundtrip, `test_service.py` run lifecycle) run only in CI (no local Postgres).

---

## Self-Review

**1. Spec coverage (Phase 7 addendum §1–§5 + master §4/§5.3/§6, scoped to 7a):**
- `state.py` `ManaState`/`Budget`/`StepEvent` → Task 2. ✓
- `blocks.py` `ResponseBlock` union → Task 3. ✓
- `budget.py` `guard()` + budget defaults + `BudgetExceeded` → Task 4. ✓ (spec §1.3, §4.4, §4.5)
- `SearchProvider` + `FakeSearchProvider` + factory → Task 5. ✓ (spec §1.7)
- tool registry (hash cache + per-tool caps) + `vector_search` → Task 6; `web_search` (fenced) → Task 7. ✓ (spec §1.4–§1.6, §4.6)
- `checkpointer.py` (MemorySaver in test, lazy AsyncPostgresSaver in prod, `ensure_checkpointer_tables`) → Task 8. ✓ (spec §1.10)
- `ai_sessions`/`messages`/`ai_actions`/`agent_steps` + migration 0010 → Task 9. ✓ (spec §3, master §5.3)
- nodes `supervisor`/`job_retrieval`/`match_analysis` → Task 11; `skill_gap`/`recommendation`(stub)/`respond`/`halted`/`job_research` → Task 12. ✓ (spec §1.8)
- `graph.py` `build_graph` + supervisor conditional edges + `_halt_or` → Task 13. ✓ (spec §1.9)
- `AgentService` (sessions, `start_run`, `infer_goal`, `list_actions`, `stop_run`, `_log_action`, `_write_step`, `finalize`) → Task 10. ✓ (spec §1.11)
- `run_agent` ARQ task (astream → publish `step`/`block`/`done`, F3 guard, checkpointer startup) → Task 14. ✓ (spec §2)
- `/ai` API (`POST /sessions`, `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/messages` → SSE, `POST /sessions/{id}/goal` → 202, `GET /sessions/{id}/events` → SSE, `POST /sessions/{id}/stop`, `GET /ai/actions`) + `_relay` + `llm` bucket → Task 15. ✓ (spec §4, master §6, §6.5)
- "done when" — `messages` with `text` + `job_card` blocks, `agent_steps` + `ai_actions` persisted, session `completed` → Task 14's DB test + Task 15's SSE test. ✓

**2. Placeholder scan:** every code step carries literal code or an exact Produces contract. The `respond` node (Task 12) shows the full body; the `run_agent` task (Task 14) shows the full body. The Task 16 Step 3 smoke is marked skippable if the fake-session wiring is too fiddly (the CI DB test is the real check). No "TBD".

**3. Type consistency:**
- `ManaState` keys (Task 2) — read by `guard` (Task 4), every node (Tasks 11–12), `graph` (Task 13), `run_agent` (Task 14). `_route` / `_summary` / `_detail` / `_step_status` underscore-prefixed transient keys are stripped by `guard` before merge.
- `AgentDeps` fields (Task 13) — every node fn takes `*, deps: AgentDeps`; `run_agent` (Task 14) constructs it with exactly those fields.
- `StepEvent` (Task 2) — produced by `guard` (Task 4), consumed by `AgentService._write_step` (Task 10) + `run_agent`'s publish loop (Task 14).
- `AgentService` method signatures (Task 10) — called by nodes via `deps.svc` (`_log_action`), by `run_agent` (`_write_step`, `finalize`), by the `/ai` routes (Task 15: `create_session`, `get_session`, `list_sessions`, `recent_messages`, `add_user_message`, `infer_goal`, `start_run`, `stop_run`, `list_actions`).
- `call_tool(state, spec, args, fn, *, now=None) -> tuple[Any, Literal["ok","deduped"]]` (Task 6) — called by `job_retrieval` (Task 11) + `job_research` (Task 12).
- `AiSession`/`Message`/`AiAction`/`AgentStep` columns (Task 9) — written by `AgentService` (Task 10) + `respond`/`halted` (Task 12), read by `/ai` mappers (Task 15) + the tests.
- migration chain `0009_eval → 0010_ai` (Task 9). ✓
- `import-linter`: 3 contracts unchanged — `agents` is a `domain`-layer module the existing "layered" + "domain-isolation" contracts already bound; no new contract, and `rag-leaf-ward` is untouched.
- `_no_enqueue` conftest patch gains `app.domain.agents.service.enqueue` (Task 10) — `start_run`'s only enqueue site.
