# Threat model

Mana Career is a single-tenant portfolio application. The assets worth
protecting are: **résumé PII and career-profile data** (work history, contact
details, salary expectations) held per user; the **JWT signing secret and
refresh-token material** that gate every session; and the **LLM prompt surface**
— job descriptions, résumé text, and retrieved web content that flow into model
prompts and could carry injected instructions.

The mitigations below are all in code on `main`, and every row points at the
symbol that enforces it. This is a STRIDE-lite pass, not an exhaustive review.

## Threats

| Threat | Vector | Mitigation (in code) | Residual risk |
| --- | --- | --- | --- |
| Résumé PII / career-profile disclosure | At rest, in structured logs, or forwarded into an LLM prompt | Per-user row filter raising `NotFoundError` → HTTP 404 (`app/domain/applications/service.py:ApplicationService.get`, `app/domain/roadmap/service.py:RoadmapService.get`, `app/domain/matching/service.py:MatchService.get`); `redact_secrets` structlog processor (`app/core/logging.py:redact_secrets`); the demo runs the fake LLM provider (`app/core/config.py:Settings.llm_provider` default `fake`) | A real LLM provider, once configured, receives résumé text on a user-initiated tailoring action — documented and user-consented |
| Prompt injection via JD / résumé / retrieved content | Attacker-controlled free text reaches a model prompt (job description, résumé section, RAG chunk) | Deterministic scorer reads no instructions — token overlap only (`app/domain/matching/scorer.py:score`); `ClaimValidator` drops or re-prompts any generated line that does not overlap a real source span (`app/domain/resume/tailoring.py:ClaimValidator`, `tailor_resume`); RAG wraps retrieved text in `<untrusted_data>` fences and neutralizes nested tags (`app/domain/rag/context.py:_render_block`, `_neutralize`) | A crafted JD could still nudge an LLM narrator's tone (`app/domain/matching/explainer.py:MatchExplainer`) — low impact, no action taken |
| Approval-gate bypass | Forcing the agent graph to the send node, or altering the payload after review | `human_approval` calls `interrupt()` — a server-side pause (`app/domain/agents/nodes/human_approval.py:human_approval`); `email_external_action` re-builds and re-hashes the snapshot and halts on mismatch (`app/domain/agents/nodes/email_external_action.py:email_external_action`); the only graph edge into the send node comes from `human_approval` (`app/domain/agents/graph.py:build_graph`) | None identified |
| Cross-user access | Guessing or replaying another user's resource id | Every user-scoped query filters `user_id == current_user.id` and raises `NotFoundError` → 404 (never 403 — no existence leak); shared rows use `user_id IS NULL` (`app/domain/matching/service.py:MatchService._visible_ready_job_id`); proven by `backend/tests/security/test_tenant_isolation.py` (19 tests across 8 resources) | None identified |
| Refresh-token theft | Token exfiltrated from client storage or transport | Refresh tokens rotate on every use; presenting an already-rotated token revokes the whole family (`app/domain/auth/service.py:AuthService.rotate`); short access-token TTL, default 900 s (`app/core/config.py:Settings.jwt_access_ttl_seconds`) | A stolen *access* token stays valid until its `exp` (minutes) |
| Secret leakage to logs | A token, password, DSN, or key passed through a structlog event | `redact_secrets` masks known sensitive keys and secret-shaped values — `sk-`, `Bearer`, long hex, JWT triplet, `$argon2`, `://user:pass@` (`app/core/logging.py:redact_secrets`, `SECRET_KEYS`, `SECRET_PATTERN`); `backend/tests/security/test_secret_redaction.py` fails CI if the configured `JWT_SECRET` reaches stdout | A novel secret shape the pattern does not match |
| Denial of service / cost blow-up | Auth-endpoint flooding; an agent run that loops or retries without bound | Per-IP fixed-window limit on auth endpoints, 10/min (`app/core/rate_limit.py:RateLimitMiddleware`, `AUTH_LIMIT_PER_MINUTE`); agent step budget halts the run at `max_steps` with `budget_exceeded` (`app/domain/agents/budget.py:check_budget`, `guard`); ARQ retry cap `MAX_TRIES = 3` then a terminal `error` finalize (`app/worker/tasks/agent.py:_run_or_resume`, `app/worker/tasks/resume.py:MAX_TRIES`); proven by `backend/tests/security/test_agent_limits.py` | No global request rate limit and no LLM spend cap — load/soak smoke is deferred (see Out of scope) |

## Out of scope

- No WAF or edge DDoS protection.
- No SSO / OAuth / social login — local password authentication only.
- No external penetration test and no bug bounty / formal disclosure process.
- Single-tenant: no organizations, teams, or shared workspaces.
- Container image scanning lands with Phase 14 (Docker).
- Load / soak testing (the master plan's "load smoke" — a `locust` / `k6`
  harness) is deferred.
