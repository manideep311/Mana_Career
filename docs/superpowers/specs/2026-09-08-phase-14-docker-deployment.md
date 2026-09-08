# Phase 14 — Docker + deployment design addendum

> Delta over master `2026-08-30-mana-career-design.md` §8 (folder structure — `compose.prod.yml`, `docs/runbook.md`) and §9 row 14. Phases 0–13 shipped the full product plus the security suite (`main@1eb0e38`, CI-green). This phase is **packaging only**: production multi-stage image targets, a `compose.prod.yml` that brings the whole stack up behind nginx/TLS with healthcheck-gated ordering, a migration one-shot, the (already-written) seed command wired in, a complete `.env.example`, a deployment runbook with backup/restore/rollback, and container image scanning in CI.

## 0. Goal (roadmap row 14)

"One-command bring-up." Master success criterion, verbatim: **clean machine: `docker compose -f compose.prod.yml up` → smoke passes.** That check runs in CI (a new `images` job) because it needs a Docker daemon; the dev box does not have one running.

## 1. What already exists — do NOT rebuild, WIRE it

- **`docker-compose.yml`** (repo root) — dev stack: `db` (pgvector/pg16), `redis`, `api`/`worker`/`frontend` all built `target: dev` with source bind-mounts + `--reload`/`pnpm dev`. Untouched by this phase.
- **`backend/Dockerfile`** — `base` (python:3.12-slim + `uv`) and `dev` stages only. `dev` is referenced by `docker-compose.yml` — **must stay byte-intact**.
- **`frontend/Dockerfile`** — `base` (node:20-slim + corepack) and `dev` stages only. `dev` referenced by `docker-compose.yml` — **must stay byte-intact**.
- **`.dockerignore`** (repo root) — covers `__pycache__`, `.venv`, `node_modules`, `.next`, caches, `.git`.
- **`.env.example`** + **`backend/.env.example`** — identical dev-flavoured files (`ENV=dev`, `JWT_SECRET=dev-only-change-me`, `LLM_PROVIDER=fake`, `EMBEDDINGS_PROVIDER=fake`).
- **`app/seed.py`** — has a working `if __name__ == "__main__"` CLI: `python -m app.seed {skills|jobs|learning|all}`. Opens its own `AsyncSessionLocal`, commits. **No new seed code — just call it from the runbook + a `just` target.**
- **`app/api/v1/health.py`** — `GET /health` → `{"status":"ok"}`; `GET /health/ready` → 200/503 with `checks: {database, redis, migrations}` (the last asserts a row in `alembic_version`). Mounted at both `/api/v1/health*` and root `/health*` (`main.py:53`). This is the container healthcheck target.
- **`alembic/env.py`** — reads `get_settings().database_url`; `uv run alembic upgrade head` is the migrate command. `uv` is present in the `base` image layer, so the prod target keeps it.
- **`app/worker/main.py:WorkerSettings`** — `uv run arq app.worker.main.WorkerSettings` is the worker command.
- **`next.config.ts`** — `output: "standalone"` already set → `.next/standalone/server.js` is the runner entrypoint.
- **`lib/env.ts`** — `export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"`. `NEXT_PUBLIC_*` is inlined **at build time**. An explicit empty string survives the `??` (only `undefined` triggers the fallback), and `"" + "/api/v1/x"` === `"/api/v1/x"` (same-origin relative). No frontend code change needed.
- **`.github/workflows/ci.yml`** — 3 jobs (`backend`, `eval`, `frontend`). Phase 13 added `pip-audit` / `pnpm audit --audit-level=high` and a `--cov-fail-under=80` floor.
- **`justfile`** — `up`/`down`/`migrate`/`ci`/`smoke` targets. `scripts/smoke.sh` curls dev ports 8000/3000 directly.

## 2. Rulings

**R1 — one cohesive phase, no a/b split.** Every deliverable is infra config or docs. The only tracked *code* files touched are `.env.example` / `backend/.env.example` (documentation) and the two Dockerfiles (additive stages + a base-image bump). No `app/**` or `frontend/{app,lib,components}/**` logic changes. No new tests in `backend/tests/` or `frontend/tests/` — validation is `docker compose config`, shell `bash -n`, and the CI `images` job.

**R2 — production image targets; dev targets frozen.**

- **`backend/Dockerfile`** — append a `prod` stage `FROM base`:
  - `COPY pyproject.toml uv.lock ./` → `RUN uv sync --frozen --no-install-project --no-dev` (cached dep layer) → `COPY . .` → `RUN uv sync --frozen --no-dev`.
  - `RUN useradd --system --uid 10001 app && chown -R app /app` → `USER app`.
  - `ENV ENV=prod`.
  - `EXPOSE 8000`.
  - `CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]` — no `--reload`.
  - The existing `base` and `dev` stages are copied through unchanged.
- **`frontend/Dockerfile`** — bump `base` to `FROM node:22-slim` (CI uses node 22; the image must match), then append:
  - `deps` stage `FROM base`: `RUN corepack prepare pnpm@11 --activate`; `COPY package.json pnpm-lock.yaml* ./`; `RUN pnpm install --frozen-lockfile`.
  - `builder` stage `FROM deps`: `COPY . .`; `ARG NEXT_PUBLIC_API_BASE_URL=""`; `ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL`; `RUN pnpm build`.
  - `runner` stage `FROM node:22-slim`: `ENV NODE_ENV=production`; `RUN useradd --system --uid 10001 app`; `WORKDIR /app`; `COPY --from=builder --chown=app /app/.next/standalone ./`; `COPY --from=builder --chown=app /app/.next/static ./.next/static`; `COPY --from=builder --chown=app /app/public ./public`; `USER app`; `EXPOSE 3000`; `CMD ["node", "server.js"]`.
  - The existing `dev` stage stays; it now sits on node:22 (verified low-risk — dev stage only runs `pnpm dev`).

  *Ruling within R2:* `NEXT_PUBLIC_API_BASE_URL` default is `""` (empty) so the shipped client bundle calls same-origin relative paths and nginx routes them — **no prod CORS dependency**. `CORS_ORIGINS` is still set in prod `.env` as defense-in-depth.

**R3 — per-build-context `.dockerignore`.** The root `.dockerignore` only applies to a root-context build; `compose.prod.yml` builds with `context: ./backend` and `context: ./frontend`. Create **`backend/.dockerignore`** (`__pycache__`, `.venv`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `var/`, `tests/`, `.env`, `*.md` except none needed, `alembic/versions/__pycache__`) and **`frontend/.dockerignore`** (`node_modules`, `.next`, `coverage`, `.env*`, `tests/`, `*.tsbuildinfo`). Keep the root `.dockerignore` as-is.

**R4 — `compose.prod.yml` at repo root.** Services, all with `env_file: [.env]`, no source bind-mounts anywhere, each buildable service carrying **both** `build:` and `image: mana-career-<svc>:${TAG:-local}` (stable ref for Trivy + `TAG` swap for rollback):

| service | image / build | command | depends_on | ports | restart | healthcheck |
|---|---|---|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | — | — | none (internal only) | `unless-stopped` | `pg_isready -U $POSTGRES_USER` |
| `redis` | `redis:7-alpine` | — | — | none | `unless-stopped` | `redis-cli ping` |
| `migrate` | `mana-career-api` / `./backend` target `prod` | `uv run alembic upgrade head` | `db: service_healthy` | none | `"no"` | — |
| `api` | `mana-career-api` (same image as migrate) | *(image default CMD)* | `migrate: service_completed_successfully`, `db: service_healthy`, `redis: service_healthy` | none (nginx fronts it) | `unless-stopped` | `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/ready').status==200 else 1)"` |
| `worker` | `mana-career-worker` / `./backend` target `prod` | `uv run arq app.worker.main.WorkerSettings` | same as `api` | none | `unless-stopped` | — |
| `frontend` | `mana-career-frontend` / `./frontend` target `runner` | *(image default CMD)* | `api: service_healthy` | none | `unless-stopped` | `node -e "require('http').get('http://localhost:3000',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"` |
| `nginx` | `nginx:1.27-alpine` | — | `api: service_healthy`, `frontend: service_healthy` | `80:80`, `443:443` | `unless-stopped` | `wget -qO- http://localhost/health \|\| exit 1` |

- `db` mounts a named volume `pgdata:/var/lib/postgresql/data`. No `init-test-db.sh` mount (that is dev/CI only — prod has no `mana_test`).
- `nginx` bind-mounts `./deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro` and `./deploy/nginx/certs:/etc/nginx/certs:ro`.
- `api`/`worker` share **one** built image (`mana-career-api`); `worker`'s `build:` block is identical so `docker compose build` is happy, but they resolve to the same tag. *Ruling:* give `worker` its own `image: mana-career-worker:${TAG:-local}` and its own identical `build:` — clearer for Trivy output and rollback, costs one extra ~0-byte image layer reuse (Docker dedupes identical layers).
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` come from `.env`; `DATABASE_URL` / `REDIS_URL` are set in each service's `environment:` block pointing at `db` / `redis` service names (mirrors the dev compose).
- **Every `${VAR}` interpolation in `compose.prod.yml` uses a `:-` default** (`${POSTGRES_USER:-mana}`, `${POSTGRES_PASSWORD:-mana}`, `${POSTGRES_DB:-mana}`, `${TAG:-local}`, `${NEXT_PUBLIC_API_BASE_URL:-}`) so `docker compose -f compose.prod.yml config -q` validates with no env file at all (the R13 local gate) and CI needs no pre-seeded values. The `.env` file overrides these for a real deploy.

**R5 — migration entrypoint = the `migrate` one-shot + `service_completed_successfully`.** Not an inline `sh -c "alembic ... && uvicorn ..."` (keeps `api`'s process tree a single supervised process), not a baked `ENTRYPOINT` wrapper (keeps the image command declarative and lets ops re-run migrations without restarting `api`). Manual upgrade path: `docker compose -f compose.prod.yml run --rm migrate`. `api` and `worker` both gate on `migrate` finishing 0.

**R6 — seed = documented one-shot, zero new code.** `docker compose -f compose.prod.yml run --rm migrate uv run python -m app.seed all` (the `migrate` service already carries the prod image + `.env` + a `db` dependency; override its command). Add `just seed`. The runbook's "first boot" sequence is: `up -d db redis` → `run --rm migrate` → `run --rm migrate uv run python -m app.seed all` → `up -d`.

**R7 — nginx reverse proxy (`deploy/nginx/nginx.conf`).** One `http {}` with:

- `upstream api { server api:8000; }`, `upstream web { server frontend:3000; }`.
- `server { listen 80; ... return 301 https://$host$request_uri; }`.
- `server { listen 443 ssl; http2 on; ssl_certificate /etc/nginx/certs/fullchain.pem; ssl_certificate_key /etc/nginx/certs/privkey.pem; }` containing:
  - `client_max_body_size 12m;` (résumé upload cap is 10 MiB — `resume_max_bytes`).
  - `gzip on;` for text types.
  - `location = /health` and `location = /health/ready` → `proxy_pass http://api;`.
  - `location /api/ { proxy_pass http://api; proxy_http_version 1.1; proxy_set_header Connection ""; proxy_buffering off; proxy_read_timeout 3600s; }` — `proxy_buffering off` + long read timeout are **required** for the SSE endpoints (`/api/v1/jobs/*/events`, `/roadmaps/*/events`, agent run streams).
  - `location / { proxy_pass http://web; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }` (Next.js HMR is dev-only but the upgrade headers are harmless in prod).
  - Common `proxy_set_header` block on all: `Host $host`, `X-Real-IP $remote_addr`, `X-Forwarded-For $proxy_add_x_forwarded_for`, `X-Forwarded-Proto $scheme`, `X-Request-ID $request_id` (nginx generates one if absent; the app's `RequestIDMiddleware` honours an inbound `X-Request-ID`).

**R8 — TLS: self-signed by default.** `deploy/nginx/certs/` is gitignored except a tracked `.gitkeep`. The runbook carries the generator:
```
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout deploy/nginx/certs/privkey.pem \
  -out deploy/nginx/certs/fullchain.pem \
  -subj "/CN=localhost"
```
plus a "replace with Let's Encrypt / your CA's chain — keep the same two filenames" note. No certbot/ACME container (single-tenant portfolio scope). The CI `images` job generates a throwaway self-signed pair before `up`.

**R9 — frontend build arg wiring.** `compose.prod.yml`'s `frontend.build` passes `args: { NEXT_PUBLIC_API_BASE_URL: "${NEXT_PUBLIC_API_BASE_URL:-}" }`. Default empty → same-origin. `.env.example` documents that leaving it empty is correct for the nginx-fronted single-origin deploy, and that setting it to an absolute URL is only for a split-origin deploy (which then also needs `CORS_ORIGINS`).

**R10 — one complete `.env.example`, dev-working, prod documented as comments.** Master §8 lists only `.env.example`; row 14 says "complete `.env.example`". The file stays **live dev config** — `cp .env.example .env` gives a working offline stack (fakes, `dev-only-change-me`) and that is exactly what the CI `images` smoke consumes. Changes:
- Add the **compose-only** vars (not read by `Settings`, needed for `compose.prod.yml` interpolation) as *live, uncommented* lines with dev-safe values: `POSTGRES_USER=mana`, `POSTGRES_PASSWORD=mana`, `POSTGRES_DB=mana`, `TAG=local`.
- Append a trailing reference block of **commented** lines (no duplicate live keys — nothing here is parsed):
```
# ==================== PRODUCTION — change these before deploying ====================
# ENV=prod
# CORS_ORIGINS=https://your-domain.example      # or leave dev value if single-origin behind nginx
# JWT_SECRET=                                    # generate: openssl rand -hex 32
# REFRESH_COOKIE_SECURE=true
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=
# EMBEDDINGS_PROVIDER=voyage
# VOYAGE_API_KEY=
# NEXT_PUBLIC_API_BASE_URL=                      # leave EMPTY for the nginx single-origin deploy
# POSTGRES_PASSWORD=                             # a real secret
```
`backend/.env.example` stays dev-only with a one-line pointer comment: `# For production values see the root .env.example`.

**R11 — CI `images` job (container scanning + the master's bring-up check).** New 4th job in `ci.yml`, `runs-on: ubuntu-latest`, on `push` + `pull_request` like the rest:

1. `actions/checkout@v4`; `docker/setup-buildx-action@v3`.
2. `cp .env.example .env` (dev defaults are a valid prod-shaped config for the smoke — fakes, self-signed).
3. `mkdir -p deploy/nginx/certs && openssl req -x509 -newkey rsa:2048 -nodes -days 1 -keyout deploy/nginx/certs/privkey.pem -out deploy/nginx/certs/fullchain.pem -subj "/CN=localhost"`.
4. `docker compose -f compose.prod.yml build` (buildx, `--build-arg NEXT_PUBLIC_API_BASE_URL=` via compose).
5. Trivy — `aquasecurity/trivy-action@0.24.0` per image (`mana-career-api:local`, `mana-career-worker:local`, `mana-career-frontend:local`) with `severity: HIGH,CRITICAL`, `ignore-unfixed: true`, `exit-code: 1`. `ignore-unfixed: true` is the sanctioned escape hatch (identical philosophy to Phase 13's `pip-audit` / `pnpm audit` gates — a HIGH/CRITICAL **with a fix available** fails the build; no `|| true`).
6. `docker compose -f compose.prod.yml up -d`; poll `https://localhost/health/ready` (`-k`) up to 90s.
7. `scripts/smoke-prod.sh`.
8. `if: failure()` → `docker compose -f compose.prod.yml logs --no-color`.
9. `if: always()` → `docker compose -f compose.prod.yml down -v`.

**R12 — `scripts/smoke-prod.sh`** (new; `scripts/smoke.sh` stays as the dev/plain-http check). `set -euo pipefail`; against `https://localhost` with `curl -fsSk`:
- `/health` body contains `"status":"ok"`.
- `/health/ready` → HTTP 200.
- `/` → HTTP 200 (Next.js standalone through nginx).
- `/api/openapi.json` → HTTP 200 (API reachable through the `/api/` location).
- `http://localhost/` (port 80) → HTTP 301 with a `https://` Location.
Prints `SMOKE OK`.

**R13 — local gates for this phase.** The dev box has the Docker CLI but no running daemon and no Trivy (parity with the standing "no local Postgres/Redis → those tests are CI-only" rule). Per-task local verification is:
- `docker compose -f compose.prod.yml --env-file .env.example config -q` — parses, interpolates, schema-validates the merged compose; **no daemon needed**; non-zero on any error.
- `bash -n scripts/smoke-prod.sh` and `bash -n` on any other shell touched.
- Dockerfile review against the hadolint rule set by eye (pinned bases ✓, no `apt-get` without `--no-install-recommends` + cache clean, `USER` set, no secrets in `ARG`/`ENV`).
- `just ci` (backend ruff + lint-imports + mypy + pytest-collect + pure suites; frontend lint + tsc + vitest) stays green — proves the `.env.example` / Dockerfile edits didn't disturb anything importable.
The authoritative build + Trivy + bring-up + smoke is the CI `images` job.

**R14 — `docs/runbook.md`** (master §8 path; "deploy doc" in row 14 is the same artifact — one file, not two). Sections: Prerequisites (Docker Engine + compose v2, a domain/DNS or `localhost`) · First boot (`.env` from `.env.example` + the exact vars to change, cert generation, `up -d db redis` → `run --rm migrate` → seed → `up -d`) · Verifying (`smoke-prod.sh`, `/health/ready` JSON, `docker compose ps`) · Operations (viewing logs, restarting one service, `run --rm migrate` for a later migration) · **Backup** (`docker compose -f compose.prod.yml exec -T db pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > backup-$(date +%F).sql.gz`; a cron example; note the `pgdata` volume and `backend/var/files` for uploaded résumés) · **Restore** (`gunzip -c … | docker compose exec -T db psql …`) · **Upgrade** (`git pull` → `docker compose -f compose.prod.yml build` → `run --rm migrate` → `up -d`) · **Rollback** (set `TAG=` to the previous build, `alembic downgrade -1` via `run --rm migrate uv run alembic downgrade <rev>`, `up -d`) · Teardown (`down` vs `down -v`) · TLS (swapping self-signed for real certs) · Out-of-scope pointer (registry push, secret managers, HA — see §3).

**R15 — `justfile` prod targets.** Add `prod-up` (`docker compose -f compose.prod.yml up -d --build`), `prod-down` (`docker compose -f compose.prod.yml down`), `prod-logs` (`docker compose -f compose.prod.yml logs -f`), `seed` (`docker compose -f compose.prod.yml run --rm migrate uv run python -m app.seed all`), `smoke-prod` (`./scripts/smoke-prod.sh`). Keep every existing target.

**R16 — docs touch-ups.** `.gitignore`: add `deploy/nginx/certs/*` + `!deploy/nginx/certs/.gitkeep`. `README.md` "Running it": add a short **Production** paragraph pointing at `compose.prod.yml` and `docs/runbook.md`. The Status table's row 14 flips to done in the **closeout**, not during implementation.

## 3. Out of scope

Kubernetes / Helm / Nomad. Cloud IaC (Terraform, Pulumi, CloudFormation). Managed Postgres / ElastiCache / a CDN. Certbot / ACME automation (self-signed default + a documented filename-compatible swap). Multi-node, replicas, HA, blue-green. Secret managers (Vault, SSM, Doppler) — the `.env` file is the mechanism; the runbook names the upgrade path. Log shipping / APM / a metrics stack — structlog-to-stdout is the boundary; the runbook points at `docker compose logs`. Publishing images to a registry — `TAG` + local `build` only; the runbook notes `docker push`. Wiring the S3 `FileStore` adapter — prod runs `FILE_STORE=local` on a bind-mounted `backend/var/files`; the adapter exists, bucket provisioning is deploy-environment-specific. Load / soak testing (still deferred from Phase 13's residual-risk note). Any `app/**` or `frontend/**` behavioural change.

## 4. File manifest

**Create**
- `compose.prod.yml`
- `backend/.dockerignore`
- `frontend/.dockerignore`
- `deploy/nginx/nginx.conf`
- `deploy/nginx/certs/.gitkeep`
- `scripts/smoke-prod.sh`
- `docs/runbook.md`

**Modify**
- `backend/Dockerfile` — append `prod` stage; `base`/`dev` unchanged
- `frontend/Dockerfile` — `base` → node:22-slim; append `deps`/`builder`/`runner`; `dev` otherwise unchanged
- `.env.example` — append the `PRODUCTION` block + compose-only vars
- `backend/.env.example` — one-line pointer comment to the root file
- `.gitignore` — `deploy/nginx/certs/*` + `!deploy/nginx/certs/.gitkeep`
- `.github/workflows/ci.yml` — new `images` job
- `justfile` — `prod-up` / `prod-down` / `prod-logs` / `seed` / `smoke-prod`
- `README.md` — Production paragraph (Status row 14 at closeout)
