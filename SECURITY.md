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
- Sessions are short-lived HS256 access JWTs; `decode_access_token` requires the
  `exp`, `sub`, and `type` claims and rejects a non-`access` token —
  `app/domain/auth/tokens.py:create_access_token` / `decode_access_token`. The
  default access TTL is 900 s — `app/core/config.py:Settings.jwt_access_ttl_seconds`.
- Refresh tokens rotate on every use; presenting an already-rotated token is
  treated as a compromised family and revokes every token in that family —
  `app/domain/auth/service.py:AuthService.rotate` (`_revoke_family`).

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

### Secrets & logging

- Secrets are read from the environment via `pydantic-settings`; `jwt_secret`
  and the provider API keys are `SecretStr` — `app/core/config.py:Settings`.
- A structlog processor redacts sensitive keys and secret-shaped values
  (`sk-`, `Bearer`, long hex, JWT triplet, `$argon2`, `://user:pass@`) from
  every log line — `app/core/logging.py:redact_secrets` (`SECRET_KEYS`,
  `SECRET_PATTERN`).

### Supply chain

- CI gates on `pip-audit` (backend) and `pnpm audit --audit-level=high`
  (frontend) — `.github/workflows/ci.yml`.
- `ruff`'s `S` (flake8-bandit) rules run in the lint gate —
  `backend/pyproject.toml` (`[tool.ruff.lint] select`).

### Abuse limits

- Per-IP fixed-window rate limit on auth endpoints (10/min) —
  `app/core/rate_limit.py:RateLimitMiddleware` (`AUTH_LIMIT_PER_MINUTE`).
- Agent runs are bounded by a step budget (`max_steps`; halts with
  `budget_exceeded`) and an ARQ retry cap (`MAX_TRIES = 3`, then a terminal
  `error` finalize) — `app/domain/agents/budget.py:check_budget` / `guard`,
  `app/worker/tasks/agent.py:_run_or_resume`,
  `app/worker/tasks/resume.py:MAX_TRIES`.

See `docs/threat-model.md` for the threat / vector / mitigation / residual-risk
breakdown and the explicit out-of-scope list.
