# Phase 8a — Résumé tailoring (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `tailor_resume` agent goal that rewrites the user's confirmed résumé to a specific job, validates every claim against the base résumé + profile, and persists a `resume_versions` row with a field-level diff available over the API.

**Architecture:** A new `generation` domain service (shared LLM-generation primitive) + a deterministic `ClaimValidator` + a `DocumentRenderer` (md/html/pdf/docx). Two new LangGraph nodes (`resume_tailoring`, `claim_validator`) wired into the Phase-7a graph behind a new `tailor_resume` goal. Migration `0011` adds `resume_versions` / `resume_chunks` / `resume_suggestions`. `/resumes` gains tailor + version + diff + render endpoints.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, LangGraph 1.2.11, ARQ + Redis, pydantic-settings, pgvector. New: `markdown-it-py`, `xhtml2pdf`, `python-docx`.

**Spec:** `docs/superpowers/specs/2026-09-04-phase-8-resume-tailoring.md` (§1–§8) + master `2026-08-30-mana-career-design.md` §4.3 / §5.3.

## Global Constraints

- Alembic chain `…→0010_ai→0011_resume_tailoring`, **single head**. Mirror `0010_ai.py` for triggered tables; mirror `0007_jobs.py`'s `job_chunks` block for `resume_chunks` (the `Computed` tsv + HNSW/GIN). **No new `import-linter` contract** — stays `Contracts: 3 kept, 0 broken`. `app.domain.generation` / `app.domain.documents` are `domain`-layer leaves: `generation` may import `app.domain.llm` + `core` + `models`; `documents` may import `app.domain.resume` (for the `ResumeExtraction` type) + `core`. Neither imports `api`/`worker`/sibling business domains.
- `LLM_PROVIDER=fake` / `EMBEDDINGS_PROVIDER=fake` / `SEARCH_PROVIDER=fake` in CI and every test. Tests assert plumbing, never LLM output quality. `FakeLLMProvider(scripted=[...])` returns each string in order; `FakeLLMProvider.complete(schema=X)` stubs structured fields to empty.
- **No local Postgres/Redis.** DB-backed tests ERROR at `tests/conftest.py`'s `_migrated` fixture and run only in CI. Local gates: `"$UV" run ruff check .` / `"$UV" run lint-imports` / `"$UV" run mypy app` / `"$UV" run pytest -q --collect-only` (error-free) + the pure test suites named per task. `$UV` = `/c/Users/chitt/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe`. Do NOT run a full DB test file locally.
- All tuning values are module-level named constants.
- Canonical structured résumé = `app.domain.resume.extractor.ResumeExtraction` (unchanged). `resume_versions.content` = `ResumeExtraction.model_dump(mode="json")`.
- `mypy` is `strict = true` (`disallow_untyped_defs`, `warn_return_any = false`, `warn_unused_ignores`). Every def fully annotated. If `mypy app` flags a new dep as missing stubs, add `[[tool.mypy.overrides]] module = "<mod>.*"` `ignore_missing_imports = true` for THAT module only, and record it.
- F3 retry discipline: not touched here — 8a adds nodes to the *graph*, not new worker tasks; `run_agent` (Phase 7a) already carries the F3 guard.
- Node budget bumps are INLINE (`state["budget"]["llm_calls_made"] += N; state["budget"]["cost_usd"] += cost`) — no helper (Phase-7a R2).
- SSE / `ai_actions` / trace come for free from Phase 7a's `run_agent` + `AgentService`.

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `backend/pyproject.toml` | Modify | + `markdown-it-py`, `xhtml2pdf`, `python-docx` |
| `backend/app/core/config.py` | Modify | + `doc_render_enabled: bool = True` |
| `backend/app/domain/generation/__init__.py` · `types.py` · `service.py` | Create | `GenerationMeta`, `GenerationResult`, `GenerationService`, `GenerationError`, `PROMPT_VERSION` |
| `backend/app/domain/resume/tailoring.py` | Create | `ClaimValidator` + `ClaimReport` (deterministic) · `tailor_resume()` primitive · `_collect_sources` / `_render_prompt` · `MAX_CLAIM_REPROMPTS` |
| `backend/app/domain/documents/__init__.py` · `renderer.py` | Create | `DocumentRenderer`, `RenderFormat`, `RenderedDoc`, `RenderUnavailable` |
| `backend/app/models/resume_version.py` | Create | `ResumeVersion`, `ResumeChunk`, `ResumeSuggestion` |
| `backend/app/models/__init__.py` | Modify | `from app.models import resume_version as resume_version` after `resume` |
| `backend/alembic/versions/0011_resume_tailoring.py` | Create | 3 tables, triggers on 2, `job_chunks`-style block for `resume_chunks` |
| `backend/app/domain/resume/version_service.py` | Create | `TailoringService` (`ensure_base_snapshot`, `write_version`, `list_versions`, `get_version`) · `diff()` · `FieldDelta` / `ResumeDiff` |
| `backend/app/domain/agents/state.py` | Modify | `AgentGoal += "tailor_resume"` · `NODE_ORDER += "resume_tailoring","claim_validator"` |
| `backend/app/domain/agents/nodes/resume_tailoring.py` · `claim_validator.py` | Create | the two nodes |
| `backend/app/domain/agents/nodes/__init__.py` | Modify | re-export the 2 new nodes |
| `backend/app/domain/agents/nodes/supervisor.py` | Modify | route `goal == "tailor_resume"` → `resume_tailoring` |
| `backend/app/domain/agents/nodes/respond.py` | Modify | a `tailored_resume_version_id` branch → `TextBlock` + `ResumeSuggestionBlock` |
| `backend/app/domain/agents/graph.py` | Modify | add the 2 nodes + supervisor edge + the `resume_tailoring → claim_validator → respond` chain |
| `backend/app/domain/agents/service.py` | Modify | `start_run` accepts `goal="tailor_resume"` (it already takes `goal`/`inputs` — verify no goal-allowlist blocks it) |
| `backend/app/api/v1/schemas/resume.py` | Modify | `TailorIn`, `ResumeVersionOut`, `ResumeVersionListOut`, `ResumeVersionDetailOut`, `FieldDeltaOut`, `ResumeDiffOut` |
| `backend/app/api/v1/resumes.py` | Modify | `POST /{id}/tailor` (202) · `GET /{id}/versions` · `GET /versions/{vid}` · `GET /versions/{vid}/diff` · `GET /versions/{vid}/render` |
| `backend/app/core/rate_limit.py` | Modify | `_bucket`: `POST …/resumes/{id}/tailor` → `"llm"` |
| tests | Create | `tests/domain/generation/test_service.py` · `tests/domain/resume/test_tailoring.py` · `tests/domain/documents/test_renderer.py` · `tests/domain/resume/test_version_diff.py` · `tests/domain/agents/test_nodes_tailoring.py` · `tests/domain/agents/test_graph_tailor.py` · `tests/models/test_resume_version_model.py` (DB) · `tests/worker/test_tailoring_task.py` (DB) · `tests/api/test_resumes_versions.py` (DB) · extend `tests/core/test_rate_limit.py` |

---

## Task 1: deps + config + package skeleton

**Files:** Modify `backend/pyproject.toml`, `backend/app/core/config.py`. Create `backend/app/domain/generation/__init__.py`, `backend/app/domain/documents/__init__.py`, `backend/tests/domain/generation/__init__.py`, `backend/tests/domain/documents/__init__.py`, `backend/tests/domain/generation/test_imports.py`.

**Interfaces:**
- Produces: importable empty packages `app.domain.generation`, `app.domain.documents`; `Settings(...).doc_render_enabled is True`.

- [ ] **Step 1: `pyproject.toml`** — add to `[project.dependencies]` (keep sorted):
```
  "markdown-it-py>=3.0.0",
  "python-docx>=1.1.2",
  "xhtml2pdf>=0.2.16",
```
Run `"$UV" sync` (or `"$UV" lock`) to regenerate `uv.lock`.

- [ ] **Step 2: `config.py`** — after `search_api_key`:
```python
    doc_render_enabled: bool = True
```

- [ ] **Step 3:** create the four empty `__init__.py` files (zero bytes).

- [ ] **Step 4: `tests/domain/generation/test_imports.py`**
```python
def test_new_packages_import():
    import app.domain.generation  # noqa: F401
    import app.domain.documents  # noqa: F401


def test_doc_render_flag_defaults_true():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
        redis_url="redis://x", jwt_secret="x",
    )
    assert s.doc_render_enabled is True
```

- [ ] **Step 5: Gates** — from `backend/`:
```
"$UV" run pytest tests/domain/generation/test_imports.py -q
"$UV" run ruff check .
"$UV" run mypy app
"$UV" run lint-imports
"$UV" run pytest -q --collect-only 2>&1 | tail -3
```
Expected: 2 tests pass; ruff clean; mypy clean; `Contracts: 3 kept, 0 broken`; collect error-free. (`markdown-it-py`/`xhtml2pdf`/`python-docx` are not imported yet, so no mypy stub issue in this task.)

- [ ] **Step 6: Commit**
```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/app/domain/generation backend/app/domain/documents backend/tests/domain/generation backend/tests/domain/documents
git commit -m "feat(gen): doc-render deps + generation/documents package skeleton"
```

---

## Task 2: `generation` service

**Files:** Create `backend/app/domain/generation/types.py`, `backend/app/domain/generation/service.py`, `backend/tests/domain/generation/test_service.py`.

**Interfaces:**
- Consumes: `app.domain.llm.provider` (`LLMProvider`, `LLMMessage`, `LLMResult`); `app.core.config.Settings`; `pydantic.BaseModel`.
- Produces:
  - `types.GenerationMeta` (frozen dataclass): `model: str`, `provider: str`, `prompt_version: str`, `prompt_hash: str`, `input_tokens: int`, `output_tokens: int`, `cost_usd: float`, `claim_validation: dict[str, Any]`.
  - `types.GenerationResult` (frozen dataclass): `structured: dict[str, Any]`, `text: str`, `meta: GenerationMeta`.
  - `service.GenerationError(Exception)`.
  - `service.PROMPT_VERSION = "gen-1"`.
  - `service.GenerationService`: `__init__(self, llm: LLMProvider, *, settings: Settings | None = None) -> None`; `async def generate(self, *, system: str, user: str, schema: type[BaseModel], prompt_version: str, max_tokens: int = 1200) -> GenerationResult`.

- [ ] **Step 1: `tests/domain/generation/test_service.py`**
```python
import pytest
from pydantic import BaseModel

from app.domain.generation.service import GenerationError, GenerationService
from app.domain.llm.adapters.fake import FakeLLMProvider


class _Tiny(BaseModel):
    a: str = ""
    b: int = 0


async def test_generate_returns_validated_structured_and_stable_hash():
    llm = FakeLLMProvider()
    svc = GenerationService(llm)
    r1 = await svc.generate(system="S", user="U-one", schema=_Tiny, prompt_version="v1")
    r2 = await svc.generate(system="S", user="U-one", schema=_Tiny, prompt_version="v1")
    r3 = await svc.generate(system="S", user="U-two", schema=_Tiny, prompt_version="v1")
    assert r1.meta.prompt_hash == r2.meta.prompt_hash
    assert r1.meta.prompt_hash != r3.meta.prompt_hash
    assert r1.meta.prompt_version == "v1"
    assert r1.meta.claim_validation == {}
    assert set(r1.structured) == {"a", "b"}   # schema-validated dump
    assert r1.meta.cost_usd == 0.0


async def test_generate_raises_when_no_structured_payload():
    class _NoStruct(FakeLLMProvider):
        async def complete(self, messages, **kw):  # type: ignore[override]
            from app.domain.llm.provider import LLMResult
            return LLMResult(text="x", model="fake", input_tokens=1, output_tokens=1, cost_usd=0.0)

    with pytest.raises(GenerationError):
        await GenerationService(_NoStruct()).generate(
            system="S", user="U", schema=_Tiny, prompt_version="v1"
        )
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: `types.py`** — the two frozen dataclasses per Produces (`from __future__ import annotations`; `from dataclasses import dataclass`; `from typing import Any`).

- [ ] **Step 4: `service.py`**
```python
from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.domain.generation.types import GenerationMeta, GenerationResult
from app.domain.llm.provider import LLMMessage, LLMProvider

PROMPT_VERSION = "gen-1"


class GenerationError(Exception):
    """A model call produced no usable structured payload."""


class GenerationService:
    def __init__(self, llm: LLMProvider, *, settings: Settings | None = None) -> None:
        self._llm = llm
        self._settings = settings or get_settings()

    async def generate(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        prompt_version: str,
        max_tokens: int = 1200,
    ) -> GenerationResult:
        messages: list[LLMMessage] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        prompt_hash = hashlib.sha256(
            f"{prompt_version}\n{system}\n{user}".encode()
        ).hexdigest()
        res = await self._llm.complete(messages, schema=schema, max_tokens=max_tokens)
        if res.structured is None:
            raise GenerationError("model returned no structured payload")
        try:
            validated = schema.model_validate(res.structured)
        except ValidationError as exc:  # pragma: no cover - defensive
            raise GenerationError(f"structured payload failed schema: {exc}") from exc
        meta = GenerationMeta(
            model=res.model,
            provider=type(self._llm).__name__,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            cost_usd=res.cost_usd,
            claim_validation={},
        )
        return GenerationResult(
            structured=validated.model_dump(mode="json"), text=res.text or "", meta=meta
        )
```

- [ ] **Step 5: Gates** — `"$UV" run pytest tests/domain/generation/test_service.py -q && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports`. Expected: 2 pass; clean; `3 kept`.

- [ ] **Step 6: Commit**
```bash
git add backend/app/domain/generation backend/tests/domain/generation/test_service.py
git commit -m "feat(gen): GenerationService — schema call + prompt hash + GenerationMeta"
```

---

## Task 3: `resume/tailoring.py` — `ClaimValidator` + `tailor_resume`

**Files:** Create `backend/app/domain/resume/tailoring.py`, `backend/tests/domain/resume/test_tailoring.py`.

**Interfaces:**
- Consumes: `app.domain.resume.extractor.ResumeExtraction` (+ the `Extracted*` sub-models); `app.domain.generation.service.GenerationService`; `app.domain.generation.types.GenerationMeta`.
- Produces:
  - `ClaimReport` (frozen dataclass): `checked: int`, `unsupported: list[str]`, `supported_ratio: float`, `passed: bool`; `def as_dict(self) -> dict[str, Any]`.
  - `_MIN_SUPPORT = 0.60`, `_STOPWORDS: frozenset[str]` (~40 words), `MAX_CLAIM_REPROMPTS = 2`, `_TAILOR_SYSTEM: str`, `_TAILOR_PROMPT_VERSION = "tailor-1"` (module constants).
  - `ClaimValidator`: `__init__(self, sources: list[str]) -> None`; `check(self, tailored: ResumeExtraction) -> ClaimReport`.
  - `def _collect_sources(base: ResumeExtraction, profile_summary: str) -> list[str]`.
  - `async def tailor_resume(*, gen: GenerationService, base: ResumeExtraction, profile_summary: str, job_brief: str) -> tuple[ResumeExtraction, GenerationMeta]`.

- [ ] **Step 1: `tests/domain/resume/test_tailoring.py`**
```python
from app.domain.resume.extractor import (
    ExtractedExperience,
    ResumeExtraction,
)
from app.domain.resume.tailoring import (
    ClaimValidator,
    _collect_sources,
    tailor_resume,
)
from app.domain.generation.service import GenerationService
from app.domain.llm.adapters.fake import FakeLLMProvider


def _base() -> ResumeExtraction:
    return ResumeExtraction(
        full_name="A. Dev",
        summary="Backend engineer focused on Python services and Postgres.",
        skills=["python", "postgresql", "fastapi"],
        experiences=[
            ExtractedExperience(
                company="Acme", title="Senior Engineer",
                description="Owned the billing service.",
                highlights=[
                    "Cut p99 latency on the billing API by 40 percent",
                    "Migrated the datastore from MySQL to Postgres",
                ],
                tech=["python", "postgresql"],
            )
        ],
    )


def test_validator_passes_when_highlights_are_grounded():
    b = _base()
    v = ClaimValidator(_collect_sources(b, ""))
    report = v.check(b)  # the base is trivially grounded in itself
    assert report.passed is True
    assert report.unsupported == []


def test_validator_flags_an_invented_highlight():
    b = _base()
    v = ClaimValidator(_collect_sources(b, ""))
    tailored = b.model_copy(deep=True)
    tailored.experiences[0].highlights.append(
        "Led a team of 50 engineers across four continents"
    )
    report = v.check(tailored)
    assert report.passed is False
    assert any("Led a team of 50" in u for u in report.unsupported)


def test_validator_ignores_blank_and_structural_lines():
    b = _base()
    v = ClaimValidator(_collect_sources(b, ""))
    tailored = b.model_copy(deep=True)
    tailored.experiences[0].highlights.append("   ")
    report = v.check(tailored)
    assert report.passed is True


async def test_tailor_resume_loop_shape_with_fake_llm():
    b = _base()
    gen = GenerationService(FakeLLMProvider())
    tailored, meta = await tailor_resume(
        gen=gen, base=b, profile_summary="", job_brief="Senior Python role at Globex"
    )
    # FakeLLMProvider stubs the schema to empty → an empty extraction, 0 claims, passes.
    assert isinstance(tailored, ResumeExtraction)
    assert meta.claim_validation["checked"] == 0
    assert meta.claim_validation["passed"] is True
    assert meta.prompt_version == "tailor-1"
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: `tailoring.py`** — implement per Produces. Key points:
  - `_norm(s)`: `s.lower()`, strip punctuation to spaces (`re.sub(r"[^\w\s]", " ", s)`), split, drop `_STOPWORDS`, return `frozenset[str]`.
  - `ClaimValidator._supported(claim)`: `ct = _norm(claim)`; `if not ct: return True`; `best = max((len(ct & st) / len(ct) for st in self._source_tokens), default=0.0)`; `return best >= _MIN_SUPPORT`.
  - `check(tailored)`: claim lines = every `experiences[].highlights[]` + `projects[].highlights[]` + each sentence (`re.split(r"(?<=[.!?])\s+", ...)`) of every non-empty `experiences[].description` / `projects[].description` / `summary`. For each, `_supported`. `checked` counts non-blank claim lines; `unsupported` collects failures; `supported_ratio = (checked - len(unsupported)) / checked` (or `1.0` when `checked == 0`); `passed = not unsupported`.
  - `_collect_sources(base, profile_summary)`: flatten to `list[str]` — `base.summary`, every `experiences[].description` + `highlights` + `title` + `company` + `tech`, same for `projects`, `education[].institution/degree/field`, `certifications[].name/issuer`, `base.skills`, and `profile_summary` split into sentences. Drop falsy/blank.
  - `_render_prompt(base, profile_summary, job_brief, rejected)`: an f-string — the base résumé as JSON, the profile summary, the job brief, and (when `rejected`) a "The following lines were not grounded in the source material; rewrite or drop them: …" block.
  - `tailor_resume`: the loop from the spec §2.2. `from dataclasses import replace`. Budget bump is the caller's job (the node) — this primitive just returns `(tailored, meta)` where `meta.claim_validation` is the last `ClaimReport.as_dict()`.

- [ ] **Step 4: Gates** — `"$UV" run pytest tests/domain/resume/test_tailoring.py -q && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports`. Expected: 4 pass; clean; `3 kept`. (`resume.tailoring` importing `generation` is a legal same-layer edge; confirm `lint-imports` stays green.)

- [ ] **Step 5: Commit**
```bash
git add backend/app/domain/resume/tailoring.py backend/tests/domain/resume/test_tailoring.py
git commit -m "feat(resume): ClaimValidator + tailor_resume primitive (reprompt <=2)"
```

---

## Task 4: `DocumentRenderer`

**Files:** Create `backend/app/domain/documents/renderer.py`, `backend/tests/domain/documents/test_renderer.py`.

**Interfaces:**
- Consumes: `app.domain.resume.extractor.ResumeExtraction`; `app.core.config` (`get_settings().doc_render_enabled`); `markdown_it` (lazy import inside `to_html`), `xhtml2pdf` (lazy, inside `to_pdf`), `docx` (lazy, inside `to_docx`).
- Produces:
  - `RenderFormat(StrEnum)`: `MD`, `HTML`, `PDF`, `DOCX`.
  - `RenderedDoc` (frozen dataclass): `fmt: RenderFormat`, `media_type: str`, `data: bytes`.
  - `RenderUnavailable(RuntimeError)`.
  - `DocumentRenderer`: `to_markdown(r) -> str`, `to_html(r) -> str`, `to_pdf(r) -> bytes`, `to_docx(r) -> bytes`, `render(r, fmt) -> RenderedDoc`.
  - `_SECTION_ORDER`, `_HTML_STYLE` (module constants).

- [ ] **Step 1: `tests/domain/documents/test_renderer.py`**
```python
import pytest

from app.domain.documents.renderer import (
    DocumentRenderer,
    RenderFormat,
    RenderUnavailable,
)
from app.domain.resume.extractor import ExtractedExperience, ResumeExtraction

R = DocumentRenderer()
CV = ResumeExtraction(
    full_name="Jamie Rivera",
    summary="Platform engineer.",
    skills=["python", "kubernetes"],
    experiences=[
        ExtractedExperience(
            company="Globex", title="Staff Engineer",
            highlights=["Ran the platform team", "Shipped the CI pipeline"],
        )
    ],
)


def test_markdown_has_name_h1_and_company_h2_and_bullets():
    md = R.to_markdown(CV)
    assert md.splitlines()[0].strip() == "# Jamie Rivera"
    assert "## Globex" in md or "Globex" in md
    assert "- Ran the platform team" in md


def test_markdown_is_stable():
    assert R.to_markdown(CV) == R.to_markdown(CV)


def test_html_contains_the_name():
    html = R.to_html(CV)
    assert "<h1>" in html and "Jamie Rivera" in html


def test_pdf_is_pdf_bytes_or_unavailable():
    try:
        data = R.to_pdf(CV)
    except RenderUnavailable:
        return
    assert data[:4] == b"%PDF"


def test_docx_is_zip_bytes_or_unavailable():
    try:
        data = R.to_docx(CV)
    except RenderUnavailable:
        return
    assert data[:2] == b"PK"


def test_render_dispatches_by_format():
    doc = R.render(CV, RenderFormat.MD)
    assert doc.fmt is RenderFormat.MD and doc.media_type == "text/markdown"
    assert b"Jamie Rivera" in doc.data
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: `renderer.py`** — implement:
  - `to_markdown`: a deterministic template. `# {full_name}`, then contact line, then `## Summary`, `## Skills` (comma-joined), `## Experience` with `### {title}, {company}` + date range + `- {highlight}` lines, then Projects / Education / Certifications in `_SECTION_ORDER`. Skip empty sections.
  - `to_html`: `from markdown_it import MarkdownIt`; `MarkdownIt().render(self.to_markdown(r))` wrapped in `<html><head><style>{_HTML_STYLE}</style></head><body>…</body></html>`. If the import fails → raise `RenderUnavailable`.
  - `to_pdf`: `if not get_settings().doc_render_enabled: raise RenderUnavailable(...)`. `try: from xhtml2pdf import pisa` (→ `RenderUnavailable` on ImportError). `buf = io.BytesIO(); pisa.CreatePDF(self.to_html(r), dest=buf)`; if `.err` → `RenderUnavailable`; `return buf.getvalue()`.
  - `to_docx`: `if not …doc_render_enabled: raise RenderUnavailable`. `try: from docx import Document` (→ `RenderUnavailable`). Build a `Document()` section by section (`add_heading`, `add_paragraph`, bullet style `"List Bullet"`), `doc.save(buf)`, `return buf.getvalue()`.
  - `render(r, fmt)`: dispatch; media types `text/markdown`, `text/html`, `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`; `data` is `str.encode()` for MD/HTML, raw bytes for PDF/DOCX.
  - If `mypy` flags `markdown_it` / `xhtml2pdf` / `docx` missing stubs → add the narrowest `[[tool.mypy.overrides]]` for each and record which.

- [ ] **Step 4: Gates** — `"$UV" run pytest tests/domain/documents/test_renderer.py -q && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only 2>&1 | tail -3`. Expected: 6 pass (pdf/docx tests tolerate `RenderUnavailable`); clean; `3 kept`; collect error-free. Record whether `to_pdf`/`to_docx` actually rendered on this box or raised `RenderUnavailable`.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domain/documents backend/tests/domain/documents/test_renderer.py backend/pyproject.toml
git commit -m "feat(docs): DocumentRenderer — md/html always, pdf/docx best-effort"
```

---

## Task 5: models + migration `0011_resume_tailoring`  *(SUBAGENT review)*

**Files:** Create `backend/app/models/resume_version.py`, `backend/alembic/versions/0011_resume_tailoring.py`, `backend/tests/models/test_resume_version_model.py` (DB — CI-deferred). Modify `backend/app/models/__init__.py`.

**Interfaces:**
- Consumes: `Base`, `TimestampMixin` (`app.models.base`); `pgvector.sqlalchemy.Vector`; `sqlalchemy.dialects.postgresql.{JSONB, TSVECTOR, UUID}`; `sqlalchemy.Computed`.
- Produces the three models + migration per spec §5. Mirror `app/models/job.py` for the `Vector` + `Computed(TSVECTOR)` idiom, `app/models/ai.py` for the plain-table idiom.

- [ ] **Step 1: DB test `tests/models/test_resume_version_model.py`**
```python
from sqlalchemy import select

from app.models.resume_version import ResumeSuggestion, ResumeVersion


async def test_version_and_suggestion_roundtrip(db_session):
    from app.models.user import User

    u = User(email="rv@x.com", password_hash="x", full_name="U")
    db_session.add(u)
    await db_session.flush()

    v = ResumeVersion(
        user_id=u.id, resume_id=u.id,  # resume_id FK is to resumes; a bare uuid is fine for the shape test only if the FK is deferrable — instead: seed a Resume
    )
```
> **Implementer:** the DB test must seed a real `Resume` row (mirror `tests/domain/resume/…` seeds) because `resume_versions.resume_id` FKs `resumes.id`. Assert: a `ResumeVersion(kind="ai_tailored", content={...}, generation_meta={...})` + a `ResumeSuggestion(status="open")` insert+flush+select round-trip; `v.created_by == "user"` default on a row that doesn't set it; `s.status == "open"` default.

- [ ] **Step 2: `app/models/resume_version.py`** — three models per spec §5:
  - `ResumeVersion(Base, TimestampMixin)` → `resume_versions`. Cols + CHECKs + indexes exactly as the spec lists. `content`/`rendered_refs`/`generation_meta` = `mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))`. `kind` CHECK `resume_versions_kind_valid`; `created_by` CHECK `resume_versions_created_by_valid`.
  - `ResumeChunk(Base)` (NO `TimestampMixin`) → `resume_chunks`. `content_tsv: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True))` — copy `app/models/job.py:162`. `embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))`. `created_at` explicit `mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))`.
  - `ResumeSuggestion(Base, TimestampMixin)` → `resume_suggestions`. Cols + CHECK `resume_suggestions_status_valid` per spec.
- [ ] **Step 3: `app/models/__init__.py`** — add `from app.models import resume_version as resume_version` immediately after the `resume` line (keep the block sorted).
- [ ] **Step 4: `alembic/versions/0011_resume_tailoring.py`** — `revision="0011_resume_tailoring"`, `down_revision="0010_ai"`. `upgrade()`: `op.create_table("resume_versions", …)` + its 3 indexes + `CREATE TRIGGER trg_resume_versions_set_updated_at …` (copy the exact phrasing from `0010_ai.py`); `op.create_table("resume_chunks", …)` with the `sa.Column("content_tsv", pg.TSVECTOR, sa.Computed("to_tsvector('english', content)", persisted=True))` + HNSW index (`postgresql_using="hnsw"`, `postgresql_with={"m": 16, "ef_construction": 64}`, `postgresql_ops={"embedding": "vector_cosine_ops"}` — copy `0007_jobs.py`'s `job_chunks` HNSW) + GIN on `content_tsv` + the `(resume_version_id, chunk_index)` index; NO trigger; `op.create_table("resume_suggestions", …)` + 2 indexes + `CREATE TRIGGER trg_resume_suggestions_set_updated_at …`. `downgrade()`: drop `resume_suggestions` → `resume_chunks` → `resume_versions`, with `DROP TRIGGER IF EXISTS …` before the two triggered `drop_table`s.

- [ ] **Step 5: Gates** — `"$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only 2>&1 | tail -3 && "$UV" run python -c "from app.models import Base; assert {'resume_versions','resume_chunks','resume_suggestions'} <= set(Base.metadata.tables); print('metadata OK')" && "$UV" run alembic heads`. Expected: clean; `3 kept`; collect error-free; `metadata OK`; `alembic heads` → single `0011_resume_tailoring (head)`. The DB test ERRORs at `_migrated` — CI-deferred; confirm it's a fixture error, not a collection/import error.

- [ ] **Step 6: Commit**
```bash
git add backend/app/models/resume_version.py backend/app/models/__init__.py backend/alembic/versions/0011_resume_tailoring.py backend/tests/models/test_resume_version_model.py
git commit -m "feat(resume): resume_versions / resume_chunks / resume_suggestions (migration 0011)"
```

---

## Task 6: `version_service.py` — `TailoringService` + `diff`

**Files:** Create `backend/app/domain/resume/version_service.py`, `backend/tests/domain/resume/test_version_diff.py`.

**Interfaces:**
- Consumes: `app.models.resume_version.ResumeVersion`; `app.models.resume.Resume`; `app.domain.resume.extractor.ResumeExtraction`; `app.core.errors.NotFoundError`; `AsyncSession`.
- Produces:
  - `FieldDelta` (frozen dataclass): `path: str`, `op: Literal["added","removed","changed","reordered"]`, `before: Any`, `after: Any`.
  - `ResumeDiff` (frozen dataclass): `deltas: list[FieldDelta]`; `def as_dict(self) -> dict[str, Any]`.
  - `def diff(base: ResumeExtraction, other: ResumeExtraction) -> ResumeDiff` — deterministic, pure (spec §6).
  - `class TailoringService`: `__init__(self, session: AsyncSession) -> None`; `async def ensure_base_snapshot(self, user_id, resume_id) -> ResumeVersion`; `async def write_version(self, *, user_id, resume_id, job_id, parent_version_id, kind, content, generation_meta, label=None, created_by) -> ResumeVersion`; `async def list_versions(self, user_id, resume_id) -> list[ResumeVersion]`; `async def get_version(self, user_id, version_id) -> ResumeVersion`.

- [ ] **Step 1: `tests/domain/resume/test_version_diff.py`** (pure — `diff` only)
```python
from app.domain.resume.extractor import ExtractedExperience, ResumeExtraction
from app.domain.resume.version_service import diff


def _cv(**kw) -> ResumeExtraction:
    base = dict(
        full_name="A", summary="s", skills=["python", "sql"],
        experiences=[ExtractedExperience(company="Acme", title="Eng", highlights=["one"])],
    )
    base.update(kw)
    return ResumeExtraction(**base)


def test_identical_extractions_have_no_deltas():
    assert diff(_cv(), _cv()).deltas == []


def test_changed_summary_is_one_changed_delta():
    d = diff(_cv(), _cv(summary="different"))
    assert [x.path for x in d.deltas] == ["summary"]
    assert d.deltas[0].op == "changed"


def test_added_highlight_on_existing_experience():
    other = _cv()
    other.experiences[0].highlights.append("two")
    d = diff(_cv(), other)
    assert any(x.path == "experiences[0].highlights" and x.op == "added" for x in d.deltas)


def test_new_experience_is_added_delta():
    other = _cv()
    other.experiences.append(ExtractedExperience(company="Globex", title="Staff"))
    d = diff(_cv(), other)
    assert any(x.path.startswith("experiences[") and x.op == "added" for x in d.deltas)


def test_skills_reordered_only():
    d = diff(_cv(), _cv(skills=["sql", "python"]))
    assert [x.op for x in d.deltas] == ["reordered"]
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: `version_service.py`** — implement `diff` per spec §6 (scalar `changed`; `skills` set-diff → `added`/`removed`/`reordered`; sub-entity lists matched by stable key `company|title` / `name` / `institution|degree` / `name`; matched-with-differences → per-sub-field `changed`/`added` at `path="experiences[<i>].highlights"` etc.). Then `TailoringService` — mirror `MatchService`/`AgentService` for the `session` + `NotFoundError` guard + `select().where(id==).where(user_id==)` idiom. `ensure_base_snapshot` is idempotent (select existing `kind="base_snapshot"` for `resume_id`, else insert from `Resume.extraction or {}`).

- [ ] **Step 4: Gates** — `"$UV" run pytest tests/domain/resume/test_version_diff.py -q && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports`. Expected: 5 pass; clean; `3 kept`.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domain/resume/version_service.py backend/tests/domain/resume/test_version_diff.py
git commit -m "feat(resume): TailoringService + deterministic field-level résumé diff"
```

---

## Task 7: nodes (`resume_tailoring`, `claim_validator`) + supervisor + respond + state

**Files:** Modify `backend/app/domain/agents/state.py`, `backend/app/domain/agents/nodes/__init__.py`, `backend/app/domain/agents/nodes/supervisor.py`, `backend/app/domain/agents/nodes/respond.py`. Create `backend/app/domain/agents/nodes/resume_tailoring.py`, `backend/app/domain/agents/nodes/claim_validator.py`, `backend/tests/domain/agents/test_nodes_tailoring.py`.

**Interfaces:**
- Consumes: `AgentDeps` (typed `"AgentDeps"` under `TYPE_CHECKING` from `app.domain.agents.graph` — no `# type: ignore` needed, `graph.py` exists since Phase 7a); `GenerationService`; `tailor_resume` / `ClaimValidator` / `_collect_sources` (Task 3); `TailoringService` (Task 6); `ResumeService` (`get`, `list_`); `ProfileService` (`load_full`, `list_skills`); `JobService` (`get`); `ResumeExtraction`; `app.domain.agents.blocks.{TextBlock, ResumeSuggestionBlock, dump_blocks}`.
- Produces:
  - `state.AgentGoal` gains `"tailor_resume"`; `NODE_ORDER` gains `"resume_tailoring"`, `"claim_validator"`.
  - `supervisor`: `if goal == "tailor_resume": return {"_route": "resume_tailoring", "_summary": "Routing: tailor a résumé"}` (before the fallthrough).
  - `resume_tailoring(state, *, deps) -> dict` — per spec §4.2. On no confirmed résumé → `{"status":"halted","error":"no confirmed résumé to tailor","_summary":"Add a résumé first"}` (guard-wrapped node — plain keys, `_halt_or` routes).
  - `claim_validator(state, *, deps) -> dict` — per spec §4.3. Never halts.
  - `respond` gains, **before** the `retrieved_jobs` check: `if state.get("tailored_resume_version_id"): blocks = [TextBlock(markdown=<"Here's a version of your résumé tuned for this role — open it to see what changed.">), ResumeSuggestionBlock(suggestion_id=uuid.UUID(state["tailored_resume_version_id"]))]; text = <that markdown>` then fall through to the persist + `_log_action` + return.
  - `nodes/__init__.py` re-exports `resume_tailoring`, `claim_validator` (grow `__all__`, keep sorted).

- [ ] **Step 1: `tests/domain/agents/test_nodes_tailoring.py`** (pure supervisor only; the nodes get DB coverage via `test_tailoring_task.py` / `test_graph_tailor.py`)
```python
from app.domain.agents.nodes.supervisor import supervisor


async def test_supervisor_routes_tailor_resume():
    out = await supervisor({"goal": "tailor_resume", "inputs": {"job_id": "j1"}}, deps=object())
    assert out["_route"] == "resume_tailoring"


async def test_supervisor_still_halts_unknown_goals():
    out = await supervisor({"goal": "analyze_profile", "inputs": {}}, deps=object())
    assert out["_route"] == "halted"
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** `state.py` — extend the `AgentGoal` Literal and `NODE_ORDER`. `supervisor.py` — insert the `tailor_resume` branch. `resume_tailoring.py` / `claim_validator.py` per spec §4.2–§4.3, budget bump INLINE. `respond.py` — insert the `tailored_resume_version_id` branch as the first `if` in the block-building section (keep the rest untouched). `nodes/__init__.py` — add the two exports.
  - `_summarise_profile(profile, skills) -> str` and `_summarise_job(job) -> str` are private helpers in `resume_tailoring.py` (≤1.5k / ≤6k chars — truncate).
  - `resume_tailoring` picks the résumé: `ResumeService(deps.session).list_(deps.user_id)` → first with `confirmed_at is not None and is_primary` else first `confirmed_at is not None`; none → halt.

- [ ] **Step 4: Gates** — `"$UV" run pytest tests/domain/agents/test_nodes_tailoring.py -q && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run pytest -q --collect-only 2>&1 | tail -3`. Expected: 2 pass; clean; `3 kept` (nodes importing `resume`/`generation`/`profile`/`jobs` services are legal same-layer edges — `agents` is not leaf-ward); collect error-free.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domain/agents/state.py backend/app/domain/agents/nodes/ backend/tests/domain/agents/test_nodes_tailoring.py
git commit -m "feat(agents): resume_tailoring + claim_validator nodes; tailor_resume route"
```

---

## Task 8: `graph.py` wiring  *(SUBAGENT review)*

**Files:** Modify `backend/app/domain/agents/graph.py`. Create `backend/tests/domain/agents/test_graph_tailor.py`.

**Interfaces:**
- Consumes: the Task 7 nodes; `guard` (`app.domain.agents.budget`); the Phase-7a `_halt_or` / `_route_from_supervisor` (already in `graph.py`).
- Produces: `build_graph` registers `resume_tailoring` and `claim_validator` as `guard`-wrapped nodes; `supervisor`'s conditional-edge map gains `"resume_tailoring": "resume_tailoring"`; new edges `resume_tailoring —_halt_or("claim_validator")→ {claim_validator | halted}` and `claim_validator —_halt_or("respond")→ {respond | halted}`.

- [ ] **Step 1: `tests/domain/agents/test_graph_tailor.py`** (pure — routing helpers + graph compiles)
```python
from app.domain.agents.graph import _route_from_supervisor


def test_route_from_supervisor_passes_resume_tailoring_through():
    assert _route_from_supervisor({"_route": "resume_tailoring"}) == "resume_tailoring"


def test_build_graph_registers_the_tailoring_nodes():
    # build_graph needs an AgentDeps; assert the node set via a stub-deps compile.
    import app.domain.agents.graph as G

    src = __import__("inspect").getsource(G.build_graph)
    assert '"resume_tailoring"' in src and '"claim_validator"' in src
```
> **Implementer:** if a stub-`AgentDeps` compile is cheap (all fields can be `object()` / `None` and `build_graph` only wires, never calls), prefer asserting `"resume_tailoring" in compiled.get_graph().nodes` over the source-string check. Either is acceptable; the DB `test_graph_tailor` end-to-end traversal is CI-only.

- [ ] **Step 2: Run — expect fail** (or pass trivially on the route helper; the `build_graph` assertion fails until Step 3).

- [ ] **Step 3: `graph.py`** — add `("resume_tailoring", resume_tailoring), ("claim_validator", claim_validator)` to the guard-wrapped node loop (import them from `app.domain.agents.nodes.resume_tailoring` / `.claim_validator`). Add `"resume_tailoring": "resume_tailoring"` to the `supervisor` `add_conditional_edges` map. Add:
```python
    g.add_conditional_edges(
        "resume_tailoring",
        _halt_or("claim_validator"),
        {"claim_validator": "claim_validator", "halted": "halted"},
    )
    g.add_conditional_edges(
        "claim_validator",
        _halt_or("respond"),
        {"respond": "respond", "halted": "halted"},
    )
```
Keep the existing `respond`/`halted` → `END` edges. The `# type: ignore[call-overload]` on the guard-loop `add_node` stays (Phase-7a R13-mypy).

- [ ] **Step 4: Gates** — `"$UV" run pytest tests/domain/agents/test_graph_tailor.py tests/domain/agents/test_graph.py -q && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports && "$UV" run python -c "import app.domain.agents.graph; print('graph import ok, no libpq')" && "$UV" run pytest -q --collect-only 2>&1 | tail -3`. Expected: all pass; clean; `3 kept`; graph imports without libpq; collect error-free.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domain/agents/graph.py backend/tests/domain/agents/test_graph_tailor.py
git commit -m "feat(agents): wire resume_tailoring -> claim_validator -> respond into the graph"
```

---

## Task 9: `/resumes` version + diff + tailor API  *(SUBAGENT review)*

**Files:** Modify `backend/app/api/v1/schemas/resume.py`, `backend/app/api/v1/resumes.py`, `backend/app/core/rate_limit.py`, `backend/tests/core/test_rate_limit.py`. Create `backend/tests/api/test_resumes_versions.py` (DB — CI-deferred), `backend/tests/worker/test_tailoring_task.py` (DB — CI-deferred).

**Interfaces:**
- Consumes: `TailoringService` (Task 6); `DocumentRenderer` + `RenderUnavailable` (Task 4); `AgentService` (Phase 7a — `create_session`, `start_run`); `ResumeService` (`get`); `CurrentUser`/`DbDep`; `app.core.errors.{NotFoundError, ValidationAppError}`; `ResumeExtraction`.
- Produces:
  - `schemas/resume.py`: `TailorIn { job_id: uuid.UUID }` (`extra="forbid"`); `ResumeVersionOut { id, kind, label: str|None, job_id: uuid|None, parent_version_id: uuid|None, created_by, created_at, claim_validation: dict[str,Any] }`; `ResumeVersionListOut { items: list[ResumeVersionOut] }`; `ResumeVersionDetailOut(ResumeVersionOut) { content: dict[str,Any] }`; `FieldDeltaOut { path, op, before: Any, after: Any }`; `ResumeDiffOut { deltas: list[FieldDeltaOut] }`. Explicit mappers, no `from_attributes` on the detail/diff shapes.
  - `resumes.py` routes (all `Depends(get_current_user)`):
    - `POST /resumes/{resume_id}/tailor` → **202** `RunRefOut` (reuse the Phase-7a `schemas/ai.py` `RunRefOut`, or a local `{run_id: str}`). Load résumé (user guard); if `confirmed_at is None` → `ValidationAppError("Confirm this résumé before tailoring it.")`. `s = await AgentService(db).create_session(user.id, kind="agent_run")`; `run_id = await AgentService(db).start_run(user.id, s.id, goal="tailor_resume", inputs={"job_id": str(body.job_id), "resume_id": str(resume_id)})`; `await db.commit()`; return.
    - `GET /resumes/{resume_id}/versions` → `ResumeVersionListOut` via `TailoringService.list_versions`.
    - `GET /resumes/versions/{version_id}` → `ResumeVersionDetailOut`.
    - `GET /resumes/versions/{version_id}/diff` → `?against: str | None` (a version id or `"base"`; default = the version's `parent_version_id`, else its résumé's base snapshot). `ResumeDiffOut` from `version_service.diff(<against>.content→ResumeExtraction, <version>.content→ResumeExtraction)`.
    - `GET /resumes/versions/{version_id}/render` → `?fmt=md|html|pdf|docx` (default `md`). Load version (user guard); `ResumeExtraction.model_validate(version.content)`; `DocumentRenderer().render(cv, RenderFormat(fmt))` → a `fastapi.Response(content=doc.data, media_type=doc.media_type)`. On `RenderUnavailable` → **409** `raise` a `ValidationAppError`-style or a bare `Response(status_code=409, ...)` with `{"code": "render_unavailable"}`.
  - `rate_limit.py` `_bucket`: before the `auth` check, `if method == "POST" and path.endswith("/tailor"): return "llm"`.
  - `router.py`: no change (routes are on the existing `resumes` router).

- [ ] **Step 1: extend `tests/core/test_rate_limit.py`** — in `test_bucket_classifies_llm_tier`: `assert _bucket("/api/v1/resumes/abc/tailor", "POST") == "llm"` and `assert _bucket("/api/v1/resumes/abc/tailor", "GET") == "read"`.

- [ ] **Step 2: DB tests** (CI-deferred, must COLLECT):
  - `tests/api/test_resumes_versions.py` — `client` + `_auth` from `tests/api/test_matches.py`. Seed a user, a confirmed `Resume` (with an `extraction`), a `Job`. Cases: `POST /resumes/{id}/tailor {job_id}` → 202 `{run_id}` (the `_no_enqueue` autouse fixture stubs `run_agent`); `POST` on an unconfirmed résumé → 422; `GET /resumes/{id}/versions` after manually inserting a `ResumeVersion` → 200 list; `GET /resumes/versions/{vid}` → 200 with `content`; `GET …/diff` between two seeded versions → `deltas` non-empty; `GET …/render?fmt=md` → 200 `text/markdown` body has the name.
  - `tests/worker/test_tailoring_task.py` — seed user + confirmed résumé + job; `AgentService.start_run(goal="tailor_resume", inputs={...})`; monkeypatch `_session_for` to the shared `db_session` (mirror `tests/worker/test_agent_task.py`); `await run_agent({}, run_id)`; assert: session `completed`; a `resume_versions` row `kind="ai_tailored"` exists for the résumé with `generation_meta.claim_validation` populated; an assistant `Message` with a `resume_suggestion` block; `agent_steps` rows for `resume_tailoring` + `claim_validator`; `ai_actions` logged.

- [ ] **Step 3: Run — expect `--collect-only` import errors** until the schemas/routes exist.

- [ ] **Step 4: Implement** schemas → routes → `rate_limit`. Mirror `app/api/v1/matches.py` for mapper + route style and `app/api/v1/ai.py` for the `start_run` + `db.commit()` shape. `get_session` dependency auto-commits, but the tailor/route explicitly `await db.commit()` before returning the 202 (the run outlives the request) — Phase-6 R9 precedent.

- [ ] **Step 5: Gates** —
```
"$UV" run pytest tests/core/test_rate_limit.py -q
"$UV" run ruff check .
"$UV" run mypy app
"$UV" run lint-imports
"$UV" run pytest -q --collect-only 2>&1 | tail -3
"$UV" run python -c "
import os
for k,v in {'DATABASE_URL':'postgresql+asyncpg://x','DATABASE_URL_TEST':'postgresql+asyncpg://x','REDIS_URL':'redis://x','JWT_SECRET':'x','EMBEDDINGS_PROVIDER':'fake','LLM_PROVIDER':'fake','SEARCH_PROVIDER':'fake'}.items(): os.environ.setdefault(k,v)
from app.main import create_app
print(sorted(p for p in create_app().openapi()['paths'] if 'resumes' in p and ('version' in p or 'tailor' in p)))
"
```
Expected: rate-limit tests pass; ruff/mypy clean; `3 kept`; collect error-free; OpenAPI lists `/api/v1/resumes/{resume_id}/tailor`, `/api/v1/resumes/{resume_id}/versions`, `/api/v1/resumes/versions/{version_id}`, `/api/v1/resumes/versions/{version_id}/diff`, `/api/v1/resumes/versions/{version_id}/render`.

- [ ] **Step 6: Commit**
```bash
git add backend/app/api/v1/schemas/resume.py backend/app/api/v1/resumes.py backend/app/core/rate_limit.py backend/tests/core/test_rate_limit.py backend/tests/api/test_resumes_versions.py backend/tests/worker/test_tailoring_task.py
git commit -m "feat(resume): /resumes tailor + versions + diff + render API"
```

---

## Task 10: verification & Phase 8a completion report

- [ ] **Step 1: Full backend gate** — from `backend/`: `"$UV" run ruff check . && "$UV" run lint-imports && "$UV" run mypy app && "$UV" run pytest -q --collect-only 2>&1 | tail -3`. All clean; `Contracts: 3 kept, 0 broken`; collect error-free. Then the pure suites: `"$UV" run pytest tests/domain/generation tests/domain/documents tests/domain/resume/test_tailoring.py tests/domain/resume/test_version_diff.py tests/domain/agents/test_nodes_tailoring.py tests/domain/agents/test_graph_tailor.py tests/core/test_rate_limit.py -q` — all pass.
- [ ] **Step 2: No-libpq import check** — `"$UV" run python -c "import app.domain.agents.graph, app.domain.agents.nodes.resume_tailoring, app.domain.agents.nodes.claim_validator, app.api.v1.resumes, app.domain.documents.renderer; print('ok')"` (with the dummy env vars from Task 9 Step 5).
- [ ] **Step 3: `alembic heads`** → single `0011_resume_tailoring`. OpenAPI has the 5 new `/resumes` paths.
- [ ] **Step 4: Fill the completion report below; commit** `docs: Phase 8a completion report`.

---

## Phase 8a completion report (fill in when done)

- **What changed:** _[generation service; ClaimValidator + tailor_resume; DocumentRenderer; resume_versions/resume_chunks/resume_suggestions + migration 0011; TailoringService + résumé diff; resume_tailoring + claim_validator nodes + tailor_resume route + graph wiring; /resumes tailor/versions/diff/render API + llm rate bucket]_
- **Why:** roadmap row 8 — a job-specific résumé the user can review as a diff, with a claim-grounding gate. The generation service + renderer are the surface Phases 9–10 (cover letter, email) extend.
- **Files changed / new deps:** _[list; +markdown-it-py, +xhtml2pdf, +python-docx]_
- **How to test:** `cd backend && "$UV" run pytest tests/domain/generation tests/domain/documents tests/domain/resume tests/domain/agents tests/worker/test_tailoring_task.py tests/api/test_resumes_versions.py tests/models/test_resume_version_model.py -q` (DB suites run in CI) · pure suites run locally
- **Regression check:** Phases 0–7 suites green; alembic chain `…→0010→0011` linear, single head; `import-linter` 3 contracts kept; `/ai`, `/jobs`, `/matches`, `/eval` unchanged; the `understand_job` / `enrich_job` graph paths unchanged (supervisor gains one branch, respond gains one leading branch); no libpq needed for lint/type/collect.
- **Baseline:** _[backend collect N → M; import contracts 3 → 3; mypy N → M files]_
- **As-built rulings:** _[R-tsv (resume_chunks Computed tsv follows job_chunks); any mypy overrides added for markdown-it/xhtml2pdf/python-docx; whether to_pdf/to_docx render on the dev box or raise RenderUnavailable; any plan self-corrections]_
- **Deviations / out of scope:** cover letter / email / approval / send — Phases 9–10; `resume_chunks` populated + retrieval — Phase 12; persisting rendered docs to `FileStore` — later; `ResumeVersionBlock` in the registry — 8b (8a reuses `resume_suggestion` stub); `manual_edit` in-place editing — later; generation LLM-judge eval — Phase 9.
- **Not verified here:** real tailoring quality (fake LLM); real PDF/DOCX fidelity; the diff on large résumés; concurrent tailor runs on one résumé.

---

## Self-Review

**1. Spec coverage (§1–§8):**
- §1 `generation` service (`GenerationService`, `GenerationMeta`, `GenerationResult`, `GenerationError`, `PROMPT_VERSION`) → Task 2. ✓
- §2 `ClaimValidator` + `tailor_resume` (≤2 reprompts) → Task 3. ✓
- §3 `DocumentRenderer` (md/html always, pdf/docx best-effort + `RenderUnavailable` + kill-switch) → Task 4. ✓
- §4 nodes (`resume_tailoring`, `claim_validator`) + `tailor_resume` goal + supervisor + respond + graph wiring → Tasks 7–8. ✓
- §5 models + migration `0011` (3 tables, triggers on 2, `job_chunks`-style `resume_chunks`) → Task 5. ✓
- §6 `TailoringService` + deterministic `diff` → Task 6. ✓
- §7 `/resumes` tailor/versions/diff/render API + `llm` bucket → Task 9. ✓
- §8 config `doc_render_enabled` + deps + no new import contract → Tasks 1, 4. ✓

**2. Placeholder scan:** every code step carries literal code or an exact Produces contract with the algorithm named. The `...` in Task 3/4/6 bodies are paired with a spec section reference + the exact constants/keys. No "TBD".

**3. Type consistency:**
- `GenerationResult`/`GenerationMeta` (Task 2) — consumed by `tailor_resume` (Task 3), whose returned `meta` is stored as `resume_versions.generation_meta` (Task 5/6) and surfaced as `ResumeVersionOut.claim_validation` (Task 9).
- `ResumeExtraction` (existing) — the one canonical résumé type: `tailor_resume` in/out (Task 3), `resume_versions.content` (Task 5), `diff` args (Task 6), `DocumentRenderer` input (Task 4), `render` route (Task 9).
- `ClaimReport.as_dict()` (Task 3) — the `claim_validation` dict on `GenerationMeta` and in `_detail` from `resume_tailoring` (Task 7).
- `FieldDelta`/`ResumeDiff` (Task 6) → `FieldDeltaOut`/`ResumeDiffOut` (Task 9).
- `AgentGoal += "tailor_resume"` (Task 7) — routed by `supervisor` (Task 7), consumed by `AgentService.start_run` (Task 9 call site), wired in `graph.py` (Task 8).
- `ResumeSuggestionBlock` (Phase-7a `blocks.py`, stub kind `resume_suggestion`, field `suggestion_id: uuid.UUID`) — emitted by `respond` (Task 7) carrying the version id.
- migration chain `0010_ai → 0011_resume_tailoring` (Task 5). ✓
- `import-linter` 3 contracts unchanged — `generation`/`documents` are `domain` leaves; `agents` nodes importing `generation`/`resume`/`profile`/`jobs` are same-layer (agents is not leaf-ward). ✓
