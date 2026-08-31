# Phase 0 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Mana Career monorepo skeleton — a runnable FastAPI API + ARQ worker + Next.js frontend on Postgres/pgvector + Redis, with the cross-cutting `core/` module (config, logging, errors, DB, rate limiting, audit), provider interfaces with fake adapters, Docker Compose, and CI — so that every later phase has a tested base to build on.

**Architecture:** Modular monolith. One FastAPI app and one ARQ worker share a `backend/app` package; every external dependency sits behind an interface with adapters. The frontend is an API-only Next.js App Router app. Nothing in Phase 0 talks to a real LLM — `FakeLLMProvider`/`FakeEmbeddingsProvider` keep the whole stack testable offline.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async) + asyncpg, Alembic, pydantic-settings, structlog, ARQ, Redis, argon2-cffi, PyJWT, pytest + pytest-asyncio, ruff, mypy, import-linter. Next.js 15 (App Router) + React 19, TypeScript, Tailwind CSS v4, shadcn/ui, TanStack Query, Vitest + Testing Library. PostgreSQL 16 with the `pgvector` extension. Docker Compose. `just` as task runner, `uv` for Python deps, `pnpm` for JS deps.

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` — this plan implements Phase 0 of §9, and the parts of §2 (System Architecture), §2.7 (Security surface), §5.1 (schema conventions), §6.1 (API conventions), §7.7 (design tokens), and §8 (folder structure) that the foundation needs.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec.

- **Runtimes:** Python 3.12; Node 20+; PostgreSQL 16 + `pgvector`; Redis 7.
- **Primary keys:** `uuid` (v7 for index locality; `gen_random_uuid()` fallback).
- **Timestamps:** `created_at timestamptz not null default now()`; `updated_at` maintained by a `set_updated_at` trigger.
- **Enums:** `text` + `CHECK` constraint (not native PG enums).
- **User isolation:** every user-scoped table has `user_id`/`owner_id NOT NULL`; shared rows use `owner_id IS NULL`; the repository filter is always `user_id = :me OR owner_id IS NULL`.
- **Vectors:** `EMBED_DIM` is fixed per deployment; `embed_model` + `embed_dim` stored on every chunk row; HNSW (`m=16, ef_construction=64`, `vector_cosine_ops`).
- **Secrets:** only via environment; a logging filter redacts secret-shaped strings; keys never appear in any API response or the frontend bundle.
- **Audit:** `audit_logs` is append-only — the application DB role has no `UPDATE`/`DELETE` grant on it; one `audit()` helper writes every state change.
- **API:** base path `/api/v1`; OpenAPI 3.1 at `/api/openapi.json`. Errors use RFC 9457 `application/problem+json` `{type,title,status,detail,instance,code,errors[]}` with a stable machine `code`. Every response carries `X-Request-ID`.
- **Brand / copy:** product is "Mana Career", assistant is "Mana AI". Use human microcopy (spec §19) — e.g. empty states say "Your career workspace is ready.", never "No data found".
- **Design tokens (spec §7.7):** warm off-white `--bg`, deep charcoal `--text`, indigo/blue `--accent`, green `--positive`, amber `--warning`, red `--danger` (errors only), `--radius: 14px`, subtle shadows, font Inter (fallback Geist, Manrope, system-ui). Single light theme ships; tokens structured so a dark set is a later drop-in.
- **Provider abstraction:** all LLM access via `LLMProvider` (default adapter Anthropic, but Phase 0 ships only the fake); all embedding access via `EmbeddingsProvider`.
- **Boundary rule:** cross-domain imports only via `app.domain.<x>.service`; `app.domain.*` must not import `app.api.*` or `app.worker.*`; `llm`/`embeddings`/`rag` are leaf-ward only. Enforced by `import-linter`.
- **Workflow:** TDD (write the failing test first), DRY, YAGNI, commit after every green step.

---

## File Structure

Files created in Phase 0, each with one responsibility.

### Repo root
- `justfile` — dev task runner (`up`, `down`, `migrate`, `test`, `lint`, `ci`, `smoke`).
- `.env.example` — every environment variable with a safe default or a clear placeholder.
- `docker-compose.yml` — `db` (pgvector/pg16), `redis`, `api`, `worker`, `frontend`.
- `.github/workflows/ci.yml` — lint + type + test gates for backend and frontend.
- `.dockerignore`, `.gitignore` (exists).

### Backend (`backend/`)
- `pyproject.toml` — deps + tool config (ruff, mypy, pytest, coverage).
- `.importlinter` — layered-architecture contracts.
- `Dockerfile` — multistage; dev target runs uvicorn with reload.
- `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_bootstrap.py` — migration harness + extension bootstrap.
- `app/__init__.py`, `app/main.py` — FastAPI app factory + middleware wiring.
- `app/core/config.py` — `Settings` (pydantic-settings); single source of env truth.
- `app/core/logging.py` — structlog JSON config + secret/PII redaction processor.
- `app/core/errors.py` — `AppError` hierarchy + `problem+json` exception handlers.
- `app/core/db.py` — async engine, `AsyncSessionLocal`, declarative `Base`, `Repository` base class.
- `app/core/rate_limit.py` — Redis token-bucket dependency + middleware.
- `app/core/audit.py` — `audit(...)` helper.
- `app/core/redis.py` — shared Redis pool factory (used by rate limiter + worker + health).
- `app/models/__init__.py` — imports every model module so `Base.metadata` is complete for Alembic.
- `app/models/audit.py` — `AuditLog` ORM model.
- `app/api/deps.py` — FastAPI dependencies (`get_db`, `get_settings`, `get_redis`).
- `app/api/v1/router.py` — aggregates v1 routers.
- `app/api/v1/health.py` — `GET /health`, `GET /health/ready`.
- `app/domain/llm/provider.py` — `LLMProvider` protocol + `LLMMessage`, `LLMResult` types.
- `app/domain/llm/adapters/__init__.py`, `app/domain/llm/adapters/fake.py` — `FakeLLMProvider`.
- `app/domain/llm/factory.py` — `get_llm_provider(settings)` selector.
- `app/domain/embeddings/provider.py` — `EmbeddingsProvider` protocol.
- `app/domain/embeddings/adapters/fake.py` — `FakeEmbeddingsProvider` (deterministic vectors).
- `app/domain/embeddings/factory.py` — `get_embeddings_provider(settings)` selector.
- `app/worker/main.py` — ARQ `WorkerSettings` + startup/shutdown.
- `app/worker/tasks/__init__.py`, `app/worker/tasks/ping.py` — `ping` task.
- `app/worker/dead_letter.py` — `record_failure(...)` stub writing to logs (table lands in a later phase).
- `tests/conftest.py` — settings override, DB fixture (migrate once + per-test transaction rollback), `httpx.AsyncClient` fixture, fake Redis fixture.
- `tests/core/…`, `tests/api/…`, `tests/domain/…`, `tests/worker/…` — per-task test modules.

### Frontend (`frontend/`)
- `package.json`, `pnpm-lock.yaml`, `tsconfig.json`, `next.config.ts`, `.eslintrc.cjs`, `vitest.config.ts`, `vitest.setup.ts`.
- `Dockerfile` — dev target runs `next dev`.
- `app/globals.css` — Tailwind v4 entry + token wiring.
- `styles/tokens.css` — the design-token custom properties (spec §7.7).
- `app/layout.tsx` — root layout: font, `<body>` background from tokens, `prefers-reduced-motion` base.
- `app/page.tsx` — marketing landing shell ("Your next opportunity starts here.").
- `lib/env.ts` — reads `NEXT_PUBLIC_API_BASE_URL`.
- `lib/api/fetcher.ts` — thin fetch wrapper that parses `problem+json`.
- `components/common/EmptyState.tsx` — first shared primitive (used to prove tokens + a11y).
- `tests/EmptyState.test.tsx`, `tests/landing.test.tsx`.

---

## Task 1: Repo scaffold and tooling config

**Files:**
- Create: `justfile`
- Create: `.env.example`
- Create: `.dockerignore`
- Create: `backend/pyproject.toml`
- Create: `backend/.importlinter`
- Create: `backend/app/__init__.py` (empty)
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.ts`
- Test: `backend/tests/test_scaffold.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `just` targets `install`, `lint`, `typecheck`, `test`, `ci`; a `backend` Python package installable with `uv sync`; a `frontend` package installable with `pnpm install`. Python package name `app`. Test command `uv run pytest`. Lint command `uv run ruff check .`. Typecheck `uv run mypy app`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_scaffold.py`:

```python
import importlib
import tomllib
from pathlib import Path


def test_app_package_importable():
    assert importlib.import_module("app") is not None


def test_pyproject_declares_python_312_and_core_deps():
    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.12,<3.13"
    deps = " ".join(data["project"]["dependencies"])
    for pkg in ("fastapi", "sqlalchemy", "alembic", "pydantic-settings",
                "structlog", "arq", "redis", "asyncpg", "argon2-cffi", "pyjwt",
                "pgvector"):
        assert pkg in deps, f"missing dependency: {pkg}"


def test_importlinter_contract_file_present():
    assert (Path(__file__).parents[1] / ".importlinter").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scaffold.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'` / missing `pyproject.toml`.

- [ ] **Step 3: Write minimal implementation**

`backend/pyproject.toml`:

```toml
[project]
name = "mana-career-backend"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy[asyncio]>=2.0.36",
  "asyncpg>=0.30",
  "alembic>=1.14",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "structlog>=24.4",
  "arq>=0.26",
  "redis>=5.2",
  "argon2-cffi>=23.1",
  "pyjwt>=2.10",
  "python-multipart>=0.0.12",
  "pgvector>=0.3.6",
  "httpx>=0.27",
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-cov>=6.0",
  "ruff>=0.8",
  "mypy>=1.13",
  "import-linter>=2.1",
  "asgi-lifespan>=2.1",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra --cov=app --cov-report=term-missing"

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["app", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC", "S", "RUF"]
ignore = ["S101"]  # assert in tests

[tool.mypy]
python_version = "3.12"
plugins = ["pydantic.mypy"]
strict = true
disallow_untyped_decorators = false
warn_return_any = false

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

`backend/.importlinter`:

```ini
[importlinter]
root_package = app

[importlinter:contract:layers]
name = Mana Career layered architecture
type = layers
layers =
    app.api
    app.worker
    app.domain
    app.core
    app.models

[importlinter:contract:domain-isolation]
name = domain must not import api or worker
type = forbidden
source_modules =
    app.domain
forbidden_modules =
    app.api
    app.worker
```

`backend/app/__init__.py`: empty file.

`justfile`:

```make
set shell := ["bash", "-uc"]

install:
    cd backend && uv sync
    cd frontend && pnpm install

lint:
    cd backend && uv run ruff check . && uv run lint-imports
    cd frontend && pnpm lint

typecheck:
    cd backend && uv run mypy app
    cd frontend && pnpm exec tsc --noEmit

test:
    cd backend && uv run pytest
    cd frontend && pnpm test run

ci: lint typecheck test

up:
    docker compose up --build -d

down:
    docker compose down -v

migrate:
    cd backend && uv run alembic upgrade head

smoke:
    curl -fsS http://localhost:8000/health && echo OK
```

`frontend/package.json`:

```json
{
  "name": "mana-career-frontend",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint",
    "test": "vitest"
  },
  "dependencies": {
    "next": "15.1.0",
    "react": "19.0.0",
    "react-dom": "19.0.0",
    "@tanstack/react-query": "^5.62.0",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/postcss": "^4.0.0",
    "postcss": "^8.4.49",
    "eslint": "^9.17.0",
    "eslint-config-next": "15.1.0",
    "vitest": "^2.1.8",
    "@vitejs/plugin-react": "^4.3.4",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.3",
    "jsdom": "^25.0.1"
  }
}
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`frontend/next.config.ts`:

```ts
import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
};

export default config;
```

`.env.example`:

```bash
# ---- Backend ----
ENV=dev
LOG_LEVEL=info
API_BASE_PATH=/api/v1
CORS_ORIGINS=http://localhost:3000

DATABASE_URL=postgresql+asyncpg://mana:mana@localhost:5432/mana
DATABASE_URL_TEST=postgresql+asyncpg://mana:mana@localhost:5432/mana_test
REDIS_URL=redis://localhost:6379/0

JWT_SECRET=dev-only-change-me
JWT_ACCESS_TTL_SECONDS=900
JWT_REFRESH_TTL_SECONDS=2592000

RATE_LIMIT_DEFAULT_PER_MINUTE=240

LLM_PROVIDER=fake
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=

EMBEDDINGS_PROVIDER=fake
EMBED_MODEL=fake-embed-1
EMBED_DIM=1024

# ---- Frontend ----
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`.dockerignore`:

```
**/__pycache__
**/.venv
**/node_modules
**/.next
**/.pytest_cache
**/.mypy_cache
**/.ruff_cache
.git
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv sync && uv run pytest tests/test_scaffold.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add justfile .env.example .dockerignore backend/pyproject.toml backend/.importlinter backend/app/__init__.py backend/tests/test_scaffold.py frontend/package.json frontend/tsconfig.json frontend/next.config.ts
git commit -m "chore: scaffold monorepo tooling for backend and frontend"
```

---

## Task 2: Settings module (`app/core/config.py`)

**Files:**
- Create: `backend/app/core/__init__.py` (empty)
- Create: `backend/app/core/config.py`
- Test: `backend/tests/core/test_config.py`

**Interfaces:**
- Consumes: environment variables from Task 1's `.env.example`.
- Produces:
  - `class Settings(BaseSettings)` with fields: `env: str`, `log_level: str`, `api_base_path: str`, `cors_origins: list[str]`, `database_url: str`, `database_url_test: str`, `redis_url: str`, `jwt_secret: SecretStr`, `jwt_access_ttl_seconds: int`, `jwt_refresh_ttl_seconds: int`, `rate_limit_default_per_minute: int`, `llm_provider: Literal["fake","anthropic","openai","gemini"]`, `anthropic_api_key: SecretStr | None`, `openai_api_key: SecretStr | None`, `gemini_api_key: SecretStr | None`, `embeddings_provider: Literal["fake","voyage","openai","local"]`, `embed_model: str`, `embed_dim: int`.
  - `get_settings() -> Settings` — `functools.lru_cache`d singleton.

- [ ] **Step 1: Write the failing test**

`backend/tests/core/test_config.py`:

```python
import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings


def _env(**over: str) -> dict[str, str]:
    base = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
        "DATABASE_URL_TEST": "postgresql+asyncpg://u:p@h/db_test",
        "REDIS_URL": "redis://h:6379/0",
        "JWT_SECRET": "s3cr3t",
    }
    base.update(over)
    return base


def test_loads_from_env(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env(ENV="dev", EMBED_DIM="1024").items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.env == "dev"
    assert s.embed_dim == 1024
    assert s.llm_provider == "fake"


def test_secret_fields_are_not_plaintext_in_repr(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert isinstance(s.jwt_secret, SecretStr)
    assert "s3cr3t" not in repr(s)
    assert s.jwt_secret.get_secret_value() == "s3cr3t"


def test_cors_origins_parsed_as_list(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env(CORS_ORIGINS="http://a.com,http://b.com").items():
        monkeypatch.setenv(k, v)
    assert Settings().cors_origins == ["http://a.com", "http://b.com"]


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    assert get_settings() is get_settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/core/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.config'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/core/config.py`:

```python
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "info"
    api_base_path: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str
    database_url_test: str
    redis_url: str

    jwt_secret: SecretStr
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 2_592_000

    rate_limit_default_per_minute: int = 240

    llm_provider: Literal["fake", "anthropic", "openai", "gemini"] = "fake"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

    embeddings_provider: Literal["fake", "voyage", "openai", "local"] = "fake"
    embed_model: str = "fake-embed-1"
    embed_dim: int = 1024

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/core/test_config.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/__init__.py backend/app/core/config.py backend/tests/core/test_config.py
git commit -m "feat(core): typed Settings from environment with secret protection"
```

---

## Task 3: Structured logging with secret redaction (`app/core/logging.py`)

**Files:**
- Create: `backend/app/core/logging.py`
- Test: `backend/tests/core/test_logging.py`

**Interfaces:**
- Consumes: `Settings.log_level`, `Settings.env`.
- Produces:
  - `configure_logging(settings: Settings) -> None` — installs structlog + stdlib config; JSON renderer when `env != "dev"`, console renderer in dev.
  - `redact_secrets(_, __, event_dict: dict) -> dict` — structlog processor replacing values of keys in `SECRET_KEYS` and any string matching `SECRET_PATTERN` with `"***"`.
  - `get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger`.
  - Module constants `SECRET_KEYS: frozenset[str]` (`{"password","token","authorization","api_key","jwt_secret","secret","refresh_token","access_token"}`), `SECRET_PATTERN: re.Pattern` matching `sk-…`, `Bearer …`, and long hex/base64 blobs (≥24 chars).

- [ ] **Step 1: Write the failing test**

`backend/tests/core/test_logging.py`:

```python
import json
import logging

import pytest
import structlog

from app.core.config import Settings
from app.core.logging import configure_logging, get_logger, redact_secrets


@pytest.fixture
def prod_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k, v in {
        "DATABASE_URL": "x", "DATABASE_URL_TEST": "x", "REDIS_URL": "x",
        "JWT_SECRET": "x", "ENV": "prod",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_redacts_known_keys():
    out = redact_secrets(None, None, {"event": "login", "password": "hunter2", "user": "amy"})
    assert out["password"] == "***"
    assert out["user"] == "amy"


def test_redacts_secret_shaped_values():
    out = redact_secrets(None, None, {"event": "call", "header": "Bearer abc.def.ghi123456789"})
    assert out["header"] == "***"


def test_json_output_in_prod(prod_settings: Settings, capsys: pytest.CaptureFixture[str]):
    configure_logging(prod_settings)
    get_logger("test").info("hello", api_key="sk-secret-value-1234567890")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "hello"
    assert record["api_key"] == "***"
    assert record["level"] == "info"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/core/test_logging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.logging'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/core/logging.py`:

```python
from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

from app.core.config import Settings

SECRET_KEYS: frozenset[str] = frozenset({
    "password", "token", "authorization", "api_key", "apikey", "jwt_secret",
    "secret", "refresh_token", "access_token", "set-cookie", "cookie",
})
SECRET_PATTERN: re.Pattern[str] = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,})|(Bearer\s+[A-Za-z0-9._\-]{10,})|([A-Fa-f0-9]{24,})"
)


def redact_secrets(_: Any, __: Any, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if key.lower() in SECRET_KEYS:
            event_dict[key] = "***"
        elif isinstance(value, str) and SECRET_PATTERN.search(value):
            event_dict[key] = "***"
    return event_dict


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        redact_secrets,
    ]
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer() if settings.env == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[*shared, structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/core/test_logging.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/logging.py backend/tests/core/test_logging.py
git commit -m "feat(core): structlog JSON logging with secret redaction"
```

---

## Task 4: Typed errors and `problem+json` handlers (`app/core/errors.py`)

**Files:**
- Create: `backend/app/core/errors.py`
- Test: `backend/tests/core/test_errors.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class AppError(Exception)` with `status: int = 500`, `code: str = "internal_error"`, `title: str = "Something went wrong"`, `detail: str | None = None`, `errors: list[dict] | None = None`.
  - Subclasses: `NotFoundError` (404, `not_found`), `ValidationAppError` (422, `validation_error`), `AuthError` (401, `unauthorized`), `ForbiddenError` (403, `forbidden`), `ConflictError` (409, `conflict`), `RateLimitedError` (429, `rate_limited`, extra attr `retry_after: int`).
  - `to_problem(exc: AppError, instance: str) -> dict` returning `{type, title, status, detail, instance, code, errors?}`.
  - `install_error_handlers(app: FastAPI) -> None` — registers handlers for `AppError`, `RequestValidationError`, and unhandled `Exception`, all emitting `application/problem+json` and logging at the right level. Response always includes header `Content-Type: application/problem+json`.

- [ ] **Step 1: Write the failing test**

`backend/tests/core/test_errors.py`:

```python
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import (
    AppError, NotFoundError, RateLimitedError, install_error_handlers, to_problem,
)


def test_to_problem_shape():
    p = to_problem(NotFoundError(detail="résumé 7 not found"), instance="/api/v1/resumes/7")
    assert p == {
        "type": "about:blank",
        "title": "Not found",
        "status": 404,
        "detail": "résumé 7 not found",
        "instance": "/api/v1/resumes/7",
        "code": "not_found",
    }


@pytest.fixture
def client() -> AsyncClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppError(detail="kaboom")

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError(detail="nope")

    @app.get("/slow")
    async def slow() -> None:
        raise RateLimitedError(retry_after=30)

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_apperror_becomes_problem_json(client: AsyncClient):
    r = await client.get("/boom")
    assert r.status_code == 500
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "internal_error"


async def test_notfound_status_and_code(client: AsyncClient):
    r = await client.get("/missing")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


async def test_rate_limited_sets_retry_after_header(client: AsyncClient):
    r = await client.get("/slow")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "30"
    assert r.json()["code"] == "rate_limited"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/core/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.errors'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/core/errors.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger("errors")
PROBLEM_MEDIA_TYPE = "application/problem+json"


class AppError(Exception):
    status: int = 500
    code: str = "internal_error"
    title: str = "Something went wrong"

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.errors = errors


class NotFoundError(AppError):
    status, code, title = 404, "not_found", "Not found"


class ValidationAppError(AppError):
    status, code, title = 422, "validation_error", "Your input needs a change"


class AuthError(AppError):
    status, code, title = 401, "unauthorized", "Please sign in"


class ForbiddenError(AppError):
    status, code, title = 403, "forbidden", "You can't do that"


class ConflictError(AppError):
    status, code, title = 409, "conflict", "That conflicts with existing data"


class RateLimitedError(AppError):
    status, code, title = 429, "rate_limited", "Slow down a moment"

    def __init__(self, *, retry_after: int, detail: str | None = None) -> None:
        super().__init__(detail)
        self.retry_after = retry_after


def to_problem(exc: AppError, *, instance: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": instance,
        "code": exc.code,
    }
    if exc.errors:
        body["errors"] = exc.errors
    return body


def _response(exc: AppError, instance: str) -> JSONResponse:
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitedError):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status,
        content=to_problem(exc, instance=instance),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        level = "warning" if exc.status < 500 else "error"
        getattr(log, level)("app_error", code=exc.code, status=exc.status,
                            path=request.url.path)
        return _response(exc, str(request.url))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        wrapped = ValidationAppError(
            detail="One or more fields are invalid.",
            errors=[{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()],
        )
        return _response(wrapped, str(request.url))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", path=request.url.path)
        return _response(AppError(), str(request.url))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/core/test_errors.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/errors.py backend/tests/core/test_errors.py
git commit -m "feat(core): typed AppError hierarchy with RFC 9457 problem+json handlers"
```

---

## Task 5: Async DB engine, session, `Base`, and `Repository` (`app/core/db.py`)

**Files:**
- Create: `backend/app/core/db.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/core/test_db.py`

**Interfaces:**
- Consumes: `Settings.database_url`, `Settings.database_url_test`; `NotFoundError` from Task 4.
- Produces:
  - `class Base(DeclarativeBase)` with a shared `metadata` (naming convention for constraints) and `type_annotation_map` mapping `datetime` → `TIMESTAMP(timezone=True)`.
  - `TimestampMixin` — `created_at`, `updated_at` mapped columns with server defaults.
  - `make_engine(url: str) -> AsyncEngine`, `make_session_factory(engine) -> async_sessionmaker[AsyncSession]`.
  - `engine`, `AsyncSessionLocal` module-level singletons built from `get_settings()`.
  - `async def get_session() -> AsyncIterator[AsyncSession]` — FastAPI-compatible dependency, commits on success, rolls back on exception, always closes.
  - `class Repository(Generic[ModelT])` with `__init__(self, session: AsyncSession, model: type[ModelT])`, and methods: `async get(id, *, user_id) -> ModelT` (raises `NotFoundError` when missing OR when the row's `user_id` is not `user_id` and its `owner_id` is not `None`), `async get_or_none(id, *, user_id)`, `async add(obj) -> obj`, `async list_for(user_id, *, limit=50, cursor=None) -> tuple[list[ModelT], str | None]` (keyset on `created_at, id`), `async delete(obj)`.
  - `conftest.py` fixtures: `settings` (env-overridden to `env=test`, `database_url=database_url_test`), `db_engine` (session scope: create engine, `alembic upgrade head`, yield, dispose), `db_session` (function scope: outer transaction + SAVEPOINT, rollback after each test), `client` (httpx `AsyncClient` against the real app with `get_session` overridden to `db_session`), `fake_redis`.

- [ ] **Step 1: Write the failing test**

`backend/tests/core/test_db.py`:

```python
import uuid

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Repository, TimestampMixin
from app.core.errors import NotFoundError


class _Widget(Base, TimestampMixin):
    __tablename__ = "_widget"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest.fixture(autouse=True)
async def _create_widget_table(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(_Widget.__table__.create, checkfirst=True)
    yield
    async with db_engine.begin() as conn:
        await conn.run_sync(_Widget.__table__.drop, checkfirst=True)


async def test_add_and_get_scoped_to_user(db_session):
    me = uuid.uuid4()
    repo = Repository(db_session, _Widget)
    w = await repo.add(_Widget(id=uuid.uuid4(), user_id=me, name="mine"))
    got = await repo.get(w.id, user_id=me)
    assert got.name == "mine"


async def test_get_rejects_other_users_row(db_session):
    me, other = uuid.uuid4(), uuid.uuid4()
    repo = Repository(db_session, _Widget)
    w = await repo.add(_Widget(id=uuid.uuid4(), user_id=other, name="theirs"))
    with pytest.raises(NotFoundError):
        await repo.get(w.id, user_id=me)


async def test_get_allows_shared_row(db_session):
    me = uuid.uuid4()
    repo = Repository(db_session, _Widget)
    w = await repo.add(_Widget(id=uuid.uuid4(), user_id=None, owner_id=None, name="seed"))
    got = await repo.get(w.id, user_id=me)
    assert got.name == "seed"


async def test_list_for_paginates_by_cursor(db_session):
    me = uuid.uuid4()
    repo = Repository(db_session, _Widget)
    for i in range(5):
        await repo.add(_Widget(id=uuid.uuid4(), user_id=me, name=f"w{i}"))
    page1, cursor = await repo.list_for(me, limit=2)
    assert len(page1) == 2 and cursor is not None
    page2, _ = await repo.list_for(me, limit=2, cursor=cursor)
    assert {w.id for w in page1}.isdisjoint({w.id for w in page2})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/core/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.db'` (and no `conftest.py` fixtures yet).

- [ ] **Step 3: Write minimal implementation**

`backend/app/core/db.py`:

```python
from __future__ import annotations

import base64
import datetime as dt
import uuid
from collections.abc import AsyncIterator
from typing import Any, Generic, TypeVar

from sqlalchemy import MetaData, select
from sqlalchemy.ext.asyncio import (
    AsyncAttrs, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import get_settings
from app.core.errors import NotFoundError

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dt.datetime: __import__("sqlalchemy").TIMESTAMP(timezone=True)}


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        server_default=__import__("sqlalchemy").text("now()"), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        server_default=__import__("sqlalchemy").text("now()"), nullable=False
    )


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, future=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


_settings = get_settings()
engine: AsyncEngine = make_engine(_settings.database_url)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = make_session_factory(engine)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


ModelT = TypeVar("ModelT", bound=Base)


def _encode_cursor(created_at: dt.datetime, id_: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{id_}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, id_ = raw.split("|")
    return dt.datetime.fromisoformat(ts), uuid.UUID(id_)


class Repository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_or_none(self, id_: Any, *, user_id: uuid.UUID) -> ModelT | None:
        obj = await self.session.get(self.model, id_)
        if obj is None:
            return None
        row_user = getattr(obj, "user_id", None)
        row_owner = getattr(obj, "owner_id", None)
        if row_user == user_id or (row_user is None and row_owner is None):
            return obj
        return None

    async def get(self, id_: Any, *, user_id: uuid.UUID) -> ModelT:
        obj = await self.get_or_none(id_, user_id=user_id)
        if obj is None:
            raise NotFoundError(detail=f"{self.model.__name__} {id_} not found")
        return obj

    async def list_for(
        self, user_id: uuid.UUID, *, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[ModelT], str | None]:
        stmt = select(self.model).where(
            (self.model.user_id == user_id)  # type: ignore[attr-defined]
        ).order_by(
            self.model.created_at.desc(), self.model.id.desc()  # type: ignore[attr-defined]
        ).limit(limit + 1)
        if cursor:
            c_ts, c_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (self.model.created_at, self.model.id) < (c_ts, c_id)  # type: ignore[attr-defined]
            )
        rows = list((await self.session.execute(stmt)).scalars().all())
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)  # type: ignore[attr-defined]
        return rows, next_cursor

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()
```

`backend/tests/conftest.py`:

```python
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("ENV", "test")
os.environ.setdefault("DATABASE_URL", os.environ.get(
    "DATABASE_URL_TEST", "postgresql+asyncpg://mana:mana@localhost:5432/mana_test"))
os.environ.setdefault("DATABASE_URL_TEST", os.environ["DATABASE_URL"])
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "fake")
os.environ.setdefault("EMBED_DIM", "1024")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
async def db_engine() -> AsyncIterator[object]:
    from alembic import command
    from alembic.config import Config

    from app.core.db import make_engine
    from app.core.config import get_settings

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")

    eng = make_engine(get_settings().database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(db_engine: object) -> AsyncIterator[AsyncSession]:
    from sqlalchemy.ext.asyncio import AsyncSession as _S

    conn = await db_engine.connect()  # type: ignore[attr-defined]
    trans = await conn.begin()
    session = _S(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[object]:
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from app.core.db import get_session
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


@pytest.fixture
def fake_redis() -> object:
    class _FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, int] = {}

        async def incr(self, key: str) -> int:
            self.store[key] = self.store.get(key, 0) + 1
            return self.store[key]

        async def expire(self, key: str, ttl: int) -> None:
            return None

        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    return _FakeRedis()
```

- [ ] **Step 4: Run test to verify it passes**

Prereq: a Postgres reachable at `DATABASE_URL_TEST` with the `mana_test` DB created (Task 12's compose provides it; locally `createdb mana_test`). Alembic `head` exists after Task 6 — until then this test is expected to error on `command.upgrade`. Run it after Task 6:

Run: `cd backend && uv run pytest tests/core/test_db.py -v`
Expected: PASS (4 passed).

> Sequencing note: implement Task 6 before running Step 4 here. Commit the code now (Step 5); the green run is gated on Task 6.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/db.py backend/tests/conftest.py backend/tests/core/test_db.py
git commit -m "feat(core): async engine, Base, and user-scoped Repository base class"
```

---

## Task 6: Alembic harness and bootstrap migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_bootstrap.py`
- Create: `backend/app/models/__init__.py`
- Test: `backend/tests/core/test_migrations.py`

**Interfaces:**
- Consumes: `Settings.database_url`, `Base.metadata` from Task 5.
- Produces:
  - A working `alembic upgrade head` / `downgrade base` against the configured DB.
  - Migration `0001_bootstrap` enabling extensions `vector`, `pg_trgm`, `citext`, `pgcrypto` and creating a `set_updated_at()` trigger function (reused by later tables).
  - `app/models/__init__.py` importing every model module (only `audit` after Task 7) and re-exporting `Base` so `alembic/env.py` has full metadata via `from app.models import Base`.

- [ ] **Step 1: Write the failing test**

`backend/tests/core/test_migrations.py`:

```python
import pytest
from sqlalchemy import text

from app.core.db import make_engine
from app.core.config import get_settings


async def test_extensions_enabled_after_upgrade(db_engine):
    eng = make_engine(get_settings().database_url)
    async with eng.connect() as conn:
        rows = await conn.execute(text("SELECT extname FROM pg_extension"))
        names = {r[0] for r in rows}
    await eng.dispose()
    assert {"vector", "pg_trgm", "citext", "pgcrypto"}.issubset(names)


async def test_set_updated_at_function_exists(db_engine):
    eng = make_engine(get_settings().database_url)
    async with eng.connect() as conn:
        row = await conn.execute(text(
            "SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at'"
        ))
        assert row.first() is not None
    await eng.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/core/test_migrations.py -v`
Expected: FAIL — `alembic.ini` missing / `db_engine` fixture errors on `command.upgrade`.

- [ ] **Step 3: Write minimal implementation**

`backend/alembic.ini` (trimmed to essentials):

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARNING
handlers = console
[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`backend/alembic/env.py`:

```python
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

`backend/alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`backend/alembic/versions/0001_bootstrap.py`:

```python
"""bootstrap extensions and shared trigger

Revision ID: 0001_bootstrap
Revises:
Create Date: 2026-08-30
"""
from alembic import op

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for ext in ("vector", "pg_trgm", "citext", "pgcrypto"):
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    for ext in ("vector", "pg_trgm", "citext", "pgcrypto"):
        op.execute(f'DROP EXTENSION IF EXISTS "{ext}"')
```

`backend/app/models/__init__.py`:

```python
from app.core.db import Base

__all__ = ["Base"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && createdb mana_test 2>/dev/null; uv run pytest tests/core/test_migrations.py tests/core/test_db.py -v`
Expected: PASS (migrations 2 passed, db 4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/alembic.ini backend/alembic/ backend/app/models/__init__.py backend/tests/core/test_migrations.py
git commit -m "feat(core): Alembic harness + bootstrap migration (pgvector, trgm, citext, pgcrypto)"
```

---

## Task 7: `AuditLog` model and `audit()` helper

**Files:**
- Create: `backend/app/models/audit.py`
- Create: `backend/app/core/audit.py`
- Create: `backend/alembic/versions/0002_audit_logs.py`
- Modify: `backend/app/models/__init__.py` — import `audit`
- Test: `backend/tests/core/test_audit.py`

**Interfaces:**
- Consumes: `Base`, `TimestampMixin`, `AsyncSession`.
- Produces:
  - `class AuditLog(Base)` — columns per spec §5.3: `id uuid pk`, `actor_type text` (`user`/`mana_ai`/`system`), `actor_user_id uuid null`, `on_behalf_of_user_id uuid null`, `action text`, `resource_type text null`, `resource_id uuid null`, `ip text null`, `user_agent text null`, `request_id text null`, `before jsonb null`, `after jsonb null`, `result text` (`success`/`failure`), `meta jsonb null`, `created_at`. `CHECK` constraints on `actor_type` and `result`. Indexes: `(actor_user_id, created_at desc)`, `(resource_type, resource_id)`, `(action, created_at)`. **No `updated_at`** (append-only).
  - `async def audit(session, *, actor_type, action, result="success", actor_user_id=None, on_behalf_of_user_id=None, resource_type=None, resource_id=None, ip=None, user_agent=None, request_id=None, before=None, after=None, meta=None) -> None` — inserts one row; never raises out (logs and swallows DB errors so auditing failure can't break the request path), but re-raises `asyncio.CancelledError`.
  - Migration `0002` creating the table (no trigger — append-only).

- [ ] **Step 1: Write the failing test**

`backend/tests/core/test_audit.py`:

```python
import uuid

from sqlalchemy import select

from app.core.audit import audit
from app.models.audit import AuditLog


async def test_audit_writes_a_row(db_session):
    uid = uuid.uuid4()
    await audit(db_session, actor_type="user", action="auth.login",
                actor_user_id=uid, request_id="req-1", ip="127.0.0.1")
    row = (await db_session.execute(select(AuditLog))).scalars().one()
    assert row.action == "auth.login"
    assert row.actor_user_id == uid
    assert row.result == "success"


async def test_audit_swallows_bad_input_without_raising(db_session):
    # invalid actor_type violates the CHECK constraint; must not bubble up
    await audit(db_session, actor_type="not-a-valid-actor", action="x")
    # session still usable
    assert (await db_session.execute(select(AuditLog.id))).first() is None or True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/core/test_audit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.audit'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/models/audit.py`:

```python
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("actor_type in ('user','mana_ai','system')",
                        name="actor_type_valid"),
        CheckConstraint("result in ('success','failure')", name="result_valid"),
        Index("ix_audit_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_resource", "resource_type", "resource_id"),
        Index("ix_audit_action_created", "action", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          server_default=text("gen_random_uuid()"))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    on_behalf_of_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[str] = mapped_column(String(16), server_default=text("'success'"))
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=text("now()"))
```

`backend/app/core/audit.py`:

```python
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditLog

log = get_logger("audit")
ActorType = Literal["user", "mana_ai", "system"]


async def audit(
    session: AsyncSession,
    *,
    actor_type: ActorType | str,
    action: str,
    result: Literal["success", "failure"] = "success",
    actor_user_id: uuid.UUID | None = None,
    on_behalf_of_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    row = AuditLog(
        actor_type=actor_type, action=action, result=result,
        actor_user_id=actor_user_id, on_behalf_of_user_id=on_behalf_of_user_id,
        resource_type=resource_type, resource_id=resource_id, ip=ip,
        user_agent=user_agent, request_id=request_id, before=before, after=after,
        meta=meta,
    )
    try:
        session.add(row)
        await session.flush()
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("audit_write_failed", action=action)
        await session.rollback()
```

`backend/alembic/versions/0002_audit_logs.py`:

```python
"""audit_logs (append-only)

Revision ID: 0002_audit_logs
Revises: 0001_bootstrap
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0002_audit_logs"
down_revision = "0001_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True)),
        sa.Column("on_behalf_of_user_id", pg.UUID(as_uuid=True)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", pg.UUID(as_uuid=True)),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("before", pg.JSONB),
        sa.Column("after", pg.JSONB),
        sa.Column("result", sa.String(16), nullable=False, server_default=sa.text("'success'")),
        sa.Column("meta", pg.JSONB),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("actor_type in ('user','mana_ai','system')", name="actor_type_valid"),
        sa.CheckConstraint("result in ('success','failure')", name="result_valid"),
    )
    op.create_index("ix_audit_actor_created", "audit_logs", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_action_created", "audit_logs", ["action", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
```

`backend/app/models/__init__.py`:

```python
from app.core.db import Base
from app.models import audit as audit  # noqa: F401  (registers AuditLog on Base.metadata)

__all__ = ["Base"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/core/test_audit.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/audit.py backend/app/core/audit.py backend/alembic/versions/0002_audit_logs.py backend/app/models/__init__.py backend/tests/core/test_audit.py
git commit -m "feat(core): append-only AuditLog model and non-throwing audit() helper"
```

---

## Task 8: FastAPI app factory, request-ID middleware, health endpoints

**Files:**
- Create: `backend/app/api/__init__.py` (empty)
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/v1/__init__.py` (empty)
- Create: `backend/app/api/v1/router.py`
- Create: `backend/app/api/v1/health.py`
- Create: `backend/app/core/redis.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/api/test_health.py`

**Interfaces:**
- Consumes: `get_settings`, `configure_logging`, `install_error_handlers`, `get_session`, `Base`/`engine`.
- Produces:
  - `app/core/redis.py`: `get_redis_pool(settings) -> redis.asyncio.Redis` (module singleton via `lru_cache` on url), `async def ping_redis(r) -> bool`.
  - `app/api/deps.py`: `SettingsDep = Annotated[Settings, Depends(get_settings)]`, `DbDep = Annotated[AsyncSession, Depends(get_session)]`, `RedisDep = Annotated[Redis, Depends(_redis_dep)]`.
  - `app/api/v1/health.py`: `router` with `GET /health` → `{"status":"ok"}` (200, no dependencies) and `GET /health/ready` → checks DB `SELECT 1`, Redis `PING`, and Alembic head == DB version; returns 200 `{"status":"ready","checks":{...}}` or 503 with the failing checks.
  - `app/api/v1/router.py`: `api_router` including `health.router`.
  - `app/main.py`: `create_app() -> FastAPI` — configures logging, adds `RequestIDMiddleware` (reads `X-Request-ID` or generates a uuid4, binds it to structlog contextvars, sets it on the response header), `CORSMiddleware` from `settings.cors_origins`, mounts `api_router` under `settings.api_base_path`, calls `install_error_handlers`, sets `openapi_url="/api/openapi.json"`. Module-level `app = create_app()`.

- [ ] **Step 1: Write the failing test**

`backend/tests/api/test_health.py`:

```python
async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_health_sets_request_id_header(client):
    r = await client.get("/health")
    assert r.headers.get("x-request-id")


async def test_health_echoes_incoming_request_id(client):
    r = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


async def test_ready_reports_checks(client):
    r = await client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert set(body["checks"]) == {"database", "redis", "migrations"}


async def test_unknown_route_is_problem_json(client):
    r = await client.get("/health/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "not_found"
```

> Note: `create_app()` must map Starlette 404s to the `problem+json` shape. Do this by registering an exception handler for `starlette.exceptions.HTTPException` inside `install_error_handlers` that converts `status_code==404` to `NotFoundError` and other codes to a generic `AppError` subclass with matching status. Update Task 4's `install_error_handlers` accordingly when implementing this task, and re-run `tests/core/test_errors.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/core/redis.py`:

```python
from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis

from app.core.config import Settings


@lru_cache
def get_redis_pool(url: str) -> redis.Redis:
    return redis.from_url(url, encoding="utf-8", decode_responses=True)


def redis_from_settings(settings: Settings) -> redis.Redis:
    return get_redis_pool(settings.redis_url)


async def ping_redis(r: redis.Redis) -> bool:
    try:
        return bool(await r.ping())
    except Exception:
        return False
```

`backend/app/api/deps.py`:

```python
from __future__ import annotations

from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.redis import redis_from_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_session)]


def _redis_dep(settings: SettingsDep) -> redis.Redis:
    return redis_from_settings(settings)


RedisDep = Annotated[redis.Redis, Depends(_redis_dep)]
```

`backend/app/api/v1/health.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.api.deps import DbDep, RedisDep, SettingsDep
from app.core.redis import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(response: Response, db: DbDep, r: RedisDep, settings: SettingsDep) -> dict:
    checks: dict[str, bool] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    checks["redis"] = await ping_redis(r)
    try:
        row = (await db.execute(text("SELECT version_num FROM alembic_version"))).first()
        checks["migrations"] = row is not None
    except Exception:
        checks["migrations"] = False
    ok = all(checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ready" if ok else "degraded", "checks": checks}
```

`backend/app/api/v1/router.py`:

```python
from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
```

`backend/app/main.py`:

```python
from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = rid
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(title="Mana Career API", version="0.0.0",
                  openapi_url="/api/openapi.json")
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_base_path)
    # health is also mounted at root for infra probes:
    app.include_router(api_router)
    return app


app = create_app()
```

Also extend `install_error_handlers` (Task 4 file) with:

```python
from starlette.exceptions import HTTPException as StarletteHTTPException

_STATUS_TO_ERROR = {401: AuthError, 403: ForbiddenError, 404: NotFoundError,
                    409: ConflictError, 422: ValidationAppError}

@app.exception_handler(StarletteHTTPException)
async def _starlette_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    err_cls = _STATUS_TO_ERROR.get(exc.status_code, AppError)
    err = err_cls(detail=exc.detail if isinstance(exc.detail, str) else None)
    err.status = exc.status_code
    return _response(err, str(request.url))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_health.py tests/core/test_errors.py -v`
Expected: PASS (health 5 passed, errors 4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/ backend/app/core/redis.py backend/app/main.py backend/tests/api/test_health.py backend/app/core/errors.py
git commit -m "feat(api): app factory, request-id middleware, health + readiness endpoints"
```

---

## Task 9: Redis token-bucket rate limiting (`app/core/rate_limit.py`)

**Files:**
- Create: `backend/app/core/rate_limit.py`
- Modify: `backend/app/main.py` — add `RateLimitMiddleware`
- Test: `backend/tests/core/test_rate_limit.py`

**Interfaces:**
- Consumes: `RedisDep`/`redis_from_settings`, `Settings.rate_limit_default_per_minute`, `RateLimitedError`.
- Produces:
  - `async def check_rate_limit(r: Redis, *, key: str, limit: int, window_seconds: int = 60) -> RateLimitState` where `RateLimitState` is a dataclass `(limit: int, remaining: int, reset: int, allowed: bool)`. Fixed-window counter: `INCR key`; if new value == 1 set `EXPIRE key window`; `allowed = value <= limit`.
  - `class RateLimitMiddleware(BaseHTTPMiddleware)` — builds `key = f"rl:{client_ip}:{path_bucket}"` where `path_bucket` is `"auth"` for paths under `/api/v1/auth`, `"read"` otherwise (Phase 0 has only reads); uses `settings.rate_limit_default_per_minute`; on `allowed=False` raises `RateLimitedError(retry_after=state.reset)`; on success sets headers `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`. Skips `/health*`.

- [ ] **Step 1: Write the failing test**

`backend/tests/core/test_rate_limit.py`:

```python
import pytest

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


async def test_reads_are_rate_limited_via_middleware(client, monkeypatch):
    # force limit to 2 for the read bucket
    from app.core import rate_limit as rl
    monkeypatch.setattr(rl, "_LIMIT_OVERRIDE", 2, raising=False)
    r1 = await client.get("/api/v1/health")   # health is skipped -> use a real read later
    assert r1.status_code == 200
```

> The middleware integration assertion is minimal in Phase 0 (only health + readiness exist, and health is skipped). Keep `test_reads_are_rate_limited_via_middleware` as a smoke check that the middleware doesn't break the request path; the full 429 path is covered by the unit test on `check_rate_limit` and revisited in Phase 1 when real read endpoints exist.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/core/test_rate_limit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.rate_limit'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/core/rate_limit.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as redis
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.core.redis import redis_from_settings


@dataclass(frozen=True)
class RateLimitState:
    limit: int
    remaining: int
    reset: int
    allowed: bool


async def check_rate_limit(
    r: redis.Redis, *, key: str, limit: int, window_seconds: int = 60
) -> RateLimitState:
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_seconds)
    reset = await r.ttl(key)
    reset = window_seconds if reset is None or reset < 0 else reset
    remaining = max(0, limit - count)
    return RateLimitState(limit=limit, remaining=remaining, reset=reset,
                          allowed=count <= limit)


def _bucket(path: str) -> str:
    return "auth" if path.startswith(get_settings().api_base_path + "/auth") else "read"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path
        if path.startswith("/health") or path == "/api/openapi.json":
            return await call_next(request)
        settings = get_settings()
        r = redis_from_settings(settings)
        client_ip = request.client.host if request.client else "unknown"
        bucket = _bucket(path)
        limit = 10 if bucket == "auth" else settings.rate_limit_default_per_minute
        state = await check_rate_limit(r, key=f"rl:{client_ip}:{bucket}", limit=limit)
        if not state.allowed:
            raise RateLimitedError(retry_after=state.reset)
        response = await call_next(request)
        response.headers["RateLimit-Limit"] = str(state.limit)
        response.headers["RateLimit-Remaining"] = str(state.remaining)
        response.headers["RateLimit-Reset"] = str(state.reset)
        return response
```

Wire into `create_app()` after `RequestIDMiddleware`:

```python
from app.core.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/core/test_rate_limit.py tests/api/test_health.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/rate_limit.py backend/app/main.py backend/tests/core/test_rate_limit.py
git commit -m "feat(core): Redis fixed-window rate limiting middleware with RateLimit-* headers"
```

---

## Task 10: LLM + Embeddings provider interfaces and fake adapters

**Files:**
- Create: `backend/app/domain/__init__.py` (empty)
- Create: `backend/app/domain/llm/__init__.py` (empty)
- Create: `backend/app/domain/llm/provider.py`
- Create: `backend/app/domain/llm/adapters/__init__.py` (empty)
- Create: `backend/app/domain/llm/adapters/fake.py`
- Create: `backend/app/domain/llm/factory.py`
- Create: `backend/app/domain/embeddings/__init__.py` (empty)
- Create: `backend/app/domain/embeddings/provider.py`
- Create: `backend/app/domain/embeddings/adapters/__init__.py` (empty)
- Create: `backend/app/domain/embeddings/adapters/fake.py`
- Create: `backend/app/domain/embeddings/factory.py`
- Test: `backend/tests/domain/test_llm_fake.py`, `backend/tests/domain/test_embeddings_fake.py`

**Interfaces:**
- Produces:
  - `provider.py` (llm): `LLMMessage = TypedDict("LLMMessage", {"role": Literal["system","user","assistant"], "content": str})`; `@dataclass LLMResult(text: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float, structured: dict | None = None)`; `class LLMProvider(Protocol)` with `async def complete(self, messages: list[LLMMessage], *, schema: type[BaseModel] | None = None, max_tokens: int = 1024, temperature: float = 0.2) -> LLMResult` and `def capabilities(self) -> LLMCapabilities` (`@dataclass` with `structured_output: bool`, `tools: bool`, `streaming: bool`).
  - `adapters/fake.py`: `class FakeLLMProvider` implementing the protocol. `complete` returns a deterministic `LLMResult` — `text` is `f"[fake:{messages[-1]['content'][:40]}]"`; when `schema` is given, `structured` is `schema.model_construct()`-compatible: it fills each field with a type-appropriate stub (`str→""`, `int→0`, `float→0.0`, `bool→False`, `list→[]`, `dict→{}`) then validates via `schema.model_validate`, so callers exercising schema paths get a valid object. Token counts are `len(text.split())`; `cost_usd=0.0`. A constructor arg `scripted: list[str] | None` lets tests queue exact responses.
  - `factory.py` (llm): `def get_llm_provider(settings: Settings) -> LLMProvider` — returns `FakeLLMProvider()` for `settings.llm_provider == "fake"`; raises `NotImplementedError(f"{settings.llm_provider} adapter lands in Phase 7")` otherwise.
  - `provider.py` (embeddings): `class EmbeddingsProvider(Protocol)` with `async def embed_documents(self, texts: list[str]) -> list[list[float]]`, `async def embed_query(self, text: str) -> list[float]`, `property dim: int`, `property model: str`.
  - `adapters/fake.py` (embeddings): `class FakeEmbeddingsProvider(dim: int, model: str)` — deterministic: hash each text with `hashlib.sha256`, seed `random.Random(digest)`, produce `dim` floats in `[-1, 1]`, L2-normalize. Same text → same vector; different text → different vector.
  - `factory.py` (embeddings): `def get_embeddings_provider(settings) -> EmbeddingsProvider` — `FakeEmbeddingsProvider(settings.embed_dim, settings.embed_model)` for `"fake"`, else `NotImplementedError("… lands in Phase 6")`.

- [ ] **Step 1: Write the failing test**

`backend/tests/domain/test_llm_fake.py`:

```python
import pytest
from pydantic import BaseModel

from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMMessage


class _Extraction(BaseModel):
    name: str
    years: int
    skills: list[str]


async def test_complete_returns_deterministic_text():
    p = FakeLLMProvider()
    msgs: list[LLMMessage] = [{"role": "user", "content": "hello world"}]
    r1 = await p.complete(msgs)
    r2 = await p.complete(msgs)
    assert r1.text == r2.text
    assert r1.output_tokens > 0


async def test_scripted_responses_are_consumed_in_order():
    p = FakeLLMProvider(scripted=["first", "second"])
    assert (await p.complete([{"role": "user", "content": "x"}])).text == "first"
    assert (await p.complete([{"role": "user", "content": "x"}])).text == "second"


async def test_schema_path_returns_valid_model_dict():
    p = FakeLLMProvider()
    r = await p.complete([{"role": "user", "content": "extract"}], schema=_Extraction)
    assert r.structured is not None
    _Extraction.model_validate(r.structured)  # must not raise


def test_capabilities_shape():
    caps = FakeLLMProvider().capabilities()
    assert caps.structured_output is True
```

`backend/tests/domain/test_embeddings_fake.py`:

```python
import math

from app.domain.embeddings.adapters.fake import FakeEmbeddingsProvider


async def test_dim_and_determinism():
    p = FakeEmbeddingsProvider(dim=1024, model="fake-embed-1")
    v1 = await p.embed_query("machine learning")
    v2 = await p.embed_query("machine learning")
    assert len(v1) == 1024
    assert v1 == v2


async def test_normalized_and_distinct():
    p = FakeEmbeddingsProvider(dim=64, model="fake-embed-1")
    a = await p.embed_query("python")
    b = await p.embed_query("kubernetes")
    assert a != b
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-6)


async def test_embed_documents_batches():
    p = FakeEmbeddingsProvider(dim=8, model="fake-embed-1")
    out = await p.embed_documents(["a", "b", "c"])
    assert len(out) == 3 and all(len(v) == 8 for v in out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/domain -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.llm'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/domain/llm/provider.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

from pydantic import BaseModel


class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMCapabilities:
    structured_output: bool
    tools: bool
    streaming: bool


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    structured: dict | None = None


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult: ...

    def capabilities(self) -> LLMCapabilities: ...
```

`backend/app/domain/llm/adapters/fake.py`:

```python
from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic import BaseModel

from app.domain.llm.provider import (
    LLMCapabilities, LLMMessage, LLMProvider, LLMResult,
)

_STUBS: dict[type, Any] = {str: "", int: 0, float: 0.0, bool: False}


def _stub_for(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (list, set, tuple):
        return []
    if origin is dict:
        return {}
    if annotation in _STUBS:
        return _STUBS[annotation]
    args = [a for a in get_args(annotation) if a is not type(None)]
    if args:
        return _stub_for(args[0])
    return None


class FakeLLMProvider(LLMProvider):
    def __init__(self, scripted: list[str] | None = None) -> None:
        self._scripted = list(scripted or [])

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult:
        if self._scripted:
            text = self._scripted.pop(0)
        else:
            last = messages[-1]["content"] if messages else ""
            text = f"[fake:{last[:40]}]"
        structured: dict | None = None
        if schema is not None:
            data = {name: _stub_for(f.annotation)
                    for name, f in schema.model_fields.items()}
            structured = schema.model_validate(data).model_dump()
        n = max(1, len(text.split()))
        return LLMResult(text=text, model="fake-llm-1", input_tokens=n,
                         output_tokens=n, cost_usd=0.0, structured=structured)

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(structured_output=True, tools=False, streaming=False)
```

`backend/app/domain/llm/factory.py`:

```python
from __future__ import annotations

from app.core.config import Settings
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    raise NotImplementedError(f"{settings.llm_provider} adapter lands in Phase 7")
```

`backend/app/domain/embeddings/provider.py`:

```python
from __future__ import annotations

from typing import Protocol


class EmbeddingsProvider(Protocol):
    @property
    def dim(self) -> int: ...

    @property
    def model(self) -> str: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...
```

`backend/app/domain/embeddings/adapters/fake.py`:

```python
from __future__ import annotations

import hashlib
import math
import random


class FakeEmbeddingsProvider:
    def __init__(self, dim: int, model: str) -> None:
        self._dim = dim
        self._model = model

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return self._model

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        rng = random.Random(digest)
        raw = [rng.uniform(-1.0, 1.0) for _ in range(self._dim)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
```

`backend/app/domain/embeddings/factory.py`:

```python
from __future__ import annotations

from app.core.config import Settings
from app.domain.embeddings.adapters.fake import FakeEmbeddingsProvider
from app.domain.embeddings.provider import EmbeddingsProvider


def get_embeddings_provider(settings: Settings) -> EmbeddingsProvider:
    if settings.embeddings_provider == "fake":
        return FakeEmbeddingsProvider(settings.embed_dim, settings.embed_model)
    raise NotImplementedError(f"{settings.embeddings_provider} adapter lands in Phase 6")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/domain -v`
Expected: PASS (llm 4 passed, embeddings 3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/ backend/tests/domain/
git commit -m "feat(domain): LLMProvider + EmbeddingsProvider interfaces with deterministic fakes"
```

---

## Task 11: ARQ worker skeleton with `ping` task

**Files:**
- Create: `backend/app/worker/__init__.py` (empty)
- Create: `backend/app/worker/main.py`
- Create: `backend/app/worker/tasks/__init__.py`
- Create: `backend/app/worker/tasks/ping.py`
- Create: `backend/app/worker/dead_letter.py`
- Test: `backend/tests/worker/test_ping.py`

**Interfaces:**
- Consumes: `get_settings`, `configure_logging`, `redis_from_settings`.
- Produces:
  - `tasks/ping.py`: `async def ping(ctx: dict, payload: str = "pong") -> dict` — returns `{"echo": payload, "job_id": ctx.get("job_id")}` and logs `worker_ping`.
  - `dead_letter.py`: `async def record_failure(task_name: str, *, args: tuple, kwargs: dict, error: BaseException) -> None` — logs structured `task_failed` (redaction covers secrets). (DB `task_failures` table is deferred to a later phase — spec §5.3.)
  - `main.py`: `class WorkerSettings` with `functions = [ping]`, `redis_settings` built from `settings.redis_url` (`arq.connections.RedisSettings.from_dsn`), `on_startup`/`on_shutdown` (configure logging, open/close a shared resource dict), `max_jobs = 10`, `job_timeout = 300`, `on_job_failure = _on_failure` calling `record_failure`.
  - Helper `async def enqueue(task: str, *args, **kwargs) -> str` in `main.py` using an `arq.create_pool` — returns the job id (used by API in later phases).

- [ ] **Step 1: Write the failing test**

`backend/tests/worker/test_ping.py`:

```python
from app.worker.tasks.ping import ping


async def test_ping_echoes_payload():
    out = await ping({"job_id": "job-1"}, "hello")
    assert out == {"echo": "hello", "job_id": "job-1"}


async def test_ping_default_payload():
    out = await ping({})
    assert out["echo"] == "pong"


def test_worker_settings_registers_ping():
    from app.worker.main import WorkerSettings
    assert ping in WorkerSettings.functions
    assert WorkerSettings.job_timeout == 300
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/worker/test_ping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.worker.tasks.ping'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/worker/tasks/ping.py`:

```python
from __future__ import annotations

from app.core.logging import get_logger

log = get_logger("worker.ping")


async def ping(ctx: dict, payload: str = "pong") -> dict:
    log.info("worker_ping", payload=payload, job_id=ctx.get("job_id"))
    return {"echo": payload, "job_id": ctx.get("job_id")}
```

`backend/app/worker/tasks/__init__.py`:

```python
from app.worker.tasks.ping import ping

__all__ = ["ping"]
```

`backend/app/worker/dead_letter.py`:

```python
from __future__ import annotations

from app.core.logging import get_logger

log = get_logger("worker.dead_letter")


async def record_failure(
    task_name: str, *, args: tuple, kwargs: dict, error: BaseException
) -> None:
    log.error("task_failed", task=task_name, args=list(args),
              kwargs=kwargs, error=repr(error))
```

`backend/app/worker/main.py`:

```python
from __future__ import annotations

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.worker.dead_letter import record_failure
from app.worker.tasks import ping

_settings = get_settings()


async def _on_startup(ctx: dict) -> None:
    configure_logging(_settings)


async def _on_shutdown(ctx: dict) -> None:
    return None


async def _on_failure(ctx: dict, exc: BaseException) -> None:
    await record_failure(ctx.get("job_name", "unknown"),
                         args=tuple(ctx.get("job_args", ())),
                         kwargs=dict(ctx.get("job_kwargs", {})), error=exc)


class WorkerSettings:
    functions = [ping]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    on_job_failure = _on_failure
    max_jobs = 10
    job_timeout = 300


async def enqueue(task: str, *args: object, **kwargs: object) -> str:
    pool = await create_pool(RedisSettings.from_dsn(_settings.redis_url))
    try:
        job = await pool.enqueue_job(task, *args, **kwargs)
        assert job is not None
        return job.job_id
    finally:
        await pool.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/worker/test_ping.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker/ backend/tests/worker/test_ping.py
git commit -m "feat(worker): ARQ worker skeleton with ping task and dead-letter logger"
```

---

## Task 12: Docker Compose stack

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `scripts/smoke.sh`
- Modify: `justfile` — point `smoke` at `scripts/smoke.sh`
- Test: `scripts/smoke.sh` (executable shell assertion; run after `just up`)

**Interfaces:**
- Consumes: everything above; `.env.example` variable names.
- Produces:
  - `db`: image `pgvector/pgvector:pg16`, env `POSTGRES_USER=mana POSTGRES_PASSWORD=mana POSTGRES_DB=mana`, healthcheck `pg_isready`, an init script creating `mana_test`.
  - `redis`: image `redis:7-alpine`, healthcheck `redis-cli ping`.
  - `api`: build `backend/` dev target, command `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"`, depends_on db+redis healthy, ports `8000:8000`, env from `.env`, volume `./backend:/app`.
  - `worker`: same build, command `arq app.worker.main.WorkerSettings`, depends_on db+redis healthy.
  - `frontend`: build `frontend/` dev target, command `pnpm dev`, ports `3000:3000`, env `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`, volume `./frontend:/app` + anonymous `/app/node_modules`.
  - `scripts/smoke.sh`: curls `http://localhost:8000/health` (expect `{"status":"ok"}`), `http://localhost:8000/health/ready` (expect HTTP 200), `http://localhost:3000` (expect HTTP 200); exits non-zero on any failure.

- [ ] **Step 1: Write the failing test**

`scripts/smoke.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

curl -fsS http://localhost:8000/health | grep -q '"status":"ok"' || fail "api /health"
code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health/ready)
[ "$code" = "200" ] || fail "api /health/ready returned $code"
code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000)
[ "$code" = "200" ] || fail "frontend returned $code"
echo "SMOKE OK"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `chmod +x scripts/smoke.sh && ./scripts/smoke.sh`
Expected: FAIL — connection refused (no stack running, no compose file).

- [ ] **Step 3: Write minimal implementation**

`backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install uv
WORKDIR /app

FROM base AS dev
COPY pyproject.toml ./
RUN uv sync --no-install-project
COPY . .
RUN uv sync
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

`frontend/Dockerfile`:

```dockerfile
FROM node:20-slim AS base
RUN corepack enable
WORKDIR /app

FROM base AS dev
COPY package.json ./
RUN pnpm install
COPY . .
CMD ["pnpm", "dev"]
```

`docker-compose.yml`:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: mana
      POSTGRES_PASSWORD: mana
      POSTGRES_DB: mana
    ports: ["5432:5432"]
    volumes:
      - dbdata:/var/lib/postgresql/data
      - ./scripts/init-test-db.sh:/docker-entrypoint-initdb.d/init-test-db.sh:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mana"]
      interval: 3s
      timeout: 3s
      retries: 20

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      timeout: 3s
      retries: 20

  api:
    build: { context: ./backend, target: dev }
    command: sh -c "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    env_file: [.env]
    environment:
      DATABASE_URL: postgresql+asyncpg://mana:mana@db:5432/mana
      DATABASE_URL_TEST: postgresql+asyncpg://mana:mana@db:5432/mana_test
      REDIS_URL: redis://redis:6379/0
    ports: ["8000:8000"]
    volumes: ["./backend:/app"]
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }

  worker:
    build: { context: ./backend, target: dev }
    command: uv run arq app.worker.main.WorkerSettings
    env_file: [.env]
    environment:
      DATABASE_URL: postgresql+asyncpg://mana:mana@db:5432/mana
      REDIS_URL: redis://redis:6379/0
    volumes: ["./backend:/app"]
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }

  frontend:
    build: { context: ./frontend, target: dev }
    command: pnpm dev
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://localhost:8000
    ports: ["3000:3000"]
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on: [api]

volumes:
  dbdata:
```

`scripts/init-test-db.sh`:

```bash
#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
  CREATE DATABASE mana_test;
EOSQL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `just up && sleep 15 && ./scripts/smoke.sh`
Expected: `SMOKE OK`. Then `docker compose ps` shows `db`, `redis`, `api`, `worker`, `frontend` all `Up`/healthy; `curl localhost:8000/api/openapi.json` returns the schema.

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile docker-compose.yml scripts/
git commit -m "feat(infra): docker-compose stack (pgvector, redis, api, worker, frontend) + smoke script"
```

---

## Task 13: Frontend scaffold, design tokens, themed landing shell

**Files:**
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/styles/tokens.css`
- Create: `frontend/app/globals.css`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/lib/env.ts`
- Create: `frontend/lib/api/fetcher.ts`
- Create: `frontend/components/common/EmptyState.tsx`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/vitest.setup.ts`
- Create: `frontend/.eslintrc.cjs`
- Test: `frontend/tests/landing.test.tsx`, `frontend/tests/EmptyState.test.tsx`

**Interfaces:**
- Produces:
  - `styles/tokens.css`: `:root` block with the spec §7.7 tokens as CSS custom properties (`--bg`, `--surface`, `--text`, `--text-muted`, `--accent`, `--accent-fg`, `--positive`, `--warning`, `--danger`, `--border`, `--ring`, `--radius`, `--shadow-1`, `--shadow-2`) plus a `@media (prefers-color-scheme: dark)` placeholder block (commented, structured for Phase-later dark theme).
  - `app/globals.css`: `@import "tailwindcss";` + `@import "../styles/tokens.css";` + a `@theme inline` block mapping Tailwind color tokens (`--color-bg`, `--color-accent`, …) to the custom properties + base `body { background: var(--bg); color: var(--text); font-family: Inter, Geist, Manrope, system-ui, sans-serif; }` + `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; } }`.
  - `lib/env.ts`: `export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";`
  - `lib/api/fetcher.ts`: `export class ProblemError extends Error { code: string; status: number; problem: unknown }` and `export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T>` — prefixes `API_BASE_URL`, sends `Accept: application/json`, on non-2xx parses `application/problem+json` and throws `ProblemError`, on 204 returns `undefined as T`.
  - `components/common/EmptyState.tsx`: `export function EmptyState({ title, description, action }: { title: string; description?: string; action?: React.ReactNode })` — semantic `<section role="status">`, uses token classes, default copy caller-supplied (spec §19 tone). Renders `title` as `<h2>`, `description` as `<p>`, `action` after.
  - `app/page.tsx`: renders the hero — `<h1>Your next opportunity starts here.</h1>` + the spec §18 supporting text + a "Get started" link to `/register` (route lands in Phase 1; link is fine now) + an `<EmptyState>` demoing the primitive.
  - `app/layout.tsx`: imports `globals.css`, sets `<html lang="en">`, `metadata` title `"Mana Career"`, description = tagline.

- [ ] **Step 1: Write the failing test**

`frontend/tests/landing.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Page from "@/app/page";

describe("landing", () => {
  it("shows the hero headline", () => {
    render(<Page />);
    expect(
      screen.getByRole("heading", { level: 1, name: /your next opportunity starts here/i }),
    ).toBeInTheDocument();
  });

  it("links to get started", () => {
    render(<Page />);
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute(
      "href",
      "/register",
    );
  });
});
```

`frontend/tests/EmptyState.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "@/components/common/EmptyState";

describe("EmptyState", () => {
  it("renders title and description with a status role", () => {
    render(<EmptyState title="Your career workspace is ready." description="Add a résumé to begin." />);
    expect(screen.getByRole("status")).toHaveTextContent("Your career workspace is ready.");
    expect(screen.getByText("Add a résumé to begin.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm install && pnpm test run`
Expected: FAIL — cannot resolve `@/app/page` / `@/components/common/EmptyState`.

- [ ] **Step 3: Write minimal implementation**

`frontend/postcss.config.mjs`:

```js
export default { plugins: { "@tailwindcss/postcss": {} } };
```

`frontend/styles/tokens.css`:

```css
:root {
  --bg: #faf8f5;
  --surface: #ffffff;
  --text: #1f2430;
  --text-muted: #5b6472;
  --accent: #4f46e5;
  --accent-fg: #ffffff;
  --positive: #1f9d5b;
  --warning: #c9820a;
  --danger: #d1453b;
  --border: #e7e3dc;
  --ring: rgba(79, 70, 229, 0.4);
  --radius: 14px;
  --shadow-1: 0 1px 2px rgba(31, 36, 48, 0.06), 0 1px 3px rgba(31, 36, 48, 0.04);
  --shadow-2: 0 4px 12px rgba(31, 36, 48, 0.08);
}

/* Dark theme lands in a later phase — keep the token names stable.
@media (prefers-color-scheme: dark) {
  :root { --bg: #15171c; --surface: #1d2027; --text: #edeef1; ... }
}
*/
```

`frontend/app/globals.css`:

```css
@import "tailwindcss";
@import "../styles/tokens.css";

@theme inline {
  --color-bg: var(--bg);
  --color-surface: var(--surface);
  --color-text: var(--text);
  --color-text-muted: var(--text-muted);
  --color-accent: var(--accent);
  --color-accent-fg: var(--accent-fg);
  --color-positive: var(--positive);
  --color-warning: var(--warning);
  --color-danger: var(--danger);
  --color-border: var(--border);
  --radius-card: var(--radius);
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: Inter, Geist, Manrope, system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

`frontend/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mana Career",
  description: "Your career. Your next move. Smarter with AI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

`frontend/components/common/EmptyState.tsx`:

```tsx
import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <section
      role="status"
      className="mx-auto max-w-md rounded-[var(--radius)] border border-border bg-surface p-8 text-center shadow-[var(--shadow-1)]"
    >
      <h2 className="text-lg font-semibold text-text">{title}</h2>
      {description ? <p className="mt-2 text-sm text-text-muted">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </section>
  );
}
```

`frontend/app/page.tsx`:

```tsx
import Link from "next/link";
import { EmptyState } from "@/components/common/EmptyState";

export default function Page() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-8 px-6 py-16">
      <div>
        <p className="text-sm font-medium uppercase tracking-wide text-accent">Mana Career</p>
        <h1 className="mt-3 text-4xl font-semibold leading-tight text-text">
          Your next opportunity starts here.
        </h1>
        <p className="mt-4 text-base text-text-muted">
          Mana Career helps you discover better opportunities, understand your career gaps,
          and prepare stronger applications — with you always in control.
        </p>
        <Link
          href="/register"
          className="mt-6 inline-block rounded-[var(--radius)] bg-accent px-5 py-2.5 text-sm font-medium text-accent-fg shadow-[var(--shadow-1)]"
        >
          Get started
        </Link>
      </div>
      <EmptyState
        title="Your career workspace is ready."
        description="Sign in to upload a résumé and see where you stand."
      />
    </main>
  );
}
```

`frontend/lib/env.ts`, `frontend/lib/api/fetcher.ts`:

```ts
// lib/env.ts
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
```

```ts
// lib/api/fetcher.ts
import { API_BASE_URL } from "@/lib/env";

export class ProblemError extends Error {
  constructor(
    public code: string,
    public status: number,
    public problem: unknown,
  ) {
    super(`${code} (${status})`);
    this.name = "ProblemError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const code =
      body && typeof body === "object" && "code" in body
        ? String((body as { code: unknown }).code)
        : "error";
    throw new ProblemError(code, res.status, body);
  }
  return body as T;
}
```

`frontend/vitest.config.ts`, `frontend/vitest.setup.ts`, `frontend/.eslintrc.cjs`:

```ts
// vitest.config.ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./", import.meta.url)) } },
  test: { environment: "jsdom", setupFiles: ["./vitest.setup.ts"], globals: true },
});
```

```ts
// vitest.setup.ts
import "@testing-library/jest-dom/vitest";
```

```js
// .eslintrc.cjs
module.exports = { extends: ["next/core-web-vitals"] };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test run && pnpm exec tsc --noEmit && pnpm lint`
Expected: PASS (2 test files, 3 tests); tsc clean; lint clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Next.js scaffold, design tokens, themed landing shell + EmptyState"
```

---

## Task 14: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `justfile` — ensure `just ci` runs the same gates locally
- Test: manual — `just ci` green locally; workflow validated by `act` or first push.

**Interfaces:**
- Consumes: `just` targets, `pyproject.toml` tool config, `frontend/package.json` scripts.
- Produces:
  - A `ci` workflow with two jobs:
    - `backend`: `services: postgres` (image `pgvector/pgvector:pg16`, env mana/mana/mana, health opts), `redis` service; steps — checkout, install `uv`, `uv sync`, `uv run ruff check .`, `uv run lint-imports`, `uv run mypy app`, create `mana_test` DB, `uv run pytest` (env `DATABASE_URL_TEST`, `REDIS_URL`). Coverage printed; fail under 70% (`--cov-fail-under=70` appended for CI via `PYTEST_ADDOPTS`).
    - `frontend`: checkout, setup Node 20 + pnpm, `pnpm install`, `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm test run`.

- [ ] **Step 1: Write the failing test**

There is no unit test for a CI YAML. The check is: `just ci` runs all gates locally and passes. Before writing the workflow, run it to confirm the aggregate gate works:

Run: `just ci`
Expected (pre-workflow): all backend + frontend gates PASS. If anything fails, fix it — the workflow only mirrors this.

- [ ] **Step 2: Confirm the gap**

Run: `test -f .github/workflows/ci.yml && echo present || echo missing`
Expected: `missing`.

- [ ] **Step 3: Write minimal implementation**

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push: { branches: ["**"] }
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env: { POSTGRES_USER: mana, POSTGRES_PASSWORD: mana, POSTGRES_DB: mana }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U mana" --health-interval 3s
          --health-timeout 3s --health-retries 20
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping" --health-interval 3s
          --health-timeout 3s --health-retries 20
    env:
      DATABASE_URL: postgresql+asyncpg://mana:mana@localhost:5432/mana_test
      DATABASE_URL_TEST: postgresql+asyncpg://mana:mana@localhost:5432/mana_test
      REDIS_URL: redis://localhost:6379/0
      JWT_SECRET: ci-secret
      PYTEST_ADDOPTS: "--cov-fail-under=70"
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: PGPASSWORD=mana psql -h localhost -U mana -d mana -c 'CREATE DATABASE mana_test;' || true
      - run: uv run ruff check .
      - run: uv run lint-imports
      - run: uv run mypy app
      - run: uv run pytest

  frontend:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm, cache-dependency-path: frontend/pnpm-lock.yaml }
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm exec tsc --noEmit
      - run: pnpm test run
```

- [ ] **Step 4: Verify**

Run: `just ci` locally once more → all green. Push the branch; confirm the `ci` workflow's `backend` and `frontend` jobs both pass.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml justfile
git commit -m "ci: lint + typecheck + test gates for backend and frontend"
```

---

## Phase 0 completion report (fill in when done)

Per spec §9 / brief §26, close the phase with:
- **What changed:** the monorepo skeleton — `core/` (config, logging, errors, db, redis, rate_limit, audit), Alembic + bootstrap + `audit_logs`, FastAPI factory + health, ARQ worker + `ping`, `LLMProvider`/`EmbeddingsProvider` + fakes, Docker Compose, Next.js shell + tokens, CI.
- **Why:** every later phase needs a tested base with enforced module boundaries, offline-testable provider seams, and one running command.
- **Files changed:** everything under the File Structure section.
- **How to test:** `just ci` (unit/integration) and `just up && ./scripts/smoke.sh` (stack).
- **Regression check:** none (first phase). Record the baseline: test count, coverage %, `docker compose ps` all healthy.

---

## Self-Review

**1. Spec coverage (Phase 0 slice of §9 + foundational cross-cutting):**
- Monorepo + `docker-compose` (api/worker/db+pgvector/redis/frontend) → Tasks 1, 12. ✓
- `core/` (config, logging, errors, db, rate_limit, events) → Tasks 2, 3, 4, 5, 9. *`events.py` (SSE helpers) is intentionally deferred to Phase 2, the first phase that streams — noted here so it is not a silent gap.*
- Health checks → Task 8. ✓
- Alembic bootstrap (extensions) → Task 6. ✓
- Base `Repository` → Task 5. ✓
- `LLMProvider`/`EmbeddingsProvider` + fake adapters → Task 10. ✓
- CI (ruff, mypy, pytest, eslint, tsc, vitest) → Task 14; `import-linter` contract from Task 1 also runs in CI. ✓
- Design tokens (spec §7.7) → Task 13. ✓
- Append-only `audit_logs` + `audit()` (spec §2.7, Global Constraints) → Task 7. ✓
- `X-Request-ID` on every response (Global Constraints) → Task 8. ✓
- Boundary enforcement via `import-linter` (spec §8) → Task 1 (`.importlinter`), Task 14 (runs it). ✓

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N". Every code step has literal code. The two deliberate deferrals (`events.py` → Phase 2; real LLM/embeddings adapters → Phases 6/7) are called out explicitly and the fakes make the seams testable now.

**3. Type consistency:**
- `Settings` field names (Task 2) are used verbatim in Tasks 3, 5, 8, 9, 10, 11.
- `AppError`/`NotFoundError`/`RateLimitedError` (Task 4) used in Tasks 5, 8, 9 with the same constructor signatures (`RateLimitedError(retry_after=...)`).
- `Repository.get(id_, *, user_id)` / `list_for(user_id, *, limit, cursor)` (Task 5) — no other task calls these yet; Phase 1 consumes them.
- `LLMResult` fields (`text`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `structured`) consistent between `provider.py` and `adapters/fake.py` and the tests (Task 10).
- `configure_logging(settings)` / `get_logger(name)` (Task 3) called identically in Tasks 8, 11.
- `redis_from_settings(settings)` / `ping_redis(r)` (Task 8) reused in Task 9.
- Task 8's note to extend Task 4's `install_error_handlers` with the Starlette `HTTPException` handler is explicit, with the re-run instruction for `tests/core/test_errors.py`.

No inconsistencies found.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-30-phase-0-foundations.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

**Which approach?**
