# Production Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist résumé files across the production API and worker containers, make rate limiting use a client address forwarded only by nginx, and fail startup on known unsafe production secrets.

**Architecture:** Keep the existing local `FileStore` and mount one host directory into API and worker. Split Compose networking into public ingress and private data networks, assign nginx a fixed configurable ingress address, and configure Uvicorn to trust forwarding only from that address. Add production-only JWT secret validation and require an explicit database password in production Compose.

**Tech Stack:** Docker Compose v2, nginx, Uvicorn `ProxyHeadersMiddleware`, FastAPI/Pydantic Settings, pytest, existing `LocalFileStore`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-25-production-runtime-hardening-design.md`

## Global Constraints

- Keep the `FileStore` API and current local-file implementation.
- Do not introduce S3 or another external service in this tranche.
- Preserve the existing API routes and user-visible workflow.
- Keep the backend API unpublished on host ports; nginx remains the public ingress.
- Keep local development Compose behavior unless a separate configuration change is required for parity.
- Production deployments are single-host portfolio deployments as scoped in the existing runbook, not multi-node or HA.
- No database schema migration is required.
- No API endpoint, request, or response changes are expected.
- Do not log secret values or include them in validation errors.
- Never mount a new empty directory over the only copy of existing résumé files; back up and verify any pre-mount copy first.

## Review Focus

- **Missing or blank production `POSTGRES_PASSWORD`:** Compose must fail before creating or starting services; Task 1 tests this with `docker compose config`.
- **Production JWT secret equal to the development sentinel or shorter than 32 characters:** settings construction must fail without echoing the secret, while test/development settings remain usable; Task 1 tests these exact values.
- **Host file directory newly created or owned by the wrong UID:** API upload and worker read must fail visibly rather than use different container-local paths; Task 2 checks UID 10001 writes in the production image and covers shared-root reads.
- **Caller-supplied `X-Forwarded-For` from an untrusted peer:** client identity must remain the socket peer; Task 3 tests trusted and untrusted ASGI peers with spoofed headers.
- **Existing files present before the bind mount is enabled:** rollout must copy and verify them before switching mounts, with a backup available; Task 2 rehearses the documented migration and compares file counts and checksums.

---

## File Map

- `backend/app/core/config.py` — production-only JWT-secret validation.
- `backend/tests/core/test_config.py` — production and non-production secret validation cases.
- `backend/tests/infra/test_prod_compose.py` — resolved Compose contract checks without a running Docker daemon.
- `compose.prod.yml` — explicit DB password, shared file mount, ingress/data networks, fixed nginx address, and Uvicorn forwarded-IP allowlist.
- `.env.example` — blank database password placeholder so a copied example cannot silently use a weak production value.
- `backend/Dockerfile` — create `/app/var/files` with UID 10001 ownership before dropping privileges.
- `backend/tests/infra/test_local_store.py` — shared-root behavior between independent file-store instances.
- `backend/tests/core/test_proxy_headers.py` — trusted-proxy and untrusted-header integration cases.
- `deploy/nginx/nginx.conf` — overwrite forwarded client IP from nginx's socket peer for direct ingress.
- `docs/runbook.md` — safe pre-mount migration, file backup/restore, network overrides, and production environment setup.
- `.github/workflows/ci.yml` — supply CI-only production secrets and validate Compose configuration before building/starting images.
- `scripts/smoke-prod.sh` — exercise an uploaded PDF through the API/worker shared-file path, including a container restart.

### Interfaces

- Settings consumers continue to call `get_settings()` and read `Settings.jwt_secret`; no new settings API is introduced.
- `LocalFileStore` continues to accept a root path and storage key. API and worker both receive `FILE_STORE_LOCAL_DIR=/app/var/files` in the production Compose environment.
- nginx is assigned `NGINX_PROXY_IP` on `PROXY_SUBNET`; Uvicorn trusts exactly `NGINX_PROXY_IP` through `--forwarded-allow-ips`.
- The production smoke continues to run through nginx/TLS and reports failure with the existing `SMOKE FAIL: ...` convention.

## Task 1: Reject known unsafe production secrets

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/core/test_config.py`
- Create: `backend/tests/infra/test_prod_compose.py`
- Modify: `compose.prod.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Existing `Settings.env: Literal["dev", "test", "prod"]` and `Settings.jwt_secret: SecretStr`.
- Produces: `Settings()` raises a Pydantic validation error in prod if the JWT secret is `dev-only-change-me` or has fewer than 32 characters; dev/test retain current behavior. Compose requires nonempty `POSTGRES_PASSWORD`.

- [x] **Step 1: Add failing production secret tests**

In `backend/tests/core/test_config.py`, add:

```python
@pytest.mark.parametrize("secret", ["dev-only-change-me", "x" * 31])
def test_prod_rejects_unsafe_jwt_secret(monkeypatch: pytest.MonkeyPatch, secret: str):
    for key, value in _env(ENV="prod", JWT_SECRET=secret).items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert secret not in str(exc.value)


def test_prod_accepts_32_character_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    secret = "x" * 32
    for key, value in _env(ENV="prod", JWT_SECRET=secret).items():
        monkeypatch.setenv(key, value)
    assert Settings().jwt_secret.get_secret_value() == secret


def test_dev_still_accepts_development_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    for key, value in _env(ENV="dev", JWT_SECRET="dev-only-change-me").items():
        monkeypatch.setenv(key, value)
    assert Settings().jwt_secret.get_secret_value() == "dev-only-change-me"
```

Import `ValidationError` from `pydantic` at the top of the test file.

In the new `backend/tests/infra/test_prod_compose.py`, also add the following Compose helper and negative test. Use a temporary empty interpolation file so a developer's ignored root `.env` cannot satisfy the required value accidentally:

```python
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _compose_config(tmp_path: Path, *, password: str | None) -> subprocess.CompletedProcess[str]:
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    env = os.environ.copy()
    env.pop("POSTGRES_PASSWORD", None)
    if password is not None:
        env["POSTGRES_PASSWORD"] = password
    return subprocess.run(
        ["docker", "compose", "--env-file", str(empty_env), "-f",
         str(ROOT / "compose.prod.yml"), "config", "--format", "json"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )


def test_prod_compose_requires_postgres_password(tmp_path: Path) -> None:
    result = _compose_config(tmp_path, password=None)
    assert result.returncode != 0
    assert "POSTGRES_PASSWORD" in result.stderr
```

- [x] **Step 2: Run the new tests and verify they fail**

Run from `backend/`: `uv run pytest tests/core/test_config.py tests/infra/test_prod_compose.py -q`.
Expected: the new unsafe-secret cases fail because current `Settings` accepts them, and the missing-password test fails because the current Compose file has a fallback; existing tests and the 32-character positive control pass.

- [x] **Step 3: Implement production-only secret validation**

In `backend/app/core/config.py`, import `model_validator` and `Self`, then add:

```python
    @model_validator(mode="after")
    def _validate_production_secrets(self) -> Self:
        if self.env == "prod":
            secret = self.jwt_secret.get_secret_value()
            if secret == "dev-only-change-me" or len(secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be a non-development secret of at least 32 characters"
                )
        return self
```

Do not place the provided value in the error string.

- [x] **Step 4: Require explicit production database credentials**

In `compose.prod.yml`, replace each production `${POSTGRES_PASSWORD:-mana}` fallback (the interpolated `DATABASE_URL` and the Postgres `environment`) with `${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env before starting production}`. In `.env.example`, change `POSTGRES_PASSWORD=mana` to `POSTGRES_PASSWORD=`. Keep development Compose defaults untouched.

In the README production instructions, state that the copied `.env` must contain a nonempty generated `POSTGRES_PASSWORD` and a non-development `JWT_SECRET` with at least 32 characters before production Compose commands run.

- [x] **Step 5: Give the image smoke job explicit CI-only secrets**

In `.github/workflows/ci.yml`, after the image job copies `.env.example`, replace the empty `POSTGRES_PASSWORD` and development JWT sample with CI-only values. Use values that satisfy the new contract, for example `ci-only-postgres-password` and `ci-only-jwt-secret-that-is-never-used-outside-ci`.

- [x] **Step 6: Verify settings and Compose input behavior**

Run from `backend/`: `uv run pytest tests/core/test_config.py tests/infra/test_prod_compose.py -q`.
Expected: all configuration tests pass; the subprocess test proves Compose rejects a missing password before contacting Docker Engine.

- [x] **Step 7: Commit Task 1**

```bash
git add backend/app/core/config.py backend/tests/core/test_config.py backend/tests/infra/test_prod_compose.py compose.prod.yml .env.example README.md .github/workflows/ci.yml
git commit -m "security: reject unsafe production secrets"
```

## Task 2: Share persistent résumé files between API and worker

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `compose.prod.yml`
- Test: `backend/tests/infra/test_local_store.py`
- Modify: `backend/tests/infra/test_prod_compose.py`
- Modify: `docs/runbook.md`

**Interfaces:**
- Consumes: `LocalFileStore(root)` and current `FILE_STORE_LOCAL_DIR` setting.
- Produces: production API and worker both read/write `/app/var/files`, backed by `./backend/var/files` on the host and writable by UID 10001.

- [x] **Step 1: Add a failing production mount contract test**

In `backend/tests/infra/test_prod_compose.py`, add a test that calls `_compose_config(tmp_path, password="ci-only-postgres-password")`, obtains JSON with `docker compose ... config --format json`, and asserts for both services `api` and `worker` that one resolved volume has source `ROOT / "backend" / "var" / "files"` and target `/app/var/files`. Assert the target is identical for both services. Do not assert the entire Compose document so unrelated service changes remain possible.

Also add the existing file-store interface regression to `backend/tests/infra/test_local_store.py`:

```python
async def test_independent_stores_share_files_when_root_is_shared(tmp_path):
    api_store = LocalFileStore(str(tmp_path))
    worker_store = LocalFileStore(str(tmp_path))
    key = "resumes/user/resume.pdf"

    await api_store.put(key, b"%PDF-1.7 shared", content_type="application/pdf")

    assert await worker_store.get(key) == b"%PDF-1.7 shared"
```

- [x] **Step 2: Run the storage test and verify the new case fails for a different root**

Run from `backend/`: `uv run pytest tests/infra/test_local_store.py tests/infra/test_prod_compose.py -q`.
Expected: the LocalFileStore shared-root contract passes and the new production Compose contract fails because neither service has the bind mount yet.

- [x] **Step 3: Create the owned container path**

In the production stage of `backend/Dockerfile`, make the directory explicit before switching users:

```dockerfile
RUN useradd --system --uid 10001 app \
    && mkdir -p /app/var/files \
    && chown -R app /app
```

Keep `USER app` after this instruction.

- [x] **Step 4: Mount one host directory into both services**

In the `api` and `worker` services in `compose.prod.yml`, set `FILE_STORE_LOCAL_DIR=/app/var/files` and add the same bind mount:

```yaml
      - ./backend/var/files:/app/var/files
```

Do not mount résumé storage into `db`, `redis`, `migrate`, `frontend`, or `nginx`. Verify that the top-level `.gitignore` continues to ignore `backend/var/` so uploaded files cannot enter version control; do not change the rule unless it has drifted.

- [x] **Step 5: Document safe migration, backup, and restore**

In `docs/runbook.md`, add a migration subsection before first use of the bind mount: back up the existing deployment, create `backend/var/files` with owner UID/GID 10001 and mode `0700`, copy `/app/var/files` from the old API container before recreating it, compare file counts and SHA-256 checksums, and only then start services with the mount. Keep the old container and backup until verification succeeds.

Update backup and restore to operate on `backend/var/files`, preserve restrictive permissions, and warn that the directory and backups contain résumé PII. State that `docker compose down -v` is not part of a production restore procedure.

- [x] **Step 6: Verify shared storage in isolation**

Run from `backend/`: `uv run pytest tests/infra/test_local_store.py tests/infra/test_prod_compose.py -q`.
Expected: the shared-root contract and resolved Compose mount contract pass, along with traversal and missing-file cases.

- [x] **Step 7: Commit Task 2**

```bash
git add backend/Dockerfile compose.prod.yml backend/tests/infra/test_local_store.py docs/runbook.md
git commit -m "fix(storage): persist shared resume files in production"
```

## Task 3: Trust forwarded client IPs only from nginx

**Files:**
- Modify: `compose.prod.yml`
- Modify: `deploy/nginx/nginx.conf`
- Create: `backend/tests/core/test_proxy_headers.py`
- Modify: `backend/tests/infra/test_prod_compose.py`
- Modify: `docs/runbook.md`

**Interfaces:**
- Consumes: `NGINX_PROXY_IP` and `PROXY_SUBNET` Compose interpolation values.
- Produces: only nginx's fixed ingress IP is trusted by Uvicorn; an untrusted peer cannot set `request.client.host` through forwarded headers.

- [x] **Step 1: Add trusted and untrusted peer tests**

Create `backend/tests/core/test_proxy_headers.py`. Build a minimal Starlette app whose `/peer` endpoint returns `request.client.host`, wrap it in Uvicorn's `ProxyHeadersMiddleware(trusted_hosts="172.30.0.2")`, and send ASGI requests using `httpx.ASGITransport`.

Test these exact cases:

```python
("172.30.0.2", "203.0.113.7", "203.0.113.7")  # nginx peer trusts forwarded client
("172.30.0.3", "198.51.100.9", "172.30.0.3")  # untrusted peer cannot spoof
```

Each tuple is `(transport_peer, x_forwarded_for, expected_request_client_host)`.

- [ ] **Step 2: Run the new proxy tests and verify they fail without proxy middleware**

The trusted/untrusted cases pass with the middleware enabled, but an unwrapped baseline run was not captured. The Compose contract test did show its expected red state before network configuration.

Run from `backend/`: `uv run pytest tests/core/test_proxy_headers.py -q`.
Expected: trusted-peer case fails when the app is unwrapped; after applying `ProxyHeadersMiddleware`, both expected results pass.

- [x] **Step 3: Add isolated Compose networks**

In `compose.prod.yml`, define `data` as a separate bridge network (do not set Docker's `internal: true`, because the ARQ worker must make outbound calls to configured AI providers) and `ingress` as a bridge network with IPAM subnet `${PROXY_SUBNET:-172.30.0.0/24}`. Assign:

- `db`, `redis`, `migrate`, and `worker` to `data` only.
- `frontend` and `nginx` to `ingress` only.
- `api` to both networks.
- `nginx` the fixed `ipv4_address: ${NGINX_PROXY_IP:-172.30.0.2}`.

Set the API command to trust only the same address, for example `--forwarded-allow-ips=${NGINX_PROXY_IP:-172.30.0.2}`. Keep API without a `ports` mapping. Ensure the fixed address is documented as belonging to the subnet, and tell operators to override both values together if the default overlaps another network.

Extend `test_prod_compose.py` to assert that the resolved API joins both `data` and `ingress`, `db` and `redis` join only `data`, `nginx` has the configured fixed ingress address, the API command contains that exact forwarded-IP allowlist, and the API has no published ports.

- [x] **Step 4: Make nginx replace untrusted forwarded chains**

In `deploy/nginx/nginx.conf`, change `X-Forwarded-For` from `$proxy_add_x_forwarded_for` to `$remote_addr`. Keep the adjacent comment explicit that nginx is the direct public ingress in this deployment; an upstream load balancer requires a separately configured trusted-proxy chain.

- [x] **Step 5: Document network and proxy assumptions**

Update the production runbook with the default ingress subnet/IP, the exact relationship between nginx's IP and Uvicorn's allowlist, the API's private host-port status, and the direct-ingress assumption. Explain how to choose a non-overlapping subnet and update both variables. Do not recommend trusting `*` or the full bridge subnet.

- [x] **Step 6: Verify proxy tests and Compose configuration**

Run from `backend/`: `uv run pytest tests/core/test_proxy_headers.py tests/core/test_rate_limit.py tests/infra/test_prod_compose.py -q`.
Expected: both trusted and untrusted identity behavior pass, and rate-limit bucket semantics are unchanged.

From the repository root, run `docker compose -f compose.prod.yml config --quiet` with the CI/test environment from Task 1.
Expected: exit 0. Confirm the resolved config has API on `data` and `ingress`, database and Redis only on `data`, nginx fixed to the configured ingress address, and no API host port.

- [x] **Step 7: Commit Task 3**

```bash
git add compose.prod.yml deploy/nginx/nginx.conf backend/tests/core/test_proxy_headers.py docs/runbook.md
git commit -m "security: trust client forwarding only from nginx"
```

## Task 4: Exercise persistent résumé storage in production smoke and CI

**Files:**
- Modify: `scripts/smoke-prod.sh`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the production Compose stack configured by Tasks 1–3.
- Produces: image CI proves an upload is stored, read by the separate worker, and still readable after API/worker restart.

- [x] **Step 1: Extend the production smoke with an authenticated upload**

In `scripts/smoke-prod.sh`, create a temporary one-page PDF fixture containing no personal data, register a unique test user through `/api/v1/auth/register`, retain the access token, and upload the PDF to `/api/v1/resumes` with `Authorization: Bearer ...`. Save the returned resume and user IDs. Poll `/api/v1/resumes/{id}` at one-second intervals for up to 30 attempts until the worker leaves `uploaded`/`parsing`.

Before upload, assert `docker compose -f compose.prod.yml exec -T api id -u` and the worker's UID both equal `10001`, and that `/app/var/files` is writable in both containers.

The fixture may end in the existing terminal parse-failure state because its content is intentionally minimal. The smoke must reject `file_not_found`, missing file-store errors, timeout, or a status that never becomes terminal.

- [ ] **Step 2: Verify worker visibility and persistence after container replacement**

The smoke script implements the worker-side file read/hash comparison before and after restart. It could not be executed locally because Docker Engine was unavailable; CI execution is pending.

Use the stored user/resume IDs to derive `resumes/{user_id}/{resume_id}.pdf`. Ask the worker container to read that file via `LocalFileStore('/app/var/files')` and print only its byte count and SHA-256. Restart both `api` and `worker` with `docker compose -f compose.prod.yml restart api worker`, wait for readiness, then read and compare the same byte count and hash again. The script must trap cleanup for temporary host files and must not delete the persistent test upload outside its disposable CI environment.

- [ ] **Step 3: Validate Compose inputs and run the full image job**

In `.github/workflows/ci.yml`, ensure the image job seeds nonempty CI-only production settings before calling Compose config/build. Add `docker compose -f compose.prod.yml config --quiet` before image build. Keep the existing Postgres/Redis health checks, Trivy scans, readiness loop, smoke invocation, and `always()` teardown. The CI config validation and production-only CI credentials are implemented, but the image build and end-to-end job remain unverified because Docker Engine is unavailable; leave this step unchecked until CI completes.

- [x] **Step 4: Run available verification**

Run from `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run lint-imports`, `uv run mypy app`, and `uv run pip-audit`.

Run from `frontend/`: `pnpm audit --audit-level=high`, `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm test run`, and `pnpm build`.

Run from the repository root: `docker compose -f compose.prod.yml config --quiet`, then `docker compose -f compose.prod.yml build` and the existing production image CI flow including Trivy scans and `scripts/smoke-prod.sh`. Record unavailable checks without reporting them as passing.

- [x] **Step 5: Commit Task 4**

```bash
git add scripts/smoke-prod.sh .github/workflows/ci.yml
git commit -m "test: cover persistent résumé storage in prod smoke"
```

## Completion Review

- Re-read every requirement in `docs/superpowers/specs/2026-09-25-production-runtime-hardening-design.md` and map it to a task above.
- Review `git diff --check`, Compose resolved service/network/volume relationships, API host-port exposure, secret interpolation, and the data migration steps.
- Confirm all new smoke data is synthetic and isolated to the disposable CI stack.
- The production fake-provider policy is addressed by the Tavily requirement. Keep the separately scoped auth-refresh race, upload-body memory bound, and frontend visual audit in the follow-up queue.


## Execution record

- Task 1 committed as 9a00c88; Task 2 as 62ff7a0; Task 3 as 545e139; Task 4 smoke/CI changes as 1d44355 and 82bfad9. The Next tracing fix remains in the preserved user diff with its untracked regression test.
- Shared-checkout validation: 37 focused backend tests passed; Ruff, mypy (176 files), lint-imports, pip-audit, the focused Next tracing regression (1 test), ash -n scripts/smoke-prod.sh, and git diff --check passed.
- Full backend test run: 249 passed, 3 failed, 241 errors; DB-backed fixtures and eval CLI checks could not reach local Postgres/Redis because the Docker Engine pipe was unavailable. Image build and end-to-end smoke were therefore not executed; CI is configured to run them.
- Additional high-impact work: Tavily live-search adapter and production fake-search rejection committed as 93f4a7b; frontend output tracing fix remains preserved in rontend/next.config.ts.
