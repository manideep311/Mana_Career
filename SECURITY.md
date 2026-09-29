# Security Policy

## Supported versions

Only the `main` branch is supported. Mana Career is a portfolio project — it is
not operated in production at scale, and there are no release branches, tags, or
backports. Fixes land on `main` and nowhere else.

## Reporting a vulnerability

Open an issue on the [`manideep311/Mana_Career`](https://github.com/manideep311/Mana_Career)
repository, or contact the repository owner through GitHub. For a sensitive
report, use GitHub's private vulnerability reporting on the same repository so the
details are not public while a fix is prepared.

There is no dedicated security mailbox and no bug bounty.

## Security posture

Every pointer below is `path:symbol` into `backend/`.

### Authentication

- Passwords are hashed with argon2id via `argon2.PasswordHasher` —
  `app/domain/auth/passwords.py:hash_password` / `verify_password`.
- Sessions are short-lived HS256 access JWTs; `decode_access_token` requires
  `iss`, `aud`, `sub`, `sid`, `jti`, `iat`, `exp` and `type`, and rejects a
  non-`access` token — `app/domain/auth/tokens.py:create_access_token` /
  `decode_access_token`. The default access TTL is 900 s —
  `app/core/config.py:Settings.jwt_access_ttl_seconds`.
- Access tokens die with their sign-in: `sid` names the refresh-token family and
  `get_current_user` rejects a token whose family has no live refresh token, so
  logout, password change and reuse detection end access immediately —
  `app/domain/auth/service.py:AuthService.is_session_live`.
- Refresh tokens rotate on every use under a row lock (`SELECT … FOR UPDATE`).
  A token rotated in the last 15 s while its session is live is a parallel
  refresh (another tab) and gets a sibling token; any later replay is treated as
  theft and revokes the whole family —
  `app/domain/auth/service.py:AuthService.rotate` (`REFRESH_REUSE_GRACE`,
  `_revoke_family`). The web client shares one in-flight refresh across
  concurrent requests and serializes tabs with a Web Lock —
  `frontend/providers/AuthProvider.tsx`.
- Startup fails on a placeholder or development `JWT_SECRET` in any environment
  and, in production, on a secret under 32 characters, an insecure refresh
  cookie, wildcard CORS, or fake providers without `DEMO_MODE` —
  `app/core/config.py:Settings._validate`. `compose.prod.yml` forces `ENV=prod`.

### Authorization & isolation

- `get_current_user` rejects a missing, malformed, forged, expired, or
  wrong-type token with 401; `get_current_admin` returns 403 for a non-admin —
  `app/api/deps.py:get_current_user` / `get_current_admin`.
- Every user-scoped service filters `user_id == current_user.id` and raises
  `NotFoundError` → HTTP 404 (never 403 — no existence leak) for a non-owner —
  `app/domain/applications/service.py:ApplicationService.get`,
  `app/domain/roadmap/service.py:RoadmapService.get`,
  `app/domain/matching/service.py:MatchService.get`.
- Shared/seed rows are read via `user_id IS NULL` —
  `app/domain/matching/service.py:MatchService._visible_ready_job_id`.

### Outbound actions

- The LangGraph agent calls `interrupt()` at `human_approval` and waits for a
  person before any send — `app/domain/agents/nodes/human_approval.py:human_approval`.
- `email_external_action` re-builds and re-hashes the approval snapshot against
  the current rows and halts without sending on any mismatch —
  `app/domain/agents/nodes/email_external_action.py:email_external_action`. Its
  only graph predecessor is `human_approval` —
  `app/domain/agents/graph.py:build_graph`.
- Email is console-only; no configuration wires a real outbound sender —
  `app/domain/email/sender.py:ConsoleEmailSender`,
  `app/domain/email/factory.py:get_email_sender`.
- Status changes, sends, and approvals are written to `audit_logs` —
  `app/core/audit.py:audit`.

### Transport & headers

- nginx sends HSTS, a same-origin Content-Security-Policy, `X-Frame-Options:
  DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` and
  `Permissions-Policy` on every HTTPS response, and hides nginx/framework
  versions — `deploy/nginx/nginx.conf` (checked by
  `tests/infra/test_nginx_conf.py` and the production smoke).
- The OpenAPI schema and Swagger/ReDoc UIs are not served when `ENV=prod` —
  `app/main.py:create_app`.

### Secrets & logging

- Secrets are read from the environment via `pydantic-settings`; `jwt_secret`
  and the provider API keys are `SecretStr` — `app/core/config.py:Settings`.
- A structlog processor redacts sensitive keys and secret-shaped values
  (`sk-`, `Bearer`, long hex, JWT triplet, `$argon2`, `://user:pass@`) from
  every log line — `app/core/logging.py:redact_secrets` (`SECRET_KEYS`,
  `SECRET_PATTERN`).

### Supply chain

- CI gates on `pip-audit` (backend), `pnpm audit --audit-level=high`
  (frontend) and Trivy HIGH/CRITICAL scans of all three production images —
  `.github/workflows/ci.yml`. Actions are pinned to commit SHAs with a
  read-only token; Dependabot proposes weekly updates — `.github/dependabot.yml`.
- `ruff`'s `S` (flake8-bandit) rules run in the lint gate —
  `backend/pyproject.toml` (`[tool.ruff.lint] select`).

### Abuse limits

- Per-IP fixed-window rate limits (auth 10/min; model work 60/h; uploads
  20/h). Counters are incremented and expired atomically in Redis, and only
  requests that start model work spend the LLM budget —
  `app/core/rate_limit.py:RateLimitMiddleware` (`_FIXED_WINDOW`, `_bucket`).
  `CF-Connecting-IP` is honoured only from `TRUSTED_PROXY_CIDRS` —
  `app/core/client_ip.py:client_ip`.
- Request bodies are capped while they stream (1 MiB; résumé uploads 10 MiB +
  multipart framing), with or without `Content-Length` and without relying on
  nginx — `app/core/body_limit.py:BodySizeLimitMiddleware`.
- Agent runs are bounded by a step budget (`max_steps`; halts with
  `budget_exceeded`). Background jobs retry transient errors via ARQ's `Retry`
  with backoff, at most three attempts, then record an explicit failure; a cron
  sweeper fails anything stranded in progress —
  `app/domain/agents/budget.py:check_budget` / `guard`,
  `app/worker/retry.py:retry_or_fail`, `app/worker/tasks/sweeper.py:sweep_stuck_jobs`.

See `docs/threat-model.md` for the threat / vector / mitigation / residual-risk
breakdown and the explicit out-of-scope list.
