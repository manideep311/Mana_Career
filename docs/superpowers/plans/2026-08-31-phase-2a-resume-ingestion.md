# Phase 2a — Résumé Ingestion (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** A signed-in user can `POST` a PDF résumé and the system stores it, parses the text, extracts a structured career profile with an LLM against a strict schema, streams status over SSE, and — on the user's confirmation — merges the extraction into their `career_profiles` + sub-entity tables (as `source="resume_extraction"` rows) and rescored strength.

**Architecture:** New `app/infra/storage/` (`FileStore` interface + local adapter) and `app/domain/resume/` (`ResumeParser` behind an interface — pure-Python `pypdf` default, OCR stub; `ResumeExtractor` = one bounded `LLMProvider.complete(schema=…)` call; `ResumeService` orchestrates upload → enqueue → confirm-merge). Two ARQ tasks (`parse_resume` → `extract_resume`) run the pipeline; each publishes a status line to a Redis channel that the new `GET /resumes/{id}/events` SSE endpoint relays. This phase also brings the **Claude adapter** online (`AnthropicAdapter.complete()` with structured output via a forced tool call) — the résumé extractor is the project's first real LLM consumer; streaming + agent tool-calling still land in Phase 7. CI keeps `LLM_PROVIDER=fake`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, ARQ + Redis, `pypdf` (text), `filetype` (MIME sniff), `anthropic` (Claude adapter), `sse-starlette` for the event stream. `uv` is available at `C:\Users\chitt\AppData\Local\Microsoft\WinGet\Links\uv.exe` (or `…\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`) — dependency changes regenerate `backend/uv.lock`; CI runs `uv sync --frozen`.

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` — implements Phase 2 of §9 (backend half), and §2.2 (`resume/`), §2.1 (worker), §5.3 (`resumes` table), §6.2 (`/resumes`), §6 SSE contract, §3.1/§3.2 J1 (the upload→extract→confirm spine, UI in Phase 2b).

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtimes:** Python 3.12; PostgreSQL 16 + `pgvector`; Redis 7. Migrations continue the chain (`0004_career_profiles` is head).
- **PKs / timestamps / enums / soft-delete / user isolation / audit:** exactly as Phase 1a/1b — `uuid` `gen_random_uuid()`; `timestamptz` + `set_updated_at` trigger; `text` + named `CHECK`; `deleted_at` on user content; `user_id NOT NULL` on user-scoped tables; append-only `audit_logs` via the one `audit()` helper; `import-linter` layers `api > worker > domain > core > models`, `domain/*` never imports `api`/`worker`.
- **API:** base `/api/v1`; long operations return `202` + a resource carrying `status`; errors are RFC 9457 `application/problem+json` `{type,title,status,detail,instance,code,errors[]}` with a stable machine `code`; every response carries `X-Request-ID`.
- **File validation (spec §7.5 / §6.2):** on `POST /resumes` — MIME sniffed from the first bytes must be `application/pdf` (`filetype.guess`), size ≤ **10 MB**; after parse, page count ≤ **15**. Reject with `problem+json` codes `resume.not_pdf`, `resume.too_large`, `resume.too_many_pages`.
- **Statuses:** `resumes.status` ∈ `uploaded → parsing → parsed → extracting → extracted → failed` (`indexing`/`indexed` are Phase 6). `failed` always carries `parse_error` — a human sentence, e.g. "This looks like a scanned PDF — text extraction isn't available yet."
- **Extraction never invents (spec §5):** the `ResumeExtractor` prompt instructs the model to copy only what the résumé states and leave unknown fields null/empty — no guessed employers, dates, or skills.
- **`source` on merged sub-entities:** every row `confirm-profile` writes carries `source="resume_extraction"`. Re-confirming replaces the `resume_extraction`-sourced rows and never touches `source="user"` rows.
- **PII:** résumé text and extraction are user data — never logged at INFO; the existing `redact_secrets` log processor stays in force; `file_ref` keys never contain the filename.
- **LLM:** all model access via `get_llm_provider(settings)`. CI and tests run `LLM_PROVIDER=fake`. The Claude adapter is exercised by a mocked-SDK unit test + an opt-in real smoke test skipped without `ANTHROPIC_API_KEY`.
- **Workflow:** TDD, DRY, YAGNI, commit per green step. Commands from `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run lint-imports`, `uv run mypy app`. DB-backed tests need Postgres+Redis (CI provides them).

---

## File Structure

**Created**
- `backend/app/core/events.py` — SSE formatting + a Redis pub/sub relay (`publish_status`, `status_stream`).
- `backend/app/infra/__init__.py`, `backend/app/infra/storage/__init__.py`
- `backend/app/infra/storage/base.py` — `FileStore` Protocol.
- `backend/app/infra/storage/local.py` — `LocalFileStore`.
- `backend/app/infra/storage/factory.py` — `get_file_store(settings)`.
- `backend/app/domain/resume/__init__.py`
- `backend/app/domain/resume/parser.py` — `ResumeParser` Protocol, `ParsedResume`, `PypdfResumeParser`, `OcrResumeParser` (stub), `get_resume_parser(settings)`.
- `backend/app/domain/resume/extractor.py` — `ResumeExtraction` (+ nested item models), `ResumeExtractor`.
- `backend/app/domain/resume/service.py` — `ResumeService`.
- `backend/app/domain/llm/adapters/anthropic.py` — `AnthropicAdapter`.
- `backend/app/models/resume.py` — `Resume` ORM model.
- `backend/alembic/versions/0005_resumes.py`
- `backend/app/worker/tasks/resume.py` — `parse_resume`, `extract_resume`.
- `backend/app/api/v1/resumes.py` — the `/resumes` router.
- `backend/app/api/v1/schemas/resume.py` — request/response models.
- Tests alongside each unit under `backend/tests/`.

**Modified**
- `backend/pyproject.toml` + `backend/uv.lock` — add `pypdf`, `filetype`, `anthropic`, `sse-starlette`.
- `backend/app/core/config.py` — file-store + LLM-model + upload-limit settings.
- `backend/app/core/rate_limit.py` — add an `upload` bucket.
- `backend/app/domain/llm/factory.py` — wire `AnthropicAdapter`.
- `backend/app/models/__init__.py` — import `resume`.
- `backend/app/worker/main.py` + `backend/app/worker/tasks/__init__.py` — register the two tasks.
- `backend/app/api/v1/router.py` — include the resumes router.
- `backend/.env.example` + repo `.env.example` — document new vars.
- `backend/.gitignore` (or repo `.gitignore`) — ignore `backend/var/`.

---

## Task 1: Dependencies + config + upload rate-limit bucket

**Files:**
- Modify: `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/core/config.py`, `backend/app/core/rate_limit.py`, `backend/.env.example` (+ repo-root `.env.example`), repo-root `.gitignore`
- Test: `backend/tests/core/test_config.py` (extend), `backend/tests/core/test_rate_limit.py` (extend)

**Interfaces — Produces:**
- New `Settings` fields: `file_store: Literal["local","s3"] = "local"`; `file_store_local_dir: str = "./var/files"`; `resume_max_bytes: int = 10_485_760`; `resume_max_pages: int = 15`; `llm_model_extraction: str = "claude-haiku-4-5-20251001"`; `anthropic_model_fallback: str = "claude-sonnet-5"`.
- `rate_limit.py`: `_bucket(path, method)` gains an `"upload"` bucket — `method == "POST"` and path is `/api/v1/resumes` or `/api/v1/jobs` → `"upload"`; limit from new `Settings.upload_limit_per_hour: int = 20` applied over a **3600s** window. `RateLimitMiddleware.dispatch` passes `request.method` and uses a 3600s window for the upload bucket (60s for the others).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/core/test_config.py`:

```python
def test_resume_and_filestore_defaults(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.file_store == "local"
    assert s.file_store_local_dir == "./var/files"
    assert s.resume_max_bytes == 10_485_760
    assert s.resume_max_pages == 15
    assert s.llm_model_extraction == "claude-haiku-4-5-20251001"
    assert s.upload_limit_per_hour == 20
```

Append to `backend/tests/core/test_rate_limit.py`:

```python
def test_bucket_classifies_uploads():
    from app.core.rate_limit import _bucket

    assert _bucket("/api/v1/resumes", "POST") == "upload"
    assert _bucket("/api/v1/jobs", "POST") == "upload"
    assert _bucket("/api/v1/resumes", "GET") == "read"
    assert _bucket("/api/v1/auth/login", "POST") == "auth"
```

> If `_bucket` currently takes only `path`, this test defines the new 2-arg signature; the middleware change in Step 3 follows.

- [ ] **Step 2: Run — expect fail.**

Run: `cd backend && "$UV" run pytest tests/core/test_config.py tests/core/test_rate_limit.py -q` (where `$UV` is the uv path from Global Constraints).

- [ ] **Step 3: Implement.**

```bash
cd backend && "$UV" add pypdf filetype anthropic sse-starlette
```

`config.py` — add the fields listed under Produces (place near the existing LLM/embeddings block).

`rate_limit.py` — change `_bucket(path: str) -> str` to `_bucket(path: str, method: str) -> str`:

```python
def _bucket(path: str, method: str) -> str:
    base = get_settings().api_base_path
    if method == "POST" and path in (f"{base}/resumes", f"{base}/jobs"):
        return "upload"
    if path.startswith(f"{base}/auth"):
        return "auth"
    return "read"
```

In `RateLimitMiddleware.dispatch`, compute `bucket = _bucket(path, request.method)`, pick `limit` (`AUTH_LIMIT_PER_MINUTE` / `settings.upload_limit_per_hour` / `settings.rate_limit_default_per_minute`) and `window` (`60` / `3600` / `60`) by bucket, and pass `window_seconds=window` to `check_rate_limit`.

`.env.example` (both copies) — add:

```bash
FILE_STORE=local
FILE_STORE_LOCAL_DIR=./var/files
RESUME_MAX_BYTES=10485760
RESUME_MAX_PAGES=15
UPLOAD_LIMIT_PER_HOUR=20
LLM_MODEL_EXTRACTION=claude-haiku-4-5-20251001
ANTHROPIC_MODEL_FALLBACK=claude-sonnet-5
```

Repo-root `.gitignore` — add `backend/var/`.

- [ ] **Step 4: Run — expect pass.**

Run: `cd backend && "$UV" run pytest tests/core -q && "$UV" run ruff check . && "$UV" run mypy app`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/app/core/rate_limit.py backend/.env.example .env.example .gitignore backend/tests/core/test_config.py backend/tests/core/test_rate_limit.py
git commit -m "feat(core): résumé/file-store/LLM-model settings + upload rate-limit bucket"
```

---

## Task 2: `FileStore` interface + local adapter

**Files:**
- Create: `backend/app/infra/__init__.py` (empty), `backend/app/infra/storage/__init__.py` (empty), `backend/app/infra/storage/base.py`, `backend/app/infra/storage/local.py`, `backend/app/infra/storage/factory.py`
- Test: `backend/tests/infra/__init__.py`? **No** — rootless test layout, no `__init__.py` under `tests/`. Just `backend/tests/infra/test_local_store.py`.

**Interfaces — Produces:**
- `app.infra.storage.base.FileStore` (Protocol): `async put(key: str, data: bytes, *, content_type: str) -> None`; `async get(key: str) -> bytes` (raises `NotFoundError` if absent); `async delete(key: str) -> None` (idempotent); `async exists(key: str) -> bool`.
- `app.infra.storage.local.LocalFileStore(root: str)` — stores at `Path(root) / key`; creates parent dirs; `get` on a missing key raises `app.core.errors.NotFoundError(code="file_not_found")`; path-traversal guard (`key` may not contain `..` or start with `/`).
- `app.infra.storage.factory.get_file_store(settings: Settings) -> FileStore` — `"local"` → `LocalFileStore(settings.file_store_local_dir)`; `"s3"` → `raise NotImplementedError("S3 file store lands later")`.
- **Import-linter:** `app.infra` is a new package. `app.domain.resume.service` imports `app.infra.storage`, so `infra` sits **below** `domain` in the layered contract. Change `backend/.importlinter`'s `layers` list from `app.api / app.worker / app.domain / app.core / app.models` to `app.api / app.worker / app.domain / app.infra / app.core / app.models`. That permits `api`/`worker`/`domain` → `infra` → `core`/`models`, and forbids `infra` → `domain`/`worker`/`api`. `app.infra.storage.base` imports only `app.core.errors` — within-layer-down, allowed. Add a one-line note in the commit body.

- [ ] **Step 1: Write the failing test**

`backend/tests/infra/test_local_store.py`:

```python
import pytest

from app.core.errors import NotFoundError
from app.infra.storage.local import LocalFileStore


@pytest.fixture
def store(tmp_path) -> LocalFileStore:
    return LocalFileStore(str(tmp_path))


async def test_put_get_delete_roundtrip(store: LocalFileStore):
    await store.put("resumes/u1/r1.pdf", b"%PDF-1.7 ...", content_type="application/pdf")
    assert await store.exists("resumes/u1/r1.pdf") is True
    assert await store.get("resumes/u1/r1.pdf") == b"%PDF-1.7 ..."
    await store.delete("resumes/u1/r1.pdf")
    await store.delete("resumes/u1/r1.pdf")  # idempotent
    assert await store.exists("resumes/u1/r1.pdf") is False


async def test_get_missing_raises_not_found(store: LocalFileStore):
    with pytest.raises(NotFoundError):
        await store.get("nope/missing.pdf")


@pytest.mark.parametrize("bad", ["../escape.pdf", "/abs/path.pdf", "a/../../b.pdf"])
async def test_rejects_path_traversal(store: LocalFileStore, bad: str):
    with pytest.raises(ValueError):
        await store.put(bad, b"x", content_type="application/pdf")
```

- [ ] **Step 2: Run — expect fail** (`ModuleNotFoundError: app.infra`).

- [ ] **Step 3: Implement** the three modules. `LocalFileStore` uses `anyio.Path` or `asyncio.to_thread` for the blocking file IO (keep it simple: `await asyncio.to_thread(path.write_bytes, data)` etc.). Traversal guard: `if key.startswith("/") or ".." in Path(key).parts: raise ValueError(...)`. Update `backend/.importlinter`.

- [ ] **Step 4: Run — expect pass.**

Run: `cd backend && "$UV" run pytest tests/infra -q && "$UV" run lint-imports && "$UV" run ruff check . && "$UV" run mypy app`

- [ ] **Step 5: Commit**

```bash
git add backend/app/infra/ backend/.importlinter backend/tests/infra/
git commit -m "feat(infra): FileStore interface + local filesystem adapter"
```

---

## Task 3: `Resume` model + migration `0005`

**Files:**
- Create: `backend/app/models/resume.py`, `backend/alembic/versions/0005_resumes.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/test_resume_model.py`

**Interfaces — Produces:**
- `app.models.resume.Resume` (`Base`, `TimestampMixin`): `id` uuid pk · `user_id` uuid FK `users.id` CASCADE, not null · `title` `String(200)` · `original_filename` `String(300)` · `file_ref` `String(400)` not null · `content_type` `String(100)` not null · `size_bytes` `BigInteger` not null · `page_count` `Integer` (nullable until parsed) · `status` `String(16)` not null server_default `'uploaded'`, `CHECK status in ('uploaded','parsing','parsed','extracting','extracted','failed')` · `parse_error` `Text` · `extracted_text` `Text` · `extraction` `JSONB` · `is_primary` `Boolean` not null server_default `false` · `confirmed_at` `TIMESTAMP(tz)` (nullable, no default — set by `ResumeService.confirm_profile`) · `deleted_at` `TIMESTAMP(tz)` · ts.
- Indexes: `ix_resumes_user_created` on `(user_id, created_at DESC)`; **partial-unique** `uq_resumes_user_primary` on `(user_id)` `WHERE is_primary AND deleted_at IS NULL`.
- Migration `0005_resumes` (`down_revision = "0004_career_profiles"`): the table + the two indexes + the `updated_at` trigger + the CHECK.

- [ ] **Step 1: Write the failing test**

`backend/tests/models/test_resume_model.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.resume import Resume
from app.models.user import User


async def _user(db_session, email="r@example.com") -> User:
    u = User(email=email, password_hash="x", full_name="R")
    db_session.add(u)
    await db_session.flush()
    return u


async def test_defaults(db_session):
    u = await _user(db_session)
    r = Resume(user_id=u.id, file_ref="resumes/x.pdf", content_type="application/pdf",
               size_bytes=1234, original_filename="cv.pdf")
    db_session.add(r)
    await db_session.flush()
    got = (await db_session.execute(select(Resume).where(Resume.id == r.id))).scalar_one()
    assert got.status == "uploaded"
    assert got.is_primary is False
    assert got.page_count is None
    assert got.confirmed_at is None


async def test_status_check(db_session):
    u = await _user(db_session, "s@example.com")
    r = Resume(user_id=u.id, file_ref="f", content_type="application/pdf", size_bytes=1)
    r.status = "weird"
    db_session.add(r)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_primary_per_user(db_session):
    u = await _user(db_session, "p@example.com")
    for i in range(2):
        db_session.add(Resume(user_id=u.id, file_ref=f"f{i}", content_type="application/pdf",
                              size_bytes=1, is_primary=True))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** the model, migration, and `models/__init__.py` import (`from app.models import resume as resume`). Migration index for the partial unique:

```python
op.create_index("uq_resumes_user_primary", "resumes", ["user_id"], unique=True,
                postgresql_where=sa.text("is_primary AND deleted_at IS NULL"))
op.create_index("ix_resumes_user_created", "resumes", ["user_id", sa.text("created_at DESC")])
```

- [ ] **Step 4: Run — expect pass** (`"$UV" run alembic upgrade head` then `"$UV" run pytest tests/models/test_resume_model.py tests/core/test_migrations.py -q`; + ruff + mypy).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/resume.py backend/app/models/__init__.py backend/alembic/versions/0005_resumes.py backend/tests/models/test_resume_model.py
git commit -m "feat(models): resumes table (upload → extraction lifecycle)"
```

---

## Task 4: `ResumeParser` — pypdf text + OCR stub

**Files:**
- Create: `backend/app/domain/resume/__init__.py` (empty), `backend/app/domain/resume/parser.py`
- Test: `backend/tests/domain/resume/test_parser.py` (+ a tiny generated PDF fixture helper inline)

**Interfaces — Produces:**
- `@dataclass(frozen=True) ParsedResume`: `text: str`, `page_count: int`.
- `ResumeParser` (Protocol): `async parse(data: bytes) -> ParsedResume`.
- `PypdfResumeParser` — `pypdf.PdfReader(BytesIO(data))`; `page_count = len(reader.pages)`; `text = "\n\n".join(p.extract_text() or "" for p in reader.pages).strip()`. Raises `app.core.errors.ValidationAppError(code="resume.unreadable_pdf")` if `pypdf` cannot open it.
- `OcrResumeParser` — stub: `async parse` raises `app.core.errors.ValidationAppError(code="resume.ocr_unavailable", detail="This looks like a scanned PDF — text extraction isn't available yet.")`.
- `get_resume_parser(settings) -> ResumeParser` — always `PypdfResumeParser()` for now (OCR is chosen by the *service* based on text yield, not config).
- Module constant `MIN_DIGITAL_TEXT_CHARS = 120` — below this the service treats the PDF as scanned.

> **DEVIATION from spec §2.2 (PyMuPDF):** `pypdf` is used instead — pure-Python, BSD-licensed (PyMuPDF is AGPL), no compiled wheel (keeps CI simple). The `ResumeParser` interface preserves the spec's intent; a `PymupdfResumeParser` can be dropped in later if digital-PDF extraction quality proves insufficient.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/resume/test_parser.py`:

```python
import io

import pytest
from pypdf import PdfWriter

from app.core.errors import ValidationAppError
from app.domain.resume.parser import OcrResumeParser, PypdfResumeParser


def _pdf_bytes(pages: int = 1) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


async def test_parses_page_count():
    parsed = await PypdfResumeParser().parse(_pdf_bytes(pages=3))
    assert parsed.page_count == 3
    assert isinstance(parsed.text, str)


async def test_rejects_non_pdf_bytes():
    with pytest.raises(ValidationAppError):
        await PypdfResumeParser().parse(b"this is not a pdf")


async def test_ocr_stub_raises():
    with pytest.raises(ValidationAppError):
        await OcrResumeParser().parse(_pdf_bytes())
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** Wrap the blocking `pypdf` calls in `await asyncio.to_thread(...)`.

- [ ] **Step 4: Run — expect pass** (`"$UV" run pytest tests/domain/resume/test_parser.py -q` + ruff + mypy — this task is fully offline).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/resume/__init__.py backend/app/domain/resume/parser.py backend/tests/domain/resume/test_parser.py
git commit -m "feat(resume): pypdf text parser + OCR stub behind ResumeParser"
```

---

## Task 5: `ResumeExtraction` schema + `ResumeExtractor` (against the fake LLM)

**Files:**
- Create: `backend/app/domain/resume/extractor.py`
- Test: `backend/tests/domain/resume/test_extractor.py`

**Interfaces — Produces (`app.domain.resume.extractor`):**
- Pydantic models (all fields optional / defaulted so the fake's stub validates):
  - `ExtractedExperience { company: str; title: str; employment_type: str | None = None; start_date: str | None = None; end_date: str | None = None; is_current: bool = False; location: str | None = None; description: str | None = None; highlights: list[str] = []; tech: list[str] = [] }`
  - `ExtractedEducation { institution: str; degree: str | None; field: str | None; start_date: str | None; end_date: str | None; grade: str | None }`
  - `ExtractedProject { name: str; description: str | None; url: str | None; highlights: list[str] = []; tech: list[str] = []; start_date: str | None; end_date: str | None }`
  - `ExtractedCertification { name: str; issuer: str | None; issued_date: str | None; expires_date: str | None; credential_id: str | None; url: str | None }`
  - `ResumeExtraction { full_name: str | None; email: str | None; location: str | None; github_url: str | None; linkedin_url: str | None; portfolio_url: str | None; summary: str | None; skills: list[str] = []; experiences: list[ExtractedExperience] = []; education: list[ExtractedEducation] = []; projects: list[ExtractedProject] = []; certifications: list[ExtractedCertification] = [] }` — `model_config = ConfigDict(extra="ignore")`.
  - Dates are kept as **strings** (résumés write "Jun 2021", "2019–2022"); normalisation to real dates is Phase 3.
- `EXTRACTION_SYSTEM_PROMPT: str` — instructs: extract only what the text states; unknown → null / empty list; never infer employers, titles, dates, or skills not present; return every field of the schema.
- `class ResumeExtractor(llm: LLMProvider, *, model: str)`:
  - `async extract(self, text: str) -> ResumeExtraction` — builds `[{"role":"system", "content": EXTRACTION_SYSTEM_PROMPT}, {"role":"user","content": text[:20000]}]`, calls `await self.llm.complete(messages, schema=ResumeExtraction, max_tokens=4096)`, returns `ResumeExtraction.model_validate(result.structured)`. If `result.structured is None` raises `app.core.errors.AppError(code="resume.extraction_failed")`.
  - carries `last_usage: LLMResult | None` after a call (for the service to persist token/cost onto the resume's `extraction` meta later — Phase 2a just stores the model dump).

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/resume/test_extractor.py`:

```python
import json

import pytest

from app.core.errors import AppError
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMResult
from app.domain.resume.extractor import (
    ExtractedExperience,
    ResumeExtraction,
    ResumeExtractor,
)


async def test_extract_returns_validated_model_from_fake():
    ex = ResumeExtractor(FakeLLMProvider(), model="fake")
    out = await ex.extract("Jane Doe\nSenior ML Engineer at Acme 2021-2024\nPython, PyTorch")
    assert isinstance(out, ResumeExtraction)
    assert out.skills == [] and out.experiences == []  # fake returns schema stubs


async def test_extract_validates_a_real_structured_payload():
    payload = ResumeExtraction(
        full_name="Jane Doe", skills=["Python", "PyTorch"],
        experiences=[ExtractedExperience(company="Acme", title="ML Eng")],
    ).model_dump()

    class _Canned(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            base = await super().complete(messages, schema=None, max_tokens=max_tokens)
            return LLMResult(text=json.dumps(payload), model=base.model,
                             input_tokens=base.input_tokens, output_tokens=base.output_tokens,
                             cost_usd=0.0, structured=payload)

    out = await ResumeExtractor(_Canned(), model="fake").extract("...")
    assert out.full_name == "Jane Doe"
    assert out.skills == ["Python", "PyTorch"]
    assert [e.company for e in out.experiences] == ["Acme"]


async def test_extract_raises_when_no_structured():
    class _NoStructured(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            r = await super().complete(messages, schema=None, max_tokens=max_tokens)
            return r  # structured is None

    with pytest.raises(AppError):
        await ResumeExtractor(_NoStructured(), model="fake").extract("x")
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run — expect pass** (fully offline — `"$UV" run pytest tests/domain/resume/test_extractor.py -q` + ruff + mypy + `"$UV" run lint-imports`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/resume/extractor.py backend/tests/domain/resume/test_extractor.py
git commit -m "feat(resume): ResumeExtraction schema + schema-bound extractor"
```

---

## Task 6: `AnthropicAdapter` — real Claude `complete()`

**Files:**
- Create: `backend/app/domain/llm/adapters/anthropic.py`
- Modify: `backend/app/domain/llm/factory.py`
- Test: `backend/tests/domain/llm/test_anthropic_adapter.py`

**Interfaces — Produces:**
- `app.domain.llm.adapters.anthropic.AnthropicAdapter(api_key: str, *, default_model: str)` implementing `LLMProvider`:
  - `async complete(messages, *, schema=None, max_tokens=1024, temperature=0.2) -> LLMResult`:
    - system message(s) are joined into the `system=` kwarg; the rest map to `messages=[{role, content}]`.
    - **no `schema`** → `client.messages.create(model, system, messages, max_tokens, temperature)`; `text` = first `text` block; `structured=None`.
    - **`schema` given** → pass `tools=[{"name":"emit","description":"Return the structured result.","input_schema": schema.model_json_schema()}]` + `tool_choice={"type":"tool","name":"emit"}`; read the `tool_use` block's `.input`; `structured = schema.model_validate(tool_use.input).model_dump()`; `text = json.dumps(structured)`.
    - `input_tokens`/`output_tokens` from `response.usage`; `cost_usd` from a small module price map keyed by model (haiku/sonnet input+output $/Mtok — use the values in `docs` / the `claude-api` skill; if unknown, `0.0` and log once at DEBUG).
    - wrap `anthropic.APIError` → `app.core.errors.AppError(code="llm.upstream_error", detail=str(exc))`.
  - `capabilities()` → `LLMCapabilities(structured_output=True, tools=True, streaming=False)` (streaming is Phase 7).
- `factory.get_llm_provider(settings)` — `"anthropic"` → `AnthropicAdapter(settings.anthropic_api_key.get_secret_value(), default_model=settings.llm_model_extraction)` (raise `AppError(code="llm.not_configured")` if the key is `None`); `"openai"`/`"gemini"` still `NotImplementedError("… lands in Phase 7")`; `"fake"` unchanged.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/llm/test_anthropic_adapter.py`:

```python
import json
from types import SimpleNamespace

import pytest

from app.domain.llm.adapters.anthropic import AnthropicAdapter


class _FakeMessages:
    def __init__(self, block):
        self._block = block

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[self._block],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
            model=kwargs["model"],
        )


class _FakeClient:
    def __init__(self, block):
        self.messages = _FakeMessages(block)


async def test_text_completion(monkeypatch):
    block = SimpleNamespace(type="text", text="hello there")
    a = AnthropicAdapter("k", default_model="claude-haiku-4-5-20251001")
    monkeypatch.setattr(a, "_client", _FakeClient(block))
    out = await a.complete([{"role": "user", "content": "hi"}])
    assert out.text == "hello there"
    assert out.structured is None
    assert out.input_tokens == 11 and out.output_tokens == 7


async def test_structured_via_forced_tool(monkeypatch):
    from app.domain.resume.extractor import ResumeExtraction

    block = SimpleNamespace(type="tool_use", name="emit",
                            input={"full_name": "Jane", "skills": ["Python"]})
    a = AnthropicAdapter("k", default_model="claude-haiku-4-5-20251001")
    monkeypatch.setattr(a, "_client", _FakeClient(block))
    out = await a.complete([{"role": "user", "content": "resume text"}],
                           schema=ResumeExtraction)
    assert out.structured["full_name"] == "Jane"
    assert out.structured["skills"] == ["Python"]
    # forced tool_choice was sent
    assert a._client.messages.kwargs["tool_choice"]["name"] == "emit"


def test_capabilities():
    a = AnthropicAdapter("k", default_model="m")
    caps = a.capabilities()
    assert caps.structured_output and caps.tools and caps.streaming is False
```

> The adapter must build its real `anthropic.AsyncAnthropic` client lazily in `__init__` as `self._client` so the test can `monkeypatch.setattr` it. Do not call the network in `__init__`.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** Consult the `claude-api` skill for the current `AsyncAnthropic` surface + model ids + pricing before writing this file.

- [ ] **Step 4: Run — expect pass** (offline — SDK is mocked; `"$UV" run pytest tests/domain/llm -q` + ruff + mypy + lint-imports).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/llm/adapters/anthropic.py backend/app/domain/llm/factory.py backend/tests/domain/llm/test_anthropic_adapter.py
git commit -m "feat(llm): Claude adapter — complete() with forced-tool structured output"
```

---

## Task 7: `core/events.py` — SSE helper + Redis status relay

**Files:**
- Create: `backend/app/core/events.py`
- Test: `backend/tests/core/test_events.py`

**Interfaces — Produces (`app.core.events`):**
- `RESUME_CHANNEL = "resume:{id}".format` helper: `resume_channel(resume_id: str) -> str` → `f"sse:resume:{resume_id}"`.
- `async publish_status(redis, channel: str, *, resource: str, id: str, status: str, message: str | None = None) -> None` — `await redis.publish(channel, json.dumps({...}))`.
- `async status_stream(redis, channel: str, *, terminal: set[str]) -> AsyncIterator[dict]` — subscribes, yields each decoded payload as a dict, and **returns** (closing the stream) after yielding a payload whose `status` is in `terminal`. Also yields an initial `{"event":"open"}` sentinel and a periodic `{"event":"ping"}` every 15s so proxies don't drop the connection.
- `sse_event(payload: dict) -> ServerSentEvent` — maps `{event, data}` to `sse_starlette.ServerSentEvent(event=payload.get("event","status"), data=json.dumps(payload))`.
- The route layer (Task 10) wraps `status_stream` in `sse_starlette.EventSourceResponse`.

- [ ] **Step 1: Write the failing test**

`backend/tests/core/test_events.py` (uses the `fake_redis` fixture — extend it with async `publish` / `pubsub` if needed, or use a real Redis when `REDIS_URL` points at one; keep this test **not** requiring a real Redis by testing the pure helpers):

```python
import json

from app.core.events import resume_channel, sse_event


def test_resume_channel():
    assert resume_channel("abc") == "sse:resume:abc"


def test_sse_event_shape():
    ev = sse_event({"event": "status", "resource": "resume", "id": "r1",
                    "status": "parsed", "message": "Understood your résumé"})
    assert ev.event == "status"
    assert json.loads(ev.data)["status"] == "parsed"
```

> A DB/Redis-backed integration test for `publish_status`/`status_stream` round-trip lands in Task 10's API test (which has a real Redis in CI).

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** `status_stream` uses `redis.pubsub()`, `await pubsub.subscribe(channel)`, an `async for message in pubsub.listen()` loop with `asyncio.wait_for(..., timeout=15)` to interleave pings; `finally: await pubsub.unsubscribe(channel); await pubsub.aclose()`.

- [ ] **Step 4: Run — expect pass** (`"$UV" run pytest tests/core/test_events.py -q` + ruff + mypy).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/events.py backend/tests/core/test_events.py
git commit -m "feat(core): SSE helpers + Redis status relay for streaming resources"
```

---

## Task 8: `ResumeService`

**Files:**
- Create: `backend/app/domain/resume/service.py`
- Test: `backend/tests/domain/resume/test_service.py`

**Interfaces — Consumes:** `FileStore` + `get_file_store` (Task 2); `Resume` (Task 3); `ResumeExtraction` (Task 5); `ProfileService` + `SUBENTITY_MODELS` (Phase 1b `app.domain.profile.service`); `audit` + `current_request_id`; `worker.main.enqueue`; `get_settings`; `filetype`.

**Interfaces — Produces (`app.domain.resume.service.ResumeService(session, *, settings=None, file_store=None)`):**
- `async create(user_id, *, filename: str, data: bytes, declared_content_type: str) -> Resume` — sniff `filetype.guess(data[:261])`; not PDF → `ValidationAppError(code="resume.not_pdf")`; `len(data) > settings.resume_max_bytes` → `ValidationAppError(code="resume.too_large")`. `resume_id = uuid4()`; `key = f"resumes/{user_id}/{resume_id}.pdf"`; `await file_store.put(key, data, content_type="application/pdf")`; insert `Resume(id=resume_id, user_id, title=filename[:200], original_filename=filename[:300], file_ref=key, content_type="application/pdf", size_bytes=len(data), status="uploaded")`; if the user has **no** non-deleted résumé yet, set `is_primary=True`; `flush`; `await enqueue("parse_resume", str(resume_id))`; `audit("resume.upload", ...)`; return.
- `async get(user_id, resume_id) -> Resume` — `NotFoundError` if missing / other user / `deleted_at` set.
- `async list_(user_id) -> list[Resume]` — non-deleted, `created_at DESC`.
- `async update(user_id, resume_id, *, title=None, is_primary=None) -> Resume` — set fields; if `is_primary=True`, clear it on the user's other résumés first (in the same tx).
- `async delete(user_id, resume_id) -> None` — set `deleted_at`; `file_store.delete(file_ref)` (best-effort); `audit("resume.delete", ...)`.
- `async reprocess(user_id, resume_id) -> Resume` — reset `status="uploaded"`, `parse_error=None`; `await enqueue("parse_resume", str(resume_id))`; `audit("resume.reprocess", ...)`.
- `async confirm_profile(user_id, resume_id, extraction: ResumeExtraction) -> None` — the résumé must be `status="extracted"` (`ConflictError(code="resume.not_extracted")` otherwise). Via `ProfileService(session)`:
  1. `get_or_create(user_id)`; map `extraction`'s scalars onto the profile (`location`, `github_url`, `linkedin_url`, `portfolio_url`, `career_goals` ← `summary`) — only overwrite a profile field that is currently empty *or* whose current value came from a prior `resume_extraction` confirm (track via a `resumes.confirmed_at` timestamp + "last confirmed resume" — simplest: always overwrite from the newest confirm, since the user reviewed it).
  2. Delete the user's existing `source="resume_extraction"` rows in all four sub-entity tables; insert fresh rows from `extraction.experiences/education/projects/certifications` with `source="resume_extraction"`, `order_index` continuing after any `source="user"` rows.
  3. `ProfileService._recompute(profile)`.
  4. Set `resumes.confirmed_at = now()`.
  5. `audit("resume.confirm_profile", meta={"resume_id": str(resume_id), "counts": {...}})`.
  > Needs a `confirmed_at TIMESTAMP(tz)` column on `resumes` — **add it to Task 3's model + migration** (nullable, no default).

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/resume/test_service.py`:

```python
import uuid

import pytest

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.domain.auth.service import AuthService
from app.domain.resume.extractor import ExtractedExperience, ResumeExtraction
from app.domain.resume.service import ResumeService
from app.models.profile import ProfileExperience
from app.models.resume import Resume
from sqlalchemy import select


class _MemStore:
    def __init__(self): self.d = {}
    async def put(self, k, data, *, content_type): self.d[k] = data
    async def get(self, k): return self.d[k]
    async def delete(self, k): self.d.pop(k, None)
    async def exists(self, k): return k in self.d


async def _uid(db_session, email) -> uuid.UUID:
    reg = await AuthService(db_session).register(email, "correct-passphrase", "R",
                                                 ip=None, user_agent=None)
    return reg.user.id


def _svc(db_session):
    return ResumeService(db_session, file_store=_MemStore())


_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


async def test_create_rejects_non_pdf(db_session, monkeypatch):
    monkeypatch.setattr("app.worker.main.enqueue", lambda *a, **k: _noop())
    uid = await _uid(db_session, "np@example.com")
    with pytest.raises(ValidationAppError):
        await _svc(db_session).create(uid, filename="cv.txt", data=b"hello",
                                      declared_content_type="text/plain")


async def test_create_first_resume_is_primary(db_session, monkeypatch):
    calls = []
    async def fake_enqueue(task, *a, **k): calls.append((task, a))
    monkeypatch.setattr("app.domain.resume.service.enqueue", fake_enqueue)
    uid = await _uid(db_session, "pr@example.com")
    r = await _svc(db_session).create(uid, filename="cv.pdf", data=_PDF,
                                      declared_content_type="application/pdf")
    assert r.is_primary is True and r.status == "uploaded"
    assert calls == [("parse_resume", (str(r.id),))]


async def test_confirm_profile_requires_extracted(db_session, monkeypatch):
    monkeypatch.setattr("app.domain.resume.service.enqueue",
                        lambda *a, **k: _anoop())
    uid = await _uid(db_session, "cf@example.com")
    r = await _svc(db_session).create(uid, filename="cv.pdf", data=_PDF,
                                      declared_content_type="application/pdf")
    with pytest.raises(ConflictError):
        await _svc(db_session).confirm_profile(uid, r.id, ResumeExtraction())


async def test_confirm_profile_merges_experiences(db_session, monkeypatch):
    monkeypatch.setattr("app.domain.resume.service.enqueue",
                        lambda *a, **k: _anoop())
    uid = await _uid(db_session, "mg@example.com")
    svc = _svc(db_session)
    r = await svc.create(uid, filename="cv.pdf", data=_PDF,
                         declared_content_type="application/pdf")
    r.status = "extracted"
    await db_session.flush()
    await svc.confirm_profile(uid, r.id, ResumeExtraction(
        location="Berlin",
        experiences=[ExtractedExperience(company="Acme", title="ML Eng")],
    ))
    rows = (await db_session.execute(
        select(ProfileExperience).where(ProfileExperience.user_id == uid)
    )).scalars().all()
    assert [x.company for x in rows] == ["Acme"]
    assert all(x.source == "resume_extraction" for x in rows)
    fresh = (await db_session.execute(select(Resume).where(Resume.id == r.id))).scalar_one()
    assert fresh.confirmed_at is not None
```

> Provide small `_noop`/`_anoop` async helpers in the test module. The service must import `enqueue` as `from app.worker.main import enqueue` so the monkeypatch target `app.domain.resume.service.enqueue` works.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run — expect pass** (DB-backed — Postgres via CI; locally run ruff + mypy + lint-imports and confirm collection).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/resume/service.py backend/tests/domain/resume/test_service.py backend/app/models/resume.py backend/alembic/versions/0005_resumes.py
git commit -m "feat(resume): ResumeService — upload, lifecycle, confirm-profile merge"
```

---

## Task 9: ARQ tasks — `parse_resume` → `extract_resume`

**Files:**
- Create: `backend/app/worker/tasks/resume.py`
- Modify: `backend/app/worker/tasks/__init__.py`, `backend/app/worker/main.py`
- Test: `backend/tests/worker/test_resume_tasks.py`

**Interfaces — Produces (`app.worker.tasks.resume`):**
- `async parse_resume(ctx, resume_id: str) -> dict` — opens its own `AsyncSessionLocal`; loads the `Resume` (any user — worker is trusted); `status="parsing"` + `publish_status`; `data = await file_store.get(resume.file_ref)`; `parsed = await PypdfResumeParser().parse(data)`; if `parsed.page_count > settings.resume_max_pages` → `status="failed"`, `parse_error="This résumé has N pages; the limit is 15."`, publish, return; if `len(parsed.text) < MIN_DIGITAL_TEXT_CHARS` → `status="failed"`, `parse_error=` the scanned-PDF sentence, publish, return; else save `extracted_text`, `page_count`, `status="parsed"`, publish, then `await enqueue("extract_resume", resume_id)`. On any unexpected exception → `status="failed"`, `parse_error="We couldn't read this file."`, publish, `dead_letter.record_failure`, re-raise (ARQ retry).
- `async extract_resume(ctx, resume_id: str) -> dict` — own session; load; `status="extracting"` + publish; `extractor = ResumeExtractor(get_llm_provider(settings), model=settings.llm_model_extraction)`; `extraction = await extractor.extract(resume.extracted_text)`; save `resume.extraction = extraction.model_dump()`, `status="extracted"`, publish `message="Ready to review"`. On failure → `status="failed"`, `parse_error="We couldn't understand this résumé. Try re-uploading."`, publish, `record_failure`, re-raise.
- `worker/tasks/__init__.py` exports `parse_resume`, `extract_resume` (+ existing `ping`); `worker/main.py` `WorkerSettings.functions` includes all three.

- [ ] **Step 1: Write the failing test**

`backend/tests/worker/test_resume_tasks.py`:

```python
import uuid

import pytest
from sqlalchemy import select

from app.domain.auth.service import AuthService
from app.models.resume import Resume
from app.worker.tasks.resume import extract_resume, parse_resume


class _MemStore:
    def __init__(self, blob=b""): self.blob = blob
    async def get(self, k): return self.blob


async def _seed_resume(db_session, *, text_blob: bytes) -> tuple[uuid.UUID, Resume]:
    reg = await AuthService(db_session).register("wt@example.com", "correct-passphrase",
                                                 "W", ip=None, user_agent=None)
    r = Resume(user_id=reg.user.id, file_ref="k", content_type="application/pdf",
               size_bytes=len(text_blob), status="uploaded")
    db_session.add(r)
    await db_session.flush()
    return reg.user.id, r


async def test_parse_marks_scanned_pdf_failed(db_session, monkeypatch, fake_redis):
    import io
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(width=200, height=200)
    buf = io.BytesIO(); w.write(buf)
    _, r = await _seed_resume(db_session, text_blob=buf.getvalue())

    monkeypatch.setattr("app.worker.tasks.resume._session_for", lambda: _ctx(db_session))
    monkeypatch.setattr("app.worker.tasks.resume.get_file_store",
                        lambda s: _MemStore(buf.getvalue()))
    monkeypatch.setattr("app.worker.tasks.resume.redis_from_settings", lambda s: fake_redis)
    enq = []
    monkeypatch.setattr("app.worker.tasks.resume.enqueue",
                        lambda *a, **k: enq.append(a) or _anoop())

    await parse_resume({}, str(r.id))
    fresh = (await db_session.execute(select(Resume).where(Resume.id == r.id))).scalar_one()
    assert fresh.status == "failed"
    assert "scanned" in fresh.parse_error.lower()
    assert enq == []  # extract not enqueued
```

> The test needs a session seam. Give `parse_resume`/`extract_resume` an internal `_session_for()` that yields `AsyncSessionLocal()` in prod and is monkeypatched to the test's `db_session` (wrapped so `async with` works). Provide `_ctx`/`_anoop` helpers in the test module. `fake_redis` (conftest) already has async `publish`? — **extend the conftest `_FakeRedis` with `async def publish(self, ch, msg): return 0`** as part of this task (allowed conftest change, note it).

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run — expect pass** (DB-backed → CI; locally ruff + mypy + lint-imports + collection).

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker/tasks/resume.py backend/app/worker/tasks/__init__.py backend/app/worker/main.py backend/tests/worker/test_resume_tasks.py backend/tests/conftest.py
git commit -m "feat(worker): parse_resume → extract_resume pipeline with SSE status"
```

---

## Task 10: `/resumes` API + schemas

**Files:**
- Create: `backend/app/api/v1/resumes.py`, `backend/app/api/v1/schemas/resume.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/api/test_resumes.py`

**Interfaces — Produces:**
- `schemas/resume.py`: `ResumeOut` (`from_attributes`; `id, title, original_filename, content_type, size_bytes, page_count, status, parse_error, is_primary, confirmed_at, created_at, updated_at`); `ResumePatchIn { title: str | None = Field(None, max_length=200); is_primary: bool | None = None }` (`extra="forbid"`); `ConfirmProfileIn { extraction: ResumeExtraction }`.
- `resumes.py` `router = APIRouter(prefix="/resumes", tags=["resumes"])`, all routes `Depends(get_current_user)`:
  - `POST ""` — `UploadFile` (`file: Annotated[UploadFile, File()]`); read bytes, `ResumeService.create(user.id, filename=file.filename or "resume.pdf", data=bytes, declared_content_type=file.content_type or "")`; `201`? spec says `202` — return `202` + `ResumeOut`.
  - `GET ""` → `list[ResumeOut]`.
  - `GET "/{resume_id}"` → `ResumeOut`.
  - `GET "/{resume_id}/events"` → `EventSourceResponse(status_stream(redis, resume_channel(id), terminal={"extracted","failed"}))` mapped through `sse_event`; sends one immediate event with the current DB `status` so a late subscriber isn't stuck.
  - `GET "/{resume_id}/extraction"` → `ResumeExtraction` (`404` `code="resume.not_extracted"` if `status != "extracted"`).
  - `PATCH "/{resume_id}"` `ResumePatchIn` → `ResumeOut`.
  - `POST "/{resume_id}/reprocess"` → `202 ResumeOut`.
  - `DELETE "/{resume_id}"` → `204`.
  - `POST "/{resume_id}/confirm-profile"` `ConfirmProfileIn` → `204` (merge happens; the frontend refetches `/profile`).
- `router.py` — `api_router.include_router(resumes.router)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/api/test_resumes.py`:

```python
import io

from pypdf import PdfWriter


def _pdf(pages=1, text_pages=0) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=300, height=300)
    buf = io.BytesIO(); w.write(buf)
    return buf.getvalue()


async def _auth(client, email="res@example.com"):
    r = await client.post("/api/v1/auth/register",
                          json={"email": email, "password": "correct-passphrase",
                                "full_name": "Res"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_upload_returns_202_and_lists(client):
    h = await _auth(client)
    up = await client.post("/api/v1/resumes", headers=h,
                           files={"file": ("cv.pdf", _pdf(), "application/pdf")})
    assert up.status_code == 202
    body = up.json()
    assert body["status"] == "uploaded" and body["is_primary"] is True
    lst = await client.get("/api/v1/resumes", headers=h)
    assert [r["id"] for r in lst.json()] == [body["id"]]


async def test_upload_rejects_non_pdf(client):
    h = await _auth(client, "npdf@example.com")
    r = await client.post("/api/v1/resumes", headers=h,
                          files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 422 and r.json()["code"] == "resume.not_pdf"


async def test_extraction_404_until_extracted(client):
    h = await _auth(client, "ex@example.com")
    up = await client.post("/api/v1/resumes", headers=h,
                           files={"file": ("cv.pdf", _pdf(), "application/pdf")})
    rid = up.json()["id"]
    r = await client.get(f"/api/v1/resumes/{rid}/extraction", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "resume.not_extracted"


async def test_resume_is_user_scoped(client):
    h1 = await _auth(client, "o1@example.com")
    h2 = await _auth(client, "o2@example.com")
    rid = (await client.post("/api/v1/resumes", headers=h1,
                             files={"file": ("cv.pdf", _pdf(), "application/pdf")})).json()["id"]
    assert (await client.get(f"/api/v1/resumes/{rid}", headers=h2)).status_code == 404
    assert (await client.delete(f"/api/v1/resumes/{rid}", headers=h2)).status_code == 404
```

> The `client` fixture's app must use a real (or fake) `FileStore` and NOT hit the real ARQ Redis for enqueue — override `get_file_store` via `app.dependency_overrides` OR set `LLM_PROVIDER=fake` + a temp `FILE_STORE_LOCAL_DIR` (conftest already gives a test env; add `FILE_STORE_LOCAL_DIR` pointing at a `tmp_path`-like dir, and let `enqueue` no-op by pointing `REDIS_URL` at the CI Redis — enqueue succeeds, the worker just isn't running). Simplest: in `conftest.py` add an autouse fixture that monkeypatches `app.domain.resume.service.enqueue` to an async no-op for API tests. Note this conftest addition in the task.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run — expect pass** (DB+Redis → CI; locally ruff + mypy + lint-imports + `"$UV" run python -c "from app.main import create_app; print(sorted(p for p in create_app().openapi()['paths'] if 'resume' in p))"` with env vars).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/resumes.py backend/app/api/v1/schemas/resume.py backend/app/api/v1/router.py backend/tests/api/test_resumes.py backend/tests/conftest.py
git commit -m "feat(api): /resumes — upload, status SSE, extraction review, confirm-profile"
```

---

## Task 11: Phase 2a verification & report

- [ ] **Step 1: Full backend gate**

`cd backend && "$UV" run ruff check . && "$UV" run lint-imports && "$UV" run mypy app && "$UV" run pytest -q` — ruff clean; import-linter contracts kept (incl. the new `app.infra` layer); mypy clean; pytest green (Phase 0/1a/1b + Phase 2a), coverage ≥ CI floor.

- [ ] **Step 2: OpenAPI sanity**

`"$UV" run python -c "from app.main import create_app; import json; print(json.dumps(sorted(create_app().openapi()['paths']), indent=1))"` — the 8 `/api/v1/resumes*` paths present.

- [ ] **Step 3: Real-LLM smoke (opt-in, not a gate)**

If `ANTHROPIC_API_KEY` is set: a one-off `scripts/smoke_extract.py` that runs `ResumeExtractor(get_llm_provider(settings_with_anthropic), model=…).extract(<a real résumé's text>)` and prints the model — eyeball that it's not empty. Document the result in the report; do not add it to CI.

- [ ] **Step 4: Fill the completion report** below, commit `docs: Phase 2a completion report`.

---

## Phase 2a completion report (fill in when done)

- **What changed:** _[list]_
- **Why:** résumé → structured extraction is the on-ramp — every later phase (matching, tailoring, the agent) reads the profile this builds; it's also the project's first real LLM call.
- **Files changed / new deps:** _[list; `pypdf`, `filetype`, `anthropic`, `sse-starlette`]_
- **How to test:** `cd backend && "$UV" run pytest tests/domain/resume tests/api/test_resumes.py tests/worker/test_resume_tasks.py -q`.
- **Regression check:** Phase 0/1a/1b suites green; migration chain `0001→…→0005` linear; `/auth`, `/profile`, `/health` unchanged; `import-linter` contracts kept.
- **Baseline:** _[N backend tests, M% coverage]_
- **Deviations:** _[pypdf vs PyMuPDF (§2.2); Claude adapter pulled forward from Phase 7 for `complete()` only; …]_
- **Not verified here:** real extraction quality on varied résumé layouts (needs the opt-in smoke + Phase 2b's review UI in front of a human); date-string normalisation (Phase 3); résumé chunk embeddings (Phase 6).

---

## Self-Review

**1. Spec coverage (Phase 2 backend half of §9 + §2.2 / §5.3 / §6.2 / §6 SSE / §3.2 J1 spine):**
- `FileStore` (local) → Task 2. ✓
- `POST /resumes` + MIME/size/page validation → Tasks 1 (limits), 8 (create), 10 (route). ✓
- ARQ `parse_resume` → `extract_resume` → Task 9. ✓
- `ResumeParser` (pypdf, spec says PyMuPDF — deviation noted) + OCR **stub** → Task 4. ✓ (spec §12 explicitly allows a stub.)
- `ResumeExtractor` (LLM + schema) → Task 5; real Claude adapter → Task 6. ✓
- SSE status → Task 7 (`core/events.py`, deferred from Phase 0) + Task 10 (`GET /resumes/{id}/events`). ✓
- `confirm-profile` merge → Task 8 (`ResumeService.confirm_profile`) + Task 10 (route). ✓
- `resumes` table per §5.3 (+ `confirmed_at` for merge idempotency) → Task 3. ✓
- Audit on `resume.upload` / `.delete` / `.reprocess` / `.confirm_profile` → Task 8. ✓
- Upload rate-limit tier (§6.5, 20/hour) → Task 1. ✓
- **Deferred (their phases, flagged):** `resume_versions` / `resume_chunks` / `resume_suggestions` (Phases 6/8); date normalisation + skill-taxonomy mapping (Phase 3); the frontend upload → 3-stage stepper → review screen (Phase 2b); OpenTelemetry token/cost meter onto a row (Phase 7 — Task 5 keeps `last_usage` ready).

**2. Placeholder scan:** Tasks 1–7 carry literal code/tests; Tasks 8–10 give full interface contracts + concrete tests and describe the route/service bodies rather than transcribing every line (the shapes are pinned by the tests and the Produces blocks). Two deliberate seams (`_session_for` in Task 9, the `enqueue`/`get_file_store` monkeypatch points) are named explicitly so the tests can drive them. No "TBD".

**3. Type consistency:**
- `ResumeExtraction` + nested `Extracted*` models (Task 5) are consumed verbatim by Task 6's structured test, Task 8's `confirm_profile`, and Task 10's `ConfirmProfileIn` / `GET .../extraction`.
- `FileStore` method set (`put`/`get`/`delete`/`exists`, all async, `put` kw-only `content_type`) — Task 2 defines, Tasks 8 & 9 consume; the test `_MemStore`s match it.
- `Resume` columns (`status`, `parse_error`, `extracted_text`, `extraction`, `is_primary`, `confirmed_at`, `page_count`) — Task 3 defines; Tasks 8/9/10 reference the same names; `status` string set is identical everywhere (`uploaded/parsing/parsed/extracting/extracted/failed`).
- `resume_channel(id)` / `publish_status` / `status_stream(terminal=…)` (Task 7) — Task 9 publishes, Task 10 streams; terminal set `{"extracted","failed"}` matches the status enum.
- `get_llm_provider(settings)` returns an `LLMProvider` with the exact `complete(messages, *, schema, max_tokens, temperature) -> LLMResult` signature from `app/domain/llm/provider.py` — the `AnthropicAdapter` (Task 6) and `FakeLLMProvider` both satisfy it; `ResumeExtractor` (Task 5) calls only that.
- `enqueue(task, *args)` from `app.worker.main` — Task 8 & 9 import it from there; the tests monkeypatch `app.domain.resume.service.enqueue` / `app.worker.tasks.resume.enqueue`, which requires the `from app.worker.main import enqueue` import style (stated in both tasks).
- Migration chain: `0004_career_profiles` → `0005_resumes`. ✓

**4. Ambiguity check:** `confirm_profile` **replaces** `source="resume_extraction"` sub-entity rows and never touches `source="user"` rows (Task 8, asserted). Scalar profile fields are overwritten from the newest confirm (the user reviewed them) — not merged field-by-field. `parse_resume` decides scanned-vs-digital by `len(text) < MIN_DIGITAL_TEXT_CHARS` (120), not by config. The SSE stream closes on `status ∈ {extracted, failed}`, not on a fixed timeout.

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-08-31-phase-2a-resume-ingestion.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between.
**2. Inline Execution** — `superpowers:executing-plans`, batched with checkpoints.

**Environment:** `uv` is installed (path in Global Constraints) — every task's `ruff`/`mypy`/`import-linter` + offline tests run locally; DB+Redis-backed tests (Tasks 3, 8, 9, 10) verify in CI, which the last three phases have shown is reliable. The Claude adapter (Task 6) is unit-tested with a mocked SDK; the opt-in real smoke (Task 11 Step 3) needs `ANTHROPIC_API_KEY` and is not a gate. **Phase 2b** (upload UI → 3-stage stepper → extraction review screen → onboarding wiring) is a separate plan on top of this.
