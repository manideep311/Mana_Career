# Phase 8 — Résumé tailoring — design addendum

**Parent spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` (§4.3 node catalog, §5.3 tables, §9 roadmap row 8, §12 open items).
**Prior phases on `main`:** 0–7 (agent runtime + frontend, CI green @ `67f0568`).

## 0. Goal (roadmap row 8)

> Tailor a base résumé to a specific job → a new `resume_versions` row (`kind="ai_tailored"`), a field-level diff the user can see, and a claim-validation pass that rejects any bullet not grounded in the base résumé / profile.

"Done when": `tailor_resume` goal on a job → new version, diff visible, no unsupported claims in `generation_meta.claim_validation`.

## Split

- **Phase 8a (backend, this plan first):** `generation` service · `ClaimValidator` · `DocumentRenderer` · `resume_tailoring` + `claim_validator` graph nodes + `tailor_resume` goal · models + migration `0011_resume_tailoring` · `/resumes/{id}/versions` + diff + tailor API.
- **Phase 8b (frontend, its own plan):** version diff view · `resume_suggestions` cards in the Résumé Workspace · nav/route touch-ups.

---

## Global Constraints

- Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic (chain `…→0010_ai→0011_resume_tailoring`, single head), `pydantic-settings`, `structlog`, `import-linter` (3 contracts — Phase 8 adds no new contract; `app.domain.generation` is a `domain`-layer service like `matching`/`rag`, may import `rag`/`resume`/`profile`/`jobs`/`llm`/`embeddings` + `models`/`core`, not `api`/`worker`), ARQ + Redis.
- **New deps** (verify installed + import-checked in Task 1): `markdown-it-py` (md → HTML, pure Python, deterministic), `weasyprint` **NOT used** — instead `xhtml2pdf` (pure-Python HTML→PDF, no system libs) for PDF, `python-docx` for DOCX. If `xhtml2pdf` import or render proves flaky on the Windows dev box, the renderer degrades to **Markdown + HTML only** (PDF/DOCX become a later polish item) — the node and the diff do NOT depend on binary rendering. Record the outcome.
- `LLM_PROVIDER=fake` / `EMBEDDINGS_PROVIDER=fake` / `SEARCH_PROVIDER=fake` in CI and every test. `FakeLLMProvider.complete(schema=X)` stubs structured fields to empty; the tailoring node's tests assert the *plumbing* (a version row is written, claim validation ran, `generation_meta` is populated), never LLM output quality.
- **No local Postgres/Redis** → DB-backed tests ERROR at the `tests/conftest.py` `_migrated` fixture and run only in CI. Local gates = `ruff` / `lint-imports` / `mypy app` / `pytest -q --collect-only` (error-free) + pure test suites.
- All tuning values are module-level named constants.
- Canonical structured résumé = the existing `app.domain.resume.extractor.ResumeExtraction` pydantic model (`full_name`, contacts, `summary`, `skills: list[str]`, `experiences`/`education`/`projects`/`certifications`). `resume_versions.content` stores `ResumeExtraction.model_dump(mode="json")`. Base and AI-tailored versions share this one type so the diff is field-level.
- The tailoring flow runs as an **agent goal** (`tailor_resume`) through the Phase-7a graph + worker + SSE + `ai_actions` trace — not a standalone REST worker task. A thin `POST /resumes/{id}/tailor {job_id}` convenience endpoint starts the run via `AgentService.start_run`.
- `/resumes/*` routes keep their existing rate-limit bucket; the new `tailor` POST lands in `"llm"`.

---

## 1. `backend/app/domain/generation/` — the generation service

The shared LLM-generation primitive Phases 8 & 9 both call. One module, small.

### 1.1 `types.py`
```python
@dataclass(frozen=True)
class GenerationMeta:
    model: str
    provider: str
    prompt_version: str
    prompt_hash: str            # sha256 of the fully-rendered prompt
    input_tokens: int
    output_tokens: int
    cost_usd: float
    claim_validation: dict[str, Any]   # ClaimReport.as_dict(); {} until claim_validator runs

@dataclass(frozen=True)
class GenerationResult:
    structured: dict[str, Any]  # schema-validated payload
    text: str                   # raw model text (may be "")
    meta: GenerationMeta
```

### 1.2 `service.py` — `GenerationService`
- `__init__(self, llm: LLMProvider, *, settings: Settings | None = None)`.
- `PROMPT_VERSION = "gen-1"` (module constant).
- `async def generate(self, *, system: str, user: str, schema: type[BaseModel], prompt_version: str, max_tokens: int = 1200) -> GenerationResult`
  - assembles `messages = [{"role":"system", system}, {"role":"user", user}]`,
  - `prompt_hash = sha256((prompt_version + "\n" + system + "\n" + user).encode()).hexdigest()`,
  - `res = await llm.complete(messages, schema=schema, max_tokens=max_tokens)`,
  - if `res.structured is None` → raise `GenerationError("model returned no structured payload")`,
  - `schema.model_validate(res.structured)` (raise `GenerationError` on `ValidationError`),
  - returns `GenerationResult(structured=<validated dump>, text=res.text or "", meta=GenerationMeta(... claim_validation={}))`.
- `class GenerationError(Exception)`.

**Tests (pure):** `generate` with `FakeLLMProvider(scripted=[...])` + a tiny schema → asserts `structured` is the validated dump, `meta.prompt_hash` is stable for the same inputs and changes when `user` changes, `meta.cost_usd == res.cost_usd`; `res.structured is None` path raises `GenerationError`.

---

## 2. `backend/app/domain/resume/tailoring.py` — the tailoring primitive + `ClaimValidator`

Kept in the `resume` domain (it reads/writes résumé structures). Two pieces.

### 2.1 `ClaimValidator` (deterministic — NOT an LLM)

Purpose: every *factual* line in the tailored résumé must be grounded in a **source span** drawn from the base résumé + the user's profile. Unsupported lines are rejected and fed back to the generator (≤2 reprompts).

```python
_MIN_SUPPORT = 0.60          # token-overlap ratio threshold
_STOPWORDS = frozenset({...}) # small, ~40 common English words + résumé filler

@dataclass(frozen=True)
class ClaimReport:
    checked: int
    unsupported: list[str]           # the offending rendered lines
    supported_ratio: float
    passed: bool                     # len(unsupported) == 0
    def as_dict(self) -> dict[str, Any]: ...

class ClaimValidator:
    def __init__(self, sources: list[str]) -> None:
        # sources = every profile highlight, experience/project description,
        # base-résumé bullet, skill label, cert name — flattened to strings.
        self._source_tokens = [self._norm(s) for s in sources if s.strip()]

    @staticmethod
    def _norm(s: str) -> frozenset[str]:
        # lowercase, strip punctuation, split on whitespace, drop stopwords + pure numbers-with-units? no:
        # keep numbers (they carry claims like "40% faster"); drop stopwords only.
        ...

    def _supported(self, claim: str) -> bool:
        ct = self._norm(claim)
        if not ct:
            return True                      # empty / structural line — not a claim
        best = max((len(ct & st) / len(ct) for st in self._source_tokens), default=0.0)
        return best >= _MIN_SUPPORT

    def check(self, tailored: ResumeExtraction) -> ClaimReport:
        # "claim lines" = every experiences[].highlights[], projects[].highlights[],
        # each non-empty experiences[].description / projects[].description sentence,
        # and summary sentences. Titles, company names, dates, skill list, education
        # institution/degree are NOT claim-checked (they are identity, not narrative)
        # — but if a highlight names a company/tech not in sources it still fails on
        # token overlap, which is the intent.
        ...
```

- `_MIN_SUPPORT`, `_STOPWORDS` are module constants.
- The validator is **pure + deterministic** — same inputs, same `ClaimReport`. No I/O.

**Tests (pure):** a tailored `ResumeExtraction` whose highlights are verbatim slices of the sources → `passed is True`, `unsupported == []`; a tailored version with one invented highlight ("Led a team of 50 across 4 continents") not in sources → `passed is False`, that line in `unsupported`; empty/whitespace highlight → not counted; a highlight that is a light paraphrase (≥60% token overlap) → supported.

### 2.2 `tailor_resume(...)` — the primitive the node calls
```python
_TAILOR_SYSTEM = (
  "You rewrite a candidate's résumé to fit a specific job. You may re-order, "
  "re-emphasise, and re-word existing achievements and skills. You must NOT "
  "invent employers, titles, dates, metrics, technologies, or accomplishments "
  "that are not already present in the provided base résumé and profile. Keep "
  "every bullet grounded in the source material. Return the full structured résumé."
)
_TAILOR_PROMPT_VERSION = "tailor-1"
MAX_CLAIM_REPROMPTS = 2

async def tailor_resume(
    *,
    gen: GenerationService,
    base: ResumeExtraction,
    profile_summary: str,     # a compact text rendering of CareerProfile + skills
    job_brief: str,           # title/company/description/required_skills, ≤ 6k chars
) -> tuple[ResumeExtraction, GenerationMeta]:
    sources = _collect_sources(base, profile_summary)
    validator = ClaimValidator(sources)
    user = _render_prompt(base, profile_summary, job_brief, rejected=None)
    for attempt in range(MAX_CLAIM_REPROMPTS + 1):
        res = await gen.generate(system=_TAILOR_SYSTEM, user=user,
                                 schema=ResumeExtraction, prompt_version=_TAILOR_PROMPT_VERSION,
                                 max_tokens=1600)
        tailored = ResumeExtraction.model_validate(res.structured)
        report = validator.check(tailored)
        meta = replace(res.meta, claim_validation=report.as_dict())
        if report.passed or attempt == MAX_CLAIM_REPROMPTS:
            return tailored, meta
        user = _render_prompt(base, profile_summary, job_brief, rejected=report.unsupported)
    # unreachable
```
- On the final attempt the last (possibly still-unsupported) version is returned with `claim_validation.passed == False` — the node records it, does NOT raise; the frontend surfaces the warning. (Never block the user's own résumé edit on a validator miss.)
- With `FakeLLMProvider` the structured payload is empty → `tailored` is an empty `ResumeExtraction`, `report.checked == 0`, `passed is True`. Tests assert the loop shape, not content.

---

## 3. `backend/app/domain/documents/renderer.py` — `DocumentRenderer`

Canonical `ResumeExtraction` → Markdown → { HTML, PDF, DOCX }.

```python
class RenderFormat(StrEnum):
    MD = "md"; HTML = "html"; PDF = "pdf"; DOCX = "docx"

@dataclass(frozen=True)
class RenderedDoc:
    fmt: RenderFormat
    media_type: str
    data: bytes

class DocumentRenderer:
    def to_markdown(self, r: ResumeExtraction) -> str: ...        # deterministic, template
    def to_html(self, r: ResumeExtraction) -> str: ...            # markdown-it-py over to_markdown + a minimal inline <style>
    def to_pdf(self, r: ResumeExtraction) -> bytes: ...           # xhtml2pdf over to_html; raises RenderUnavailable if the lib is missing/broken
    def to_docx(self, r: ResumeExtraction) -> bytes: ...          # python-docx, section by section
    def render(self, r: ResumeExtraction, fmt: RenderFormat) -> RenderedDoc: ...

class RenderUnavailable(RuntimeError): ...
```
- `to_markdown` and `to_html` are the load-bearing paths — always available, pure. `to_pdf`/`to_docx` may raise `RenderUnavailable`; callers (the version API) catch it and return the MD/HTML the client can print.
- Module constants for the résumé section order and the HTML `<style>`.
- **Tests (pure):** `to_markdown` of a small `ResumeExtraction` contains the name as an `# H1`, each company as `## `, highlights as `- `; round-trips stably; `to_html` contains `<h1>` and the name; `to_pdf` either returns `bytes` starting `b"%PDF"` or raises `RenderUnavailable` (test tolerates both — `pytest.raises((RenderUnavailable,)) or assert data[:4] == b"%PDF"`); `to_docx` returns a non-empty zip (`data[:2] == b"PK"`) or `RenderUnavailable`.

---

## 4. Nodes + goal wiring

### 4.1 `state.py` additions (Phase 7a `ManaState` already has the keys)
`ManaState` already declares `tailored_resume_version_id: str | None` and `revise_count`. Phase 8 adds the goal literal and node names.
- `AgentGoal` gains `"tailor_resume"`.
- `NODE_ORDER` gains `"resume_tailoring"`, `"claim_validator"` (informational; the graph wiring is explicit).

### 4.2 `nodes/resume_tailoring.py`
`async def resume_tailoring(state, *, deps) -> dict[str, Any]`
- `job_id = state["inputs"]["job_id"]` (the `tailor_resume` goal requires it; `AgentService.infer_goal` for this goal path pulls it from `inputs`).
- Load: the user's **primary confirmed résumé** (`ResumeService`), its `extraction` → `base: ResumeExtraction`; `ProfileService.load_full` → `profile_summary` (a `_summarise_profile(profile, skills)` helper, ≤ 1.5k chars); the job (`JobService.get`) → `job_brief` (`_summarise_job(job)`, ≤ 6k).
- If no confirmed résumé → return `{"status": "halted", "error": "no confirmed résumé to tailor", "_route": "halted", "_summary": "Add a résumé first"}` (supervisor-style; but this node IS guard-wrapped, so return the plain keys and let `_halt_or` route).
- `tailored, meta = await tailor_resume(gen=GenerationService(deps.llm), base=base, profile_summary=..., job_brief=...)`.
- **budget bump INLINE** (R2 from Phase 7a): `state["budget"]["llm_calls_made"] += 1 + <reprompts>`; `state["budget"]["cost_usd"] += meta.cost_usd`.
- Persist via `TailoringService.write_version(...)` (§5): a new `resume_versions` row `kind="ai_tailored"`, `content=tailored.model_dump(mode="json")`, `job_id=job_id`, `parent_version_id=<the base snapshot's id, created lazily>`, `generation_meta=asdict(meta)`, `created_by="mana_ai"`.
- `deps.svc._log_action(node="resume_tailoring", action_key="tailored_resume", summary=f"Tailored your résumé for {job.title} — {meta.claim_validation.get('checked',0)} claims checked")`.
- Return `{"tailored_resume_version_id": str(version.id), "_summary": "Tailored résumé draft ready", "_detail": {"claim_validation": meta.claim_validation}}`.

### 4.3 `nodes/claim_validator.py`
`async def claim_validator(state, *, deps) -> dict[str, Any]`
- Deterministic, no LLM. Re-loads the version written by `resume_tailoring` (`state["tailored_resume_version_id"]`), re-runs `ClaimValidator` over its `content` for an authoritative record (the node exists so the trace shows a discrete validation step and so a future path can re-validate a user-edited version).
- Writes `deps.svc._log_action(node="claim_validator", action_key="validated_claims", summary=<"All N claims grounded" | "M of N claims need a source">, status="ok" | "warning")`.
- Updates the version's `generation_meta.claim_validation` if it changed (it won't, first pass — kept for the edit path).
- Return `{"_summary": <same>, "_step_status": "ok"}`. Never halts.

### 4.4 `graph.py` wiring
`build_graph` gains: `supervisor` routes `goal == "tailor_resume"` → `resume_tailoring`. Chain: `resume_tailoring` → `_halt_or("claim_validator")` → `claim_validator` → `_halt_or("respond")` → `respond`.
`respond` (Phase 7a) already emits a `TextBlock` + block list; Phase 8 adds a `ResumeSuggestionBlock` case (the stub kind already exists in `blocks.py`) carrying `{ "suggestion_id": <version_id>, "kind": "resume_suggestion" }` — reused as "a tailored résumé version is ready" — plus a `TextBlock` summary line. (A dedicated `ResumeVersionBlock` is 8b's call; the stub carries the id now.)

### 4.5 `AgentService.infer_goal` / `start_run`
`infer_goal` stays `("understand_job", …)` for free-text. The `tailor_resume` goal is only reachable via `POST /ai/sessions/{id}/goal {goal:"tailor_resume", inputs:{job_id}}` or the convenience `POST /resumes/{id}/tailor {job_id}` (which calls `start_run(..., goal="tailor_resume", inputs={"job_id": job_id, "resume_id": id})`).

---

## 5. Models + migration `0011_resume_tailoring`

`app/models/resume_version.py` (new module; `models/__init__` imports it after `resume`).

### `resume_versions`
`id` uuid pk `gen_random_uuid()` · `user_id` FK `users.id` CASCADE not null · `resume_id` FK `resumes.id` CASCADE not null · `job_id` uuid null (no FK — a job may be deleted) · `application_id` uuid null · `parent_version_id` uuid null (self-ref, no FK constraint to avoid cascade tangle) · `label` String(120) null · `kind` String(16) not null + CHECK `resume_versions_kind_valid` `kind in ('base_snapshot','manual_edit','ai_tailored')` · `content` JSONB not null `'{}'` · `rendered_refs` JSONB not null `'{}'` · `generation_meta` JSONB not null `'{}'` · `created_by` String(16) not null server_default `text("'user'")` + CHECK `in ('user','mana_ai')` · `TimestampMixin`. Indexes: `ix_resume_versions_resume` (`resume_id`, `created_at DESC`), `ix_resume_versions_user` (`user_id`), `ix_resume_versions_job` (`job_id`). `updated_at` trigger.

### `resume_chunks` *(vector — declared now, populated later)*
`id` · `resume_version_id` FK CASCADE not null · `owner_id` uuid not null · `chunk_index` int not null · `section` String(40) not null · `ref_id` String(80) null · `content` Text not null · `token_count` int not null server_default `0` · `embed_model` String(80) not null · `embed_dim` int not null · `embedding` `Vector(1024)` null · `tsv` `TSVECTOR` null · created_at (no `TimestampMixin` — append-only chunk). Indexes: HNSW on `embedding` (`vector_cosine_ops`), GIN on `tsv`, `ix_resume_chunks_version` (`resume_version_id`, `chunk_index`). **No generated columns** — `tsv` is populated by the (future) indexer, not `Computed` (Phase-4 CI-red class). Phase 8 writes NO rows here; it exists so 8b/Phase 12 retrieval has the table.

### `resume_suggestions`
`id` · `user_id` FK CASCADE not null · `resume_version_id` FK `resume_versions.id` CASCADE not null · `section` String(40) not null · `target_ref_id` String(80) null · `suggestion_type` String(24) not null · `title` String(200) not null · `body` Text not null · `proposed_change` JSONB not null `'{}'` · `status` String(12) not null server_default `text("'open'")` + CHECK `in ('open','accepted','edited','dismissed')` · `resulting_version_id` uuid null · `source` String(16) not null server_default `text("'mana_ai'")` · `generation_meta` JSONB not null `'{}'` · `TimestampMixin`. Index `ix_resume_suggestions_user` (`user_id`, `created_at DESC`), `ix_resume_suggestions_version` (`resume_version_id`). `updated_at` trigger.

Migration: `revision="0011_resume_tailoring"`, `down_revision="0010_ai"`. Create order `resume_versions` → `resume_chunks` → `resume_suggestions`; downgrade reversed; `updated_at` triggers on `resume_versions` + `resume_suggestions` only (`resume_chunks` append-only, no trigger). Mirror `0010_ai.py` style. **No `sa.Computed`, no generated columns.** `Vector` import from `pgvector.sqlalchemy` (already a dep, used by `job_chunks`).

---

## 6. `backend/app/domain/resume/version_service.py` — `TailoringService` / version reads

Small service, `resume` domain.
- `ensure_base_snapshot(user_id, resume_id) -> ResumeVersion` — idempotent; if a `kind="base_snapshot"` row for `resume_id` exists return it, else create one from `resumes.extraction` (`content = resume.extraction or {}`), `created_by="user"`.
- `write_version(*, user_id, resume_id, job_id, parent_version_id, kind, content, generation_meta, label=None, created_by) -> ResumeVersion` — insert + flush.
- `list_versions(user_id, resume_id) -> list[ResumeVersion]` — `order_by created_at desc`.
- `get_version(user_id, version_id) -> ResumeVersion` — id + user guard → `NotFoundError`.
- `diff(base: ResumeExtraction, other: ResumeExtraction) -> ResumeDiff` — **deterministic, pure** field-level diff:
  ```python
  @dataclass(frozen=True)
  class FieldDelta:
      path: str                 # "summary" | "experiences[1].highlights" | "skills"
      op: Literal["added","removed","changed","reordered"]
      before: Any
      after: Any
  @dataclass(frozen=True)
  class ResumeDiff:
      deltas: list[FieldDelta]
      def as_dict(self) -> dict[str, Any]: ...
  ```
  - scalar fields (`summary`, contacts) → `changed` when unequal.
  - `skills` (list[str]) → one `added` delta with the set difference, one `removed`, one `reordered` if same set different order.
  - `experiences`/`projects`/`education`/`certifications` → matched by a stable key (`company+title` / `name` / `institution+degree` / `name`); unmatched on one side → `added`/`removed`; matched with differing `highlights`/`description`/`tech` → `changed` per sub-field with `path` like `experiences[0].highlights`.
- **Tests (pure):** identical extractions → `deltas == []`; a changed summary → one `changed` delta at `path="summary"`; an added highlight on an existing experience → one `added` delta at `experiences[0].highlights`; a new experience → one `added` at `experiences[]`; skills re-ordered only → one `reordered`.

---

## 7. `/resumes` API additions — `backend/app/api/v1/resumes.py`

- `POST /resumes/{resume_id}/tailor` → **202** `{ run_id }`. Body `TailorIn { job_id: uuid }`. Loads the résumé (user guard, must be `confirmed`), creates an `ai_session` (kind `agent_run`), `AgentService.start_run(user.id, session.id, goal="tailor_resume", inputs={"job_id": str(job_id), "resume_id": str(resume_id)})`, `db.commit()`, returns the `run_id`. Rate bucket `"llm"`.
- `GET /resumes/{resume_id}/versions` → `ResumeVersionListOut { items: ResumeVersionOut[] }` — `TailoringService.list_versions`. `ResumeVersionOut`: `id, kind, label, job_id, parent_version_id, created_by, created_at, claim_validation: dict` (pulled from `generation_meta`).
- `GET /resumes/versions/{version_id}` → `ResumeVersionDetailOut` = `ResumeVersionOut` + `content: dict` (the full `ResumeExtraction` dump).
- `GET /resumes/versions/{version_id}/diff?against=<version_id|base>` → `ResumeDiffOut { deltas: [...] }` — `against` defaults to the version's `parent_version_id` (or the base snapshot). Both versions loaded with the user guard.
- `GET /resumes/versions/{version_id}/render?fmt=md|html` → the rendered doc as `text/markdown` / `text/html`. `fmt=pdf|docx` attempted; on `RenderUnavailable` → **409** `{ code: "render_unavailable" }` (the frontend falls back to HTML-print). No new file-store writes in 8a — rendering is on-demand, not persisted (`rendered_refs` stays `{}` this phase).
- `schemas/resume.py` gains `TailorIn`, `ResumeVersionOut`, `ResumeVersionListOut`, `ResumeVersionDetailOut`, `FieldDeltaOut`, `ResumeDiffOut`. Explicit mappers, no `from_attributes` on the diff/version-detail shapes.

---

## 8. Config + CI

- `app/core/config.py`: `doc_render_enabled: bool = True` (a kill-switch; when `False`, `to_pdf`/`to_docx` raise `RenderUnavailable` without importing the libs — keeps CI deterministic if a wheel breaks).
- `pyproject.toml` deps: `markdown-it-py`, `xhtml2pdf`, `python-docx`. `uv.lock` regenerated. If `mypy` flags any as missing stubs, add a `[[tool.mypy.overrides]]` `ignore_missing_imports = true` for that module only.
- CI: no new job. The `backend` job's `pytest` covers the new pure suites + the CI-only DB suites (`test_resume_version_model.py`, `test_tailoring_task.py`, `test_resumes_versions_api.py`).
- `import-linter`: still 3 contracts. `app.domain.generation` + `app.domain.documents` are `domain`-layer leaves (no sibling-domain imports except `generation → llm`, `documents → resume` for the `ResumeExtraction` type). Confirm `lint-imports` stays `3 kept, 0 broken`.

---

## 9. Phase 8b (frontend) — summary (its own plan)

- `lib/api/types.ts` — `ResumeVersion`, `ResumeVersionDetail`, `FieldDelta`, `ResumeDiff`, `ResumeSuggestion`, `TailorRunRef`.
- `lib/api/endpoints.ts` — `api.resumes` gains `tailor(id, {job_id})`, `versions(id)`, `version(versionId)`, `diff(versionId, against?)`, `renderUrl(versionId, fmt)`; `api.resumeSuggestions` (`list(versionId)`, `patch(id, status)`).
- `lib/query.ts` — `qk.resumeVersions(id)`, `qk.resumeVersion(id)`, `qk.resumeDiff(id, against)`, `qk.resumeSuggestions(versionId)`.
- `components/resume/VersionDiff.tsx` — renders a `ResumeDiff`: grouped by top-level path, `added`/`removed`/`changed`/`reordered` chips, before/after side-by-side for `changed`, a claim-validation banner (`passed` → muted "all grounded", else a warning listing the unsupported lines).
- `components/resume/TailorButton.tsx` — on a Job Detail / Résumé Workspace, "Tailor for this job" → `api.resumes.tailor` → routes to the new version's diff once the SSE run reports `done` (reuse `useAgentStream` from 7b, keyed on the returned `run_id`).
- `components/resume/SuggestionCard.tsx` + a `ResumeSuggestions` list in the Résumé Workspace 3-pane shell — `open` suggestions with Accept / Edit / Dismiss (`patch`).
- `app/(app)/resume/versions/[id]/page.tsx` — the diff page (`<VersionDiff>` + a format switcher that opens `renderUrl`).
- Tests: `endpoints.test.ts` extend; `tests/resume/version-diff.test.tsx`; `tests/resume/tailor-button.test.tsx`; `tests/resume/suggestion-card.test.tsx`.

---

## 10. Out of scope (flag in the 8a completion report)

- Cover letter / email generation / approval / send — Phases 9–10 (`cover_letter`, `email_draft`, `application_prep`, `human_approval`, `email_external_action` nodes).
- `resume_chunks` population + retrieval over tailored versions — Phase 12 (the table lands now, empty).
- Persisting rendered PDFs/DOCX to the `FileStore` (`rendered_refs`) — a later polish item; 8a renders on demand only.
- A dedicated `ResumeVersionBlock` in the block registry — 8b decides; 8a reuses the `resume_suggestion` stub kind carrying the version id.
- User-driven `manual_edit` versions (editing a version in place) — 8b's `SuggestionCard` "Edit" is stubbed to "accept as-is" this phase; full inline editing is a later phase.
- LLM-as-judge generation eval — Phase 9 (`/eval` gains the `generation` suite there).
