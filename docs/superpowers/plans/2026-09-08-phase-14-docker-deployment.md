# Phase 14 — Docker + Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the shipped Mana Career product for one-command production bring-up: multi-stage prod image targets, a `compose.prod.yml` stack behind nginx/TLS with healthcheck-gated ordering + a migration one-shot, the existing `app.seed` CLI wired into docs, a complete `.env.example`, a deployment runbook, and a CI job that builds the images, scans them with Trivy, and runs the master's `docker compose -f compose.prod.yml up → smoke` check.

**Architecture:** Additive only. Each Dockerfile gains a `prod`/`runner` target beside its untouched `dev` target. `compose.prod.yml` is a new root file (the dev `docker-compose.yml` is unchanged). The backend prod image runs `uvicorn`/`alembic`/`arq` directly off `/app/.venv/bin` on `PATH` (no `uv run` at runtime). A dedicated `migrate` one-shot service runs `alembic upgrade head` and `api`/`worker` gate on it via `service_completed_successfully`. nginx terminates TLS and routes `/api/` + `/health*` to the backend and everything else to the Next.js standalone server, same-origin (no prod CORS dependency). Validation is CI-side (the dev box has no running Docker daemon); the per-task local gate is `docker compose config -q` + `bash -n` + the existing `just ci`.

**Tech Stack:** Docker multi-stage builds, Docker Compose v2 (long-form `depends_on`, `service_completed_successfully`, `env_file: required: false`), nginx 1.27-alpine, `pgvector/pgvector:pg16`, `redis:7-alpine`, `python:3.12-slim` + `uv`, `node:22-slim` + pnpm 11 + Next.js standalone output, `aquasecurity/trivy-action`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-08-phase-14-docker-deployment.md`

## Global Constraints

- **Additive only.** No `app/**` or `frontend/{app,lib,components,providers,hooks}/**` behavioural change. The only tracked code touched: two Dockerfiles (new stages + one base-image bump), `.env.example` / `backend/.env.example` (docs), `.gitignore`, `.github/workflows/ci.yml`, `justfile`, `README.md`. (Spec R1)
- **Dev targets frozen.** `backend/Dockerfile`'s `base` + `dev` stages and `frontend/Dockerfile`'s `dev` stage keep their exact behaviour — `docker-compose.yml` builds `target: dev` and must keep working. `git diff` on each Dockerfile must show only additions after the existing stages, plus (frontend only) the single `node:20-slim` → `node:22-slim` change on the `base` line. (Spec R2)
- **No local Docker daemon / no Trivy on the dev box.** Per-task local verification = `docker compose -f compose.prod.yml config -q` (daemon-free YAML+interpolation validation), `bash -n <script>` on every shell file touched, by-eye Dockerfile review, and `just ci` staying green. The authoritative build + scan + bring-up + smoke is the new CI `images` job. (Spec R13)
- **Audit/scan gates are not `|| true`-neutered.** Trivy runs with `exit-code: 1`; `ignore-unfixed: true` is the only escape (a HIGH/CRITICAL *with a fix available* fails the build) — same philosophy as Phase 13's `pip-audit` / `pnpm audit` gates. (Spec R11)
- **Same-origin frontend.** The production client bundle is built with `NEXT_PUBLIC_API_BASE_URL` empty so it calls relative `/api/v1/...` + `/health*`, which nginx routes to the backend. (Spec R2/R9)
- **Runbook path** is `docs/runbook.md` (master §8); the row-14 "deploy doc" is the same single file. (Spec R14)
- **Image tags:** `mana-career-api:${TAG:-local}`, `mana-career-worker:${TAG:-local}`, `mana-career-frontend:${TAG:-local}`. (Spec R4)
- **Non-root runtime:** every long-running prod container runs as uid `10001`. (Spec R2)

### Plan-level rulings (deviations from / tightenings of the spec)

- **PR-1 (tightens R9):** `compose.prod.yml`'s `frontend.build.args.NEXT_PUBLIC_API_BASE_URL` is the **literal empty string `""`**, not `${NEXT_PUBLIC_API_BASE_URL:-}`. Reason: compose interpolates `${...}` from the project `.env`, whose existing dev line is `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` — that value would bake into the production client bundle. Hardcoding `""` gives the correct same-origin default with zero `.env` coupling; a split-origin deployer edits this one line (documented in `.env.example` + runbook). Cost if wrong: a split-origin deploy needs a one-line compose edit instead of an env var — acceptable, it is the rarer case.
- **PR-2 (tightens R2):** the backend prod image puts `/app/.venv/bin` on `PATH` and runs `uvicorn` / `alembic` / `arq` as **direct entrypoints**, not via `uv run`. Reason: `uv run` performs an implicit `uv sync` (project reinstall / hatchling packaging resolution) on every invocation unless suppressed; the direct-binary form is the conventional uv-in-prod pattern and removes that failure surface. `PYTHONPATH=/app` + cwd `/app` keep `app.main` / alembic's `prepend_sys_path=.` importable without an editable install (`uv sync --no-install-project`). Cost if wrong: none identified.
- **PR-3 (fills an R2 gap):** the frontend `builder` stage runs `RUN mkdir -p public` before `pnpm build`, because the repo currently has **no `frontend/public/` dir** and the `runner` stage's `COPY --from=builder /app/public` would fail without it. Keeps the COPY stable whether or not static assets are added later.
- **PR-4 (tightens R4):** `compose.prod.yml` sets `env_file: [{ path: .env, required: false }]` so the `config -q` local gate and the CI job work without a pre-existing `.env`. All deploy-critical values still come from `environment:` overrides (DB/Redis URLs) or have compose `:-` defaults; a real `up` still fails loudly if `.env` is missing the app's required `JWT_SECRET`.

---

## Task 1: Backend production image target

**Files:**
- Modify: `backend/Dockerfile` (append a `prod` stage after the existing `dev` stage; do not touch `base` or `dev`)
- Create: `backend/.dockerignore`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - A `prod` build stage in `backend/Dockerfile`. Built as `docker build --target prod ./backend`.
  - Runtime contract relied on by Task 3: image `WORKDIR` is `/app`; `/app/.venv/bin` is on `PATH`; `uvicorn`, `alembic`, `arq` are directly invocable; default `CMD` starts uvicorn on `0.0.0.0:8000`; container runs as uid `10001`; `PYTHONPATH=/app`.

**Context:** The current `backend/Dockerfile` is:
```dockerfile
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv
WORKDIR /app

FROM base AS dev
# Dependency layer (cached until pyproject/lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```
`base` + `dev` stay exactly as above.

- [ ] **Step 1: Append the `prod` stage to `backend/Dockerfile`**

Add these lines at the end of the file (after the `dev` stage's `CMD` line), separated by a blank line:

```dockerfile

FROM base AS prod
ENV UV_COMPILE_BYTECODE=1
# Dependency layer only — no project, no dev group (cached until pyproject/lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
# App source
COPY . .
RUN useradd --system --uid 10001 app && chown -R app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app ENV=prod
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

Rationale for each line:
- `UV_COMPILE_BYTECODE=1` — precompile `.pyc` for faster cold start.
- `uv sync --frozen --no-install-project --no-dev` before `COPY . .` — deps-only layer, cache-stable across app-code edits; `--no-dev` drops `pytest`/`ruff`/`mypy`/`pip-audit`/etc.
- No second `uv sync` after `COPY . .` — the app is imported from source on `PYTHONPATH`, not installed (PR-2). Deps are already present from the first sync.
- `useradd --system --uid 10001 app && chown -R app /app` then `USER app` — non-root runtime; `chown` covers `/app/.venv`.
- `PATH="/app/.venv/bin:$PATH"` — `uvicorn`, `alembic`, `arq` resolve directly (PR-2).
- `PYTHONPATH=/app ENV=prod` — `app.main` importable; safe prod default (compose `.env` overrides `ENV` for the CI smoke).
- `--workers 2`, no `--reload`.

- [ ] **Step 2: Create `backend/.dockerignore`**

The `backend/Dockerfile` builds with context `./backend`, so the repo-root `.dockerignore` does not apply. Create `backend/.dockerignore`:

```
__pycache__/
**/__pycache__/
.venv/
.venv.broken/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
var/
tests/
.env
.env.*
*.md
```

Notes: `pyproject.toml`, `uv.lock`, `app/`, `alembic/`, `alembic.ini`, `eval/` are **not** excluded — `uv sync` needs `pyproject.toml`+`uv.lock`, and the app needs `app/` + `alembic/`. `tests/` is excluded (not needed at runtime; smaller image). `*.md` excludes stray docs from the context.

- [ ] **Step 3: Verify `dev` and `base` are untouched**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && git diff backend/Dockerfile
```
Expected: the diff shows **only** added lines, all after the existing `CMD ["uv", "run", ... "--reload"]` line. No `-` (removed) lines. If any existing line changed, revert that part.

- [ ] **Step 4: Sanity-check the Dockerfile by eye against the hadolint rule set**

Confirm: base image is pinned (`python:3.12-slim` ✓, inherited), `USER` is set before `CMD` ✓, no secret in `ENV`/`ARG` ✓, no `apt-get` added ✓, `COPY` (not `ADD`) ✓, `CMD` is exec-form JSON array ✓.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/chitt/Career Assistant" && git add backend/Dockerfile backend/.dockerignore && git commit -m "build(backend): production image target + backend .dockerignore"
```

---

## Task 2: Frontend production image target

**Files:**
- Modify: `frontend/Dockerfile` (change the `base` line `node:20-slim` → `node:22-slim`; append `deps`, `builder`, `runner` stages after the existing `dev` stage; do not otherwise touch `dev`)
- Create: `frontend/.dockerignore`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - A `runner` build stage in `frontend/Dockerfile`. Built as `docker build --target runner --build-arg NEXT_PUBLIC_API_BASE_URL="" ./frontend`.
  - Runtime contract relied on by Task 3: `WORKDIR /app`; default `CMD ["node", "server.js"]`; listens on `0.0.0.0:3000` (`ENV HOSTNAME=0.0.0.0 PORT=3000`); runs as uid `10001`; the Next.js client bundle has whatever `NEXT_PUBLIC_API_BASE_URL` was passed as a `--build-arg` inlined (empty ⇒ same-origin relative requests).

**Context:** The current `frontend/Dockerfile` is:
```dockerfile
FROM node:20-slim AS base
RUN corepack enable
WORKDIR /app

FROM base AS dev
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]
```
`frontend/next.config.ts` already sets `output: "standalone"` (so `pnpm build` emits `.next/standalone/server.js`). The frontend CI job uses node 22 + pnpm 11 — the image must match to avoid a "green in CI, broken in image" gap.

- [ ] **Step 1: Bump the `base` image**

In `frontend/Dockerfile`, change the first line only:
```
FROM node:20-slim AS base
```
to
```
FROM node:22-slim AS base
```
Leave `RUN corepack enable`, `WORKDIR /app`, and the entire `dev` stage exactly as they are.

- [ ] **Step 2: Append `deps`, `builder`, `runner` stages**

Add at the end of the file (after the `dev` stage's `CMD` line), separated by a blank line:

```dockerfile

FROM base AS deps
RUN corepack prepare pnpm@11 --activate
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

FROM deps AS builder
COPY . .
# public/ may not exist in the repo yet — keep the runner COPY stable
RUN mkdir -p public
ARG NEXT_PUBLIC_API_BASE_URL=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN pnpm build

FROM node:22-slim AS runner
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
RUN useradd --system --uid 10001 --create-home app
WORKDIR /app
COPY --from=builder --chown=app /app/.next/standalone ./
COPY --from=builder --chown=app /app/.next/static ./.next/static
COPY --from=builder --chown=app /app/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
```

Rationale:
- `deps` pins `pnpm@11` (CI parity — the base only does `corepack enable`, which floats) and installs with `--frozen-lockfile`.
- `builder` copies source, guarantees `public/` exists (PR-3), takes `NEXT_PUBLIC_API_BASE_URL` as a build arg (default `""`), inlines it via `ENV` for `next build`, then builds.
- `runner` is a clean `node:22-slim` (no pnpm, no source) — copies only the standalone server, static assets, and `public/`; runs as non-root; `HOSTNAME=0.0.0.0` so Next's standalone server is reachable from outside the container; `node server.js` is the standalone entrypoint.

- [ ] **Step 3: Create `frontend/.dockerignore`**

The `frontend/Dockerfile` builds with context `./frontend`. Create `frontend/.dockerignore`:

```
node_modules/
.next/
coverage/
.env
.env.*
tests/
test/
*.tsbuildinfo
.turbo/
```

Notes: `package.json`, `pnpm-lock.yaml`, `next.config.ts`, `tsconfig.json`, `postcss.config.mjs`, `app/`, `components/`, `lib/`, `providers/`, `hooks/`, `styles/`, `types/` are **not** excluded — `next build` needs them. `tests/` + `test/` + `*.tsbuildinfo` are excluded.

- [ ] **Step 4: Verify `dev` is untouched apart from the inherited base bump**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && git diff frontend/Dockerfile
```
Expected: exactly one changed line in the existing content — `node:20-slim` → `node:22-slim` on the `base` line — plus the appended `deps`/`builder`/`runner` block. No other `-` lines. The `dev` stage body is byte-identical.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/chitt/Career Assistant" && git add frontend/Dockerfile frontend/.dockerignore && git commit -m "build(frontend): standalone runner image target (node 22) + frontend .dockerignore"
```

---

## Task 3: Production compose stack + nginx + env

**Files:**
- Create: `compose.prod.yml` (repo root)
- Create: `deploy/nginx/nginx.conf`
- Create: `deploy/nginx/certs/.gitkeep`
- Modify: `.gitignore` (add the certs ignore pair)
- Modify: `.env.example` (add compose-only vars + the PRODUCTION reference block)
- Modify: `backend/.env.example` (add a one-line pointer comment)

**Interfaces:**
- Consumes:
  - `backend/Dockerfile` `prod` target (Task 1): `WORKDIR /app`, `/app/.venv/bin` on `PATH`, `PYTHONPATH=/app`, `alembic`/`arq`/`uvicorn` on `PATH`, `EXPOSE 8000`, non-root.
  - `frontend/Dockerfile` `runner` target (Task 2): `CMD ["node","server.js"]`, listens `0.0.0.0:3000`, `EXPOSE 3000`, non-root.
- Produces:
  - `compose.prod.yml` with services `db`, `redis`, `migrate`, `api`, `worker`, `frontend`, `nginx` and a `pgdata` named volume; images tagged `mana-career-{api,worker,frontend}:${TAG:-local}`. Consumed by Task 4 (CI builds/scans these) and Task 5 (runbook + `just` targets reference it).
  - `deploy/nginx/nginx.conf` mounted read-only into the `nginx` service at `/etc/nginx/nginx.conf`; expects certs at `/etc/nginx/certs/{fullchain.pem,privkey.pem}`; exposes `GET /nginx-health` → `200 "ok\n"`.

**Context:** the dev `docker-compose.yml` wires env like this (mirror the `DATABASE_URL`/`REDIS_URL` service-name pattern):
```yaml
    environment:
      DATABASE_URL: postgresql+asyncpg://mana:mana@db:5432/mana
      REDIS_URL: redis://redis:6379/0
```
`app/api/v1/health.py` serves `GET /health` → `{"status":"ok"}` and `GET /health/ready` → 200 (all of db+redis+`alembic_version` ok) or 503, at both `/api/v1/health*` and root `/health*`.

- [ ] **Step 1: Create `compose.prod.yml`**

```yaml
name: mana-career-prod

x-backend-build: &backend-build
  context: ./backend
  target: prod

x-backend-env: &backend-env
  DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-mana}:${POSTGRES_PASSWORD:-mana}@db:5432/${POSTGRES_DB:-mana}
  REDIS_URL: redis://redis:6379/0

services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-mana}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-mana}
      POSTGRES_DB: ${POSTGRES_DB:-mana}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-mana}"]
      interval: 5s
      timeout: 3s
      retries: 20
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20
    restart: unless-stopped

  migrate:
    image: mana-career-api:${TAG:-local}
    build: *backend-build
    command: ["alembic", "upgrade", "head"]
    env_file:
      - path: .env
        required: false
    environment: *backend-env
    depends_on:
      db:
        condition: service_healthy
    restart: "no"

  api:
    image: mana-career-api:${TAG:-local}
    build: *backend-build
    env_file:
      - path: .env
        required: false
    environment: *backend-env
    depends_on:
      migrate:
        condition: service_completed_successfully
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/ready').status==200 else 1)"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
    restart: unless-stopped

  worker:
    image: mana-career-worker:${TAG:-local}
    build: *backend-build
    command: ["arq", "app.worker.main.WorkerSettings"]
    env_file:
      - path: .env
        required: false
    environment: *backend-env
    depends_on:
      migrate:
        condition: service_completed_successfully
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    image: mana-career-frontend:${TAG:-local}
    build:
      context: ./frontend
      target: runner
      args:
        NEXT_PUBLIC_API_BASE_URL: ""
    healthcheck:
      test: ["CMD", "node", "-e", "require('http').get('http://localhost:3000/',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped

  nginx:
    image: nginx:1.27-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./deploy/nginx/certs:/etc/nginx/certs:ro
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost/nginx-health"]
      interval: 10s
      timeout: 5s
      retries: 6
    depends_on:
      api:
        condition: service_healthy
      frontend:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
```

Key points:
- `migrate` and `api` share `image: mana-career-api:${TAG:-local}` with the same `build`; `worker` builds an identical image under its own tag `mana-career-worker` (spec R4 — clearer Trivy output + independent rollback; Docker dedupes identical layers).
- `migrate.command` / `worker.command` override the image `CMD` with the direct `alembic` / `arq` binaries (on `PATH` from Task 1).
- `api` has **no** `command:` — it uses the image's default `uvicorn ... --workers 2`.
- `environment: *backend-env` overrides any `DATABASE_URL`/`REDIS_URL` coming from `.env`, forcing the compose service names.
- `NEXT_PUBLIC_API_BASE_URL: ""` is hardcoded (PR-1).
- `env_file … required: false` (PR-4) — `config -q` and CI work without a `.env`.
- Only `nginx` publishes host ports. `db`/`redis`/`api`/`worker`/`frontend` are reachable only on the compose network.
- `pgdata` named volume persists Postgres data across `down`/`up` (lost only on `down -v`).

- [ ] **Step 2: Create `deploy/nginx/nginx.conf`**

```nginx
worker_processes auto;
events { worker_connections 1024; }

http {
  include       /etc/nginx/mime.types;
  default_type  application/octet-stream;
  sendfile      on;
  keepalive_timeout 65;
  client_max_body_size 12m;

  gzip on;
  gzip_types text/plain text/css application/json application/javascript application/xml image/svg+xml;

  # Preserve an inbound X-Request-ID, else let nginx mint one.
  map $http_x_request_id $req_id {
    default $http_x_request_id;
    ""      $request_id;
  }

  upstream api { server api:8000; }
  upstream web { server frontend:3000; }

  # Inherited by every location that does NOT set its own proxy_set_header.
  proxy_http_version 1.1;
  proxy_set_header Host              $host;
  proxy_set_header X-Real-IP         $remote_addr;
  proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Request-ID      $req_id;

  # ---- HTTP :80 -> redirect to HTTPS ----
  server {
    listen 80;
    server_name _;
    location = /nginx-health { return 200 "ok\n"; add_header Content-Type text/plain; }
    location / { return 301 https://$host$request_uri; }
  }

  # ---- HTTPS :443 ----
  server {
    listen 443 ssl;
    http2 on;
    server_name _;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location = /nginx-health { return 200 "ok\n"; add_header Content-Type text/plain; }

    # Container / uptime probes -> backend health (also mounted at root by the app).
    location ~ ^/health(/ready)?$ {
      proxy_pass http://api;
    }

    # API + SSE. proxy_buffering off + long read timeout are required for the
    # EventSource streams (/api/v1/jobs/*/events, /roadmaps/*/events, agent runs).
    location /api/ {
      proxy_pass http://api;
      proxy_buffering off;
      proxy_read_timeout 3600s;
    }

    # Everything else -> Next.js standalone server.
    location / {
      proxy_pass http://web;
    }
  }
}
```

Why no `proxy_set_header` inside any `location`: nginx replaces the *entire* inherited set the moment a level adds one. Keeping all headers at `http` scope and only non-header directives (`proxy_buffering`, `proxy_read_timeout`) in `location /api/` means every location inherits the full header set correctly.

- [ ] **Step 3: Create `deploy/nginx/certs/.gitkeep`**

Empty file. Run:
```bash
cd "C:/Users/chitt/Career Assistant" && mkdir -p deploy/nginx/certs && : > deploy/nginx/certs/.gitkeep
```

- [ ] **Step 4: Add the certs ignore pair to `.gitignore`**

The current `.gitignore` has (around lines 21-28):
```
.env
.env.*
!.env.example
...
backend/var/
```
Append at the end of the file:
```

# Local TLS material for compose.prod.yml (never commit real keys)
deploy/nginx/certs/*
!deploy/nginx/certs/.gitkeep
```

- [ ] **Step 5: Extend `.env.example`**

The file currently ends with:
```
LLM_MODEL_EXTRACTION=claude-haiku-4-5-20251001
ANTHROPIC_MODEL_FALLBACK=claude-sonnet-5

# ---- Frontend ----
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```
Leave every existing line as-is (dev stays working out of the box). Append:
```

# ---- Compose (compose.prod.yml interpolation only; NOT read by app Settings) ----
POSTGRES_USER=mana
POSTGRES_PASSWORD=mana
POSTGRES_DB=mana
TAG=local

# ==================== PRODUCTION — change before deploying ====================
# Copy this file to .env, then override at least:
#   ENV=prod
#   JWT_SECRET=                 # generate: openssl rand -hex 32
#   POSTGRES_PASSWORD=          # a real secret (also feeds DATABASE_URL in compose.prod.yml)
#   REFRESH_COOKIE_SECURE=true
#   LLM_PROVIDER=anthropic
#   ANTHROPIC_API_KEY=
#   EMBEDDINGS_PROVIDER=voyage
#   VOYAGE_API_KEY=
#   CORS_ORIGINS=https://your-domain.example   # only for a split-origin deploy
# The bundled nginx serves the app and API same-origin, so the frontend needs
# NO API base URL. For a split-origin deploy, set the build arg in
# compose.prod.yml (frontend.build.args.NEXT_PUBLIC_API_BASE_URL) and set
# CORS_ORIGINS above. Full procedure: docs/runbook.md
```

- [ ] **Step 6: Add a pointer comment to `backend/.env.example`**

`backend/.env.example` is a dev convenience copy. Add as its **first** line (before `# ---- Backend ----`):
```
# Dev defaults. For production values and compose vars see the root .env.example
```

- [ ] **Step 7: Verify the compose file parses (daemon-free)**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && docker compose -f compose.prod.yml config -q && echo "compose OK"
```
Expected: prints `compose OK`, exit 0, no warnings about undefined variables. If it complains about a missing `.env`, confirm the `env_file` blocks use the `path:`/`required: false` long form.

- [ ] **Step 8: Verify the interpolated topology**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && docker compose -f compose.prod.yml config | grep -E "image:|target:|condition:|published:|source:.*nginx" 
```
Expected to see: `mana-career-api:local` (twice — migrate + api), `mana-career-worker:local`, `mana-career-frontend:local`, `target: prod` / `target: runner`, `service_completed_successfully` + `service_healthy` conditions, `published: "80"` / `"443"` only, and the two nginx bind-mount sources.

- [ ] **Step 9: Confirm `just ci` still green**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && just ci
```
Expected: backend ruff + lint-imports + mypy + pytest (pure suites; DB-gated ones ERROR at the `_migrated` fixture as always) and frontend lint + tsc + vitest all pass. (This only proves the `.env.example` / gitignore edits didn't disturb anything importable — none of them should.)

- [ ] **Step 10: Commit**

```bash
cd "C:/Users/chitt/Career Assistant" && git add compose.prod.yml deploy/nginx/nginx.conf deploy/nginx/certs/.gitkeep .gitignore .env.example backend/.env.example && git commit -m "build: compose.prod.yml stack (nginx/TLS, migrate one-shot) + prod .env.example"
```

---

## Task 4: CI `images` job + production smoke script

**Files:**
- Create: `scripts/smoke-prod.sh`
- Modify: `.github/workflows/ci.yml` (add a fourth job `images`)

**Interfaces:**
- Consumes:
  - `compose.prod.yml` (Task 3) — service names, image tags `mana-career-{api,worker,frontend}:local`, the `nginx` service on ports 80/443, `deploy/nginx/certs/{fullchain.pem,privkey.pem}`.
  - `scripts/smoke.sh` (existing) — style reference:
    ```bash
    #!/usr/bin/env bash
    set -euo pipefail
    fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }
    curl -fsS http://localhost:8000/health | grep -q '"status":"ok"' || fail "api /health"
    code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health/ready)
    [ "$code" = "200" ] || fail "api /health/ready returned $code"
    ...
    echo "SMOKE OK"
    ```
- Produces:
  - `scripts/smoke-prod.sh` — exits 0 only if the full nginx-fronted stack answers. Reused by `just smoke-prod` (Task 5).
  - A CI job `images` that builds all three prod images, Trivy-scans them (HIGH/CRITICAL, fail on fixable), brings the stack up, and runs `scripts/smoke-prod.sh`.

**Context:** the current `.github/workflows/ci.yml` has jobs `backend`, `eval`, `frontend` (each `runs-on: ubuntu-latest`), triggered `on: push: branches: ["**"]` + `pull_request`. Phase 13 added `- run: uv run pip-audit` and `- run: pnpm audit --audit-level=high` as non-neutered gates.

- [ ] **Step 1: Create `scripts/smoke-prod.sh`**

```bash
#!/usr/bin/env bash
# Production smoke: the full compose.prod.yml stack, reached through nginx/TLS.
# Self-signed certs -> curl -k. Run after `docker compose -f compose.prod.yml up -d`.
set -euo pipefail

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

base_https="https://localhost"
base_http="http://localhost"

# 1. nginx liveness
curl -fsSk "$base_https/nginx-health" | grep -q "ok" || fail "nginx /nginx-health"

# 2. backend health through nginx
curl -fsSk "$base_https/health" | grep -q '"status":"ok"' || fail "/health via nginx"

# 3. backend readiness through nginx (db + redis + migrations)
code=$(curl -s -o /dev/null -w '%{http_code}' -k "$base_https/health/ready")
[ "$code" = "200" ] || fail "/health/ready returned $code"

# 4. API reachable through the /api/ location
code=$(curl -s -o /dev/null -w '%{http_code}' -k "$base_https/api/openapi.json")
[ "$code" = "200" ] || fail "/api/openapi.json returned $code"

# 5. frontend (Next.js standalone) served at /
code=$(curl -s -o /dev/null -w '%{http_code}' -k "$base_https/")
[ "$code" = "200" ] || fail "frontend / returned $code"

# 6. plain HTTP is redirected to HTTPS
redirect=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$base_http/")
case "$redirect" in
  30[12]\ https://*) : ;;
  *) fail "http:// not redirected to https (got: $redirect)" ;;
esac

echo "SMOKE OK"
```

- [ ] **Step 2: `bash -n` the new script**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && bash -n scripts/smoke-prod.sh && echo "syntax OK"
```
Expected: `syntax OK`.

- [ ] **Step 3: `chmod +x` the script**

```bash
cd "C:/Users/chitt/Career Assistant" && chmod +x scripts/smoke-prod.sh && git update-index --chmod=+x scripts/smoke-prod.sh 2>/dev/null || true
```

- [ ] **Step 4: Add the `images` job to `.github/workflows/ci.yml`**

Append this job under `jobs:` (after `frontend:`), matching the file's 2-space indentation:

```yaml
  images:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3

      - name: Seed a dev .env for the smoke
        run: cp .env.example .env

      - name: Generate a throwaway self-signed cert
        run: |
          mkdir -p deploy/nginx/certs
          openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
            -keyout deploy/nginx/certs/privkey.pem \
            -out deploy/nginx/certs/fullchain.pem \
            -subj "/CN=localhost"

      - name: Build production images
        run: docker compose -f compose.prod.yml build

      - name: Trivy scan (api)
        uses: aquasecurity/trivy-action@0.24.0
        with:
          image-ref: mana-career-api:local
          severity: HIGH,CRITICAL
          ignore-unfixed: true
          exit-code: "1"

      - name: Trivy scan (worker)
        uses: aquasecurity/trivy-action@0.24.0
        with:
          image-ref: mana-career-worker:local
          severity: HIGH,CRITICAL
          ignore-unfixed: true
          exit-code: "1"

      - name: Trivy scan (frontend)
        uses: aquasecurity/trivy-action@0.24.0
        with:
          image-ref: mana-career-frontend:local
          severity: HIGH,CRITICAL
          ignore-unfixed: true
          exit-code: "1"

      - name: Bring the stack up
        run: docker compose -f compose.prod.yml up -d

      - name: Wait for readiness
        run: |
          for i in $(seq 1 30); do
            if curl -fsSk https://localhost/health/ready >/dev/null 2>&1; then
              echo "ready after ${i} tries"; exit 0
            fi
            sleep 3
          done
          echo "stack did not become ready in 90s"; exit 1

      - name: Smoke
        run: ./scripts/smoke-prod.sh

      - name: Dump logs on failure
        if: failure()
        run: docker compose -f compose.prod.yml logs --no-color

      - name: Tear down
        if: always()
        run: docker compose -f compose.prod.yml down -v
```

Notes:
- `ignore-unfixed: true` is the sanctioned escape (Global Constraints). A HIGH/CRITICAL **with a fix** fails the job.
- `cp .env.example .env` gives the dev-default (fake providers) config — enough for the stack to boot and answer health/smoke without real API keys.
- The readiness loop polls the nginx-fronted `/health/ready` (needs `-k` for the self-signed cert).
- `down -v` in an `always()` step frees the runner's volumes.
- Pin `aquasecurity/trivy-action@0.24.0` (a real released tag) — if the implementer finds a newer stable tag, using it is fine; do not use `@master`.

- [ ] **Step 5: Validate the workflow YAML**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/ci.yml')); assert 'images' in d['jobs']; assert d['jobs']['images']['runs-on']=='ubuntu-latest'; print('jobs:', list(d['jobs']))"
```
Expected: `jobs: ['backend', 'eval', 'frontend', 'images']`.

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/chitt/Career Assistant" && git add scripts/smoke-prod.sh .github/workflows/ci.yml && git commit -m "ci: images job — build, Trivy scan, compose.prod up, prod smoke"
```

---

## Task 5: Runbook + `just` targets + README

**Files:**
- Create: `docs/runbook.md`
- Modify: `justfile` (add `prod-up`, `prod-down`, `prod-logs`, `seed`, `smoke-prod`)
- Modify: `README.md` ("Running it" — add a Production paragraph)

**Interfaces:**
- Consumes: everything from Tasks 1-4 — `compose.prod.yml` service names + `run --rm migrate`, `scripts/smoke-prod.sh`, `deploy/nginx/certs/`, the `app.seed` CLI (`python -m app.seed {skills|jobs|learning|all}` — already exists in `backend/app/seed.py`).
- Produces: operator docs. No downstream consumer (last task).

**Context:** the current `justfile` (uses `set shell := ["bash", "-uc"]`):
```
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
    ./scripts/smoke.sh
```
The `app.seed` CLI: `python -m app.seed skills|jobs|learning|all` — opens its own `AsyncSessionLocal`, commits, prints a count. In the prod image it runs as `python -m app.seed all` with `/app/.venv/bin` on `PATH`.

- [ ] **Step 1: Add the prod `just` targets**

Append to `justfile` (keep every existing target; match the existing style — target name, then tab-indented recipe lines):

```
prod-up:
    docker compose -f compose.prod.yml up -d --build

prod-down:
    docker compose -f compose.prod.yml down

prod-logs:
    docker compose -f compose.prod.yml logs -f

seed:
    docker compose -f compose.prod.yml run --rm migrate python -m app.seed all

smoke-prod:
    ./scripts/smoke-prod.sh
```

Note `seed` overrides the `migrate` service's `command` (`alembic upgrade head`) with `python -m app.seed all` — the `migrate` service already carries the prod image, `.env`, and a `db` dependency, so it is the natural one-shot host. `prod-down` (no `-v`) preserves `pgdata`; use `docker compose -f compose.prod.yml down -v` by hand to wipe.

- [ ] **Step 2: Create `docs/runbook.md`**

```markdown
# Mana Career — Deployment Runbook

The production stack is `compose.prod.yml`: Postgres 16 + pgvector, Redis 7, the
FastAPI `api`, the ARQ `worker`, the Next.js standalone `frontend`, and an
`nginx` reverse proxy terminating TLS. A one-shot `migrate` service runs
`alembic upgrade head` before `api`/`worker` start.

`AI recommends -> AI prepares -> Human decides` — nothing is emailed without an
explicit in-app approval; see `SECURITY.md` and `docs/threat-model.md`.

## 1. Prerequisites

- Docker Engine 24+ with the Compose v2 plugin (`docker compose version`).
- A host with ports 80 and 443 free.
- For real TLS: a domain with DNS pointing at the host, and a certificate
  chain + private key. The default below uses a self-signed pair.

## 2. First boot

```bash
git clone https://github.com/manideep311/Mana_Career.git
cd Mana_Career

# 2.1 Configure
cp .env.example .env
#   Edit .env — at minimum (see the PRODUCTION block in the file):
#     ENV=prod
#     JWT_SECRET=$(openssl rand -hex 32)
#     POSTGRES_PASSWORD=<a real secret>
#     REFRESH_COOKIE_SECURE=true
#     LLM_PROVIDER=anthropic   + ANTHROPIC_API_KEY=...      (or leave fake)
#     EMBEDDINGS_PROVIDER=voyage + VOYAGE_API_KEY=...        (or leave fake)

# 2.2 TLS material -> deploy/nginx/certs/{fullchain.pem,privkey.pem}
#   Self-signed (dev / demo):
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout deploy/nginx/certs/privkey.pem \
  -out deploy/nginx/certs/fullchain.pem \
  -subj "/CN=localhost"
#   Real cert: drop your chain + key in as those exact two filenames.

# 2.3 Build images
docker compose -f compose.prod.yml build

# 2.4 Start data services, run migrations, seed reference data
docker compose -f compose.prod.yml up -d db redis
docker compose -f compose.prod.yml run --rm migrate                         # alembic upgrade head
docker compose -f compose.prod.yml run --rm migrate python -m app.seed all  # skills + jobs + learning

# 2.5 Start everything
docker compose -f compose.prod.yml up -d
```

`just` shortcuts: `just prod-up` (build + up), `just seed`, `just smoke-prod`,
`just prod-logs`, `just prod-down`.

## 3. Verify

```bash
docker compose -f compose.prod.yml ps        # every service "healthy" / migrate "exited (0)"
./scripts/smoke-prod.sh                       # -> SMOKE OK
curl -sk https://localhost/health/ready | jq  # {"status":"ready","checks":{...}}
```

Open `https://localhost/` (accept the self-signed warning) — the app shell loads
and talks to the API same-origin through nginx.

## 4. Routine operations

| Task | Command |
|---|---|
| Tail logs | `docker compose -f compose.prod.yml logs -f [service]` |
| Restart one service | `docker compose -f compose.prod.yml restart api` |
| Apply a new migration | `git pull && docker compose -f compose.prod.yml build && docker compose -f compose.prod.yml run --rm migrate && docker compose -f compose.prod.yml up -d` |
| Re-seed reference data | `docker compose -f compose.prod.yml run --rm migrate python -m app.seed all` |
| Stop (keep data) | `docker compose -f compose.prod.yml down` |
| Stop and wipe data | `docker compose -f compose.prod.yml down -v` |

## 5. Backup

Two pieces of state: the `pgdata` volume (all rows) and `backend/var/files`
(uploaded résumés, if `FILE_STORE=local`).

```bash
# Postgres logical dump (run on a schedule, e.g. cron @daily)
docker compose -f compose.prod.yml exec -T db \
  pg_dump -U "${POSTGRES_USER:-mana}" "${POSTGRES_DB:-mana}" | gzip > "backup-$(date +%F).sql.gz"

# Uploaded files
tar czf "files-$(date +%F).tgz" backend/var/files
```

## 6. Restore

```bash
docker compose -f compose.prod.yml up -d db
gunzip -c backup-YYYY-MM-DD.sql.gz | docker compose -f compose.prod.yml exec -T db \
  psql -U "${POSTGRES_USER:-mana}" -d "${POSTGRES_DB:-mana}"
tar xzf files-YYYY-MM-DD.tgz
docker compose -f compose.prod.yml up -d
```

## 7. Upgrade & rollback

**Upgrade:** `git pull` -> `docker compose -f compose.prod.yml build` ->
`docker compose -f compose.prod.yml run --rm migrate` ->
`docker compose -f compose.prod.yml up -d`. Take a backup (section 5) first.

**Rollback:**
- Code/image: check out the previous commit (or set `TAG=` in `.env` to a
  previously built image tag) and `docker compose -f compose.prod.yml up -d`.
- Schema: `docker compose -f compose.prod.yml run --rm migrate alembic downgrade -1`
  (or `alembic downgrade <rev>`). Restore from a dump if a migration was
  destructive.

## 8. TLS in production

Replace `deploy/nginx/certs/{fullchain.pem,privkey.pem}` with your CA-issued
chain and key (same filenames), then `docker compose -f compose.prod.yml
restart nginx`. For automatic renewal, terminate TLS at an upstream load
balancer or add an ACME sidecar — out of scope here (single-tenant portfolio).

## 9. Out of scope (see the Phase 14 spec §3)

Kubernetes/Helm, cloud IaC, managed Postgres/Redis, a CDN, ACME automation,
multi-node/HA, secret managers, log shipping/APM, pushing images to a registry,
the S3 `FileStore` adapter, load/soak testing.
```

- [ ] **Step 3: Add the Production paragraph to `README.md`**

The "## Running it" section currently ends with:
```
`just` targets: `just up` / `just down` / `just migrate` / `just ci` / `just smoke`.
Copy `.env.example` to `.env` first; the LLM/embeddings providers default to deterministic
fakes so the whole stack runs offline.
```
Append immediately after that paragraph:
```

**Production:** `compose.prod.yml` builds multi-stage images and runs the stack
behind an nginx reverse proxy with TLS, a one-shot Alembic `migrate` service,
and healthcheck-gated startup. `just prod-up` / `just seed` / `just smoke-prod`;
full procedure (certs, backup, restore, rollback) in
[`docs/runbook.md`](docs/runbook.md).
```

- [ ] **Step 4: Verify `justfile` still parses**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && just --list
```
Expected: the list includes `prod-up`, `prod-down`, `prod-logs`, `seed`, `smoke-prod` alongside the existing targets, no parse error.

- [ ] **Step 5: Link-check the new doc**

Run:
```bash
cd "C:/Users/chitt/Career Assistant" && test -f docs/runbook.md && grep -q "runbook.md" README.md && echo "docs wired"
```
Expected: `docs wired`.

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/chitt/Career Assistant" && git add docs/runbook.md justfile README.md && git commit -m "docs: deployment runbook + prod just targets + README production note"
```

---

## Final verification (whole-branch, before the phase review)

Run all of:
```bash
cd "C:/Users/chitt/Career Assistant"
docker compose -f compose.prod.yml config -q && echo "compose OK"
bash -n scripts/smoke-prod.sh && echo "smoke syntax OK"
python -c "import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); assert list(d['jobs'])==['backend','eval','frontend','images'], list(d['jobs']); print('ci jobs OK')"
git diff main --stat
just ci
```
Expected: `compose OK`, `smoke syntax OK`, `ci jobs OK`; the diffstat touches only the **15 files** in the spec's manifest — 7 created (`compose.prod.yml`, `backend/.dockerignore`, `frontend/.dockerignore`, `deploy/nginx/nginx.conf`, `deploy/nginx/certs/.gitkeep`, `scripts/smoke-prod.sh`, `docs/runbook.md`) + 8 modified (`backend/Dockerfile`, `frontend/Dockerfile`, `.env.example`, `backend/.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `justfile`, `README.md`); `just ci` green (DB-gated backend tests ERROR at `_migrated` as always — that is the documented local baseline, not a regression).

The real end-to-end proof (image build + Trivy + `compose.prod.yml up` + `smoke-prod.sh`) runs in the CI `images` job after the branch is pushed.

## Self-review notes (done during planning)

- **Spec coverage:** R1→Global Constraints; R2→T1 step 1 + T2 steps 1-2; R3→T1 step 2 + T2 step 3; R4→T3 step 1 (+PR-1/PR-4); R5→T3 step 1 (`migrate` service + `service_completed_successfully`); R6→T5 step 1 (`just seed`) + runbook §2.4; R7→T3 step 2; R8→T3 steps 3-4 + runbook §2.2/§8 + CI cert step; R9→T2 (build arg) + PR-1; R10→T3 steps 5-6; R11→T4 step 4; R12→T4 step 1; R13→Global Constraints + every task's verify steps; R14→T5 step 2; R15→T5 step 1; R16→T3 step 4 (gitignore) + T5 step 3 (README). Row-14 "backup notes" → runbook §5-6.
- **Placeholder scan:** every file's full content is inline; no "TBD"/"handle errors"/"similar to".
- **Consistency:** image tags `mana-career-{api,worker,frontend}:${TAG:-local}` identical in T3, T4, T5. `migrate` service reused for both migrations and seed. `/nginx-health` defined in T3 nginx.conf, probed in T3 compose healthcheck + T4 smoke. `NEXT_PUBLIC_API_BASE_URL=""` consistent T2/T3/PR-1. `python -m app.seed all` (not `uv run`) consistent T5 + runbook (prod image has `.venv/bin` on PATH).
```
