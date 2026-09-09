# Mana Career

**Your career. Your next move. Smarter with AI.**

A human-first AI career agent. Mana Career parses your résumé into a structured career
profile, lets you ingest job descriptions, computes an **explainable** résumé↔job match
score, finds your skill gaps, builds a grounded learning roadmap, tailors résumés and
drafts cover letters + application emails, and — through the **Mana AI** agent — prepares
complete applications that **you review and approve before anything is sent**.

> AI recommends → AI prepares → **Human decides.**

The full system design is in
[`docs/superpowers/specs/2026-08-30-mana-career-design.md`](docs/superpowers/specs/2026-08-30-mana-career-design.md);
implementation follows the 14-phase roadmap in §9.

## Status

**All 14 roadmap phases are complete and CI-green on `main`** (backend + `eval` +
frontend + `images` jobs; ~170 backend tests against real Postgres + Redis,
including a `tests/security/` suite; ~88% coverage; `pip-audit` + `pnpm audit` +
Trivy image scans gate every push).

| Phase | Scope | State |
|---|---|---|
| **0 — Foundations** | monorepo, `core/` (config, logging, `problem+json` errors, async DB + `Repository`, append-only audit log, Redis rate limiting), Alembic bootstrap, app factory + health, ARQ worker, swappable LLM/embeddings seams, dev Docker Compose, Next.js shell + tokens, CI | ✅ |
| **1 — Auth + career profile + shell** | argon2id + HS256 access JWT + rotating refresh with family reuse-detection; `career_profiles` + sub-entities + deterministic strength scorer; design system + auth/profile UI | ✅ |
| **2–3 — Résumé → profile** | PDF parsing, structured extraction, profile generation | ✅ |
| **4–5 — Jobs + matching** | job ingestion + search; deterministic, explainable résumé↔job scorer with per-dimension breakdown + skill gaps | ✅ |
| **6 — RAG** | pgvector retrieval, chunking, `<untrusted_data>`-fenced context assembly | ✅ |
| **7 — Mana AI agent** | LangGraph agent (SSE-streamed), block registry, Activity feed | ✅ |
| **8–9 — Tailoring + letters** | grounded résumé tailoring with a claim validator; cover-letter + application-email drafting | ✅ |
| **10 — Human-approval workflow** | `interrupt()`-gated send, sha256 payload re-verification, `ConsoleEmailSender`, approval UI | ✅ |
| **11 — Application tracker** | append-only `application_events`, status board + timeline UI | ✅ |
| **12 — Career insights + roadmap** | aggregate skill-gap rollup, grounded learning roadmap (streamed), insights + next-best-action | ✅ |
| **13 — Testing + security hardening** | `tests/security/` (tenant isolation, authz, secret redaction, prompt injection, agent limits); `SECURITY.md`; `docs/threat-model.md`; audit + coverage gates | ✅ |
| **14 — Docker + deployment** | multi-stage prod images, `compose.prod.yml` behind nginx/TLS, migrate one-shot, healthcheck-gated startup, seed command, `docs/runbook.md`, Trivy CI scan | ✅ |

Phase specs, plans, and completion reports: [`docs/superpowers/specs/`](docs/superpowers/specs/) · [`docs/superpowers/plans/`](docs/superpowers/plans/).

## What works today

A running API where a user can:

- **Register / log in / refresh / log out / change password** — access tokens are short-lived
  JWTs; the refresh token is an httpOnly `SameSite=Strict` cookie, stored only as a hash, and
  rotates on every use. Presenting an already-rotated token revokes the whole session family.
- **Build a career profile** — one profile per account, auto-created on first read, with
  contact links, job preferences, salary expectations, seniority, goals, and ordered lists of
  work experience, education, projects, and certifications.
- **See a profile-strength score** — a deterministic 0–100 score with a per-section
  completeness map and a plain-language list of what's still missing, recomputed on every edit.

…and, on top of that foundation, the full flow: **résumé upload → structured profile →
explainable job matching → skill gaps → grounded learning roadmap → résumé/cover-letter
tailoring → application prep → human-approval-gated email → application tracking → career
insights** — driven end to end by the **Mana AI** agent, with a human approving every
outbound action.

Every state change and auth event is written to an append-only `audit_logs` table. Every
request carries an `X-Request-ID`; errors are RFC 9457 `application/problem+json` with stable
machine codes. Module boundaries are enforced by `import-linter`.

## Stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind, shadcn/ui, Lucide, TanStack Query
- **Backend:** Python 3.12, FastAPI, ARQ worker, SQLAlchemy 2.0 (async) + Alembic
- **AI:** LangGraph + LangChain, RAG, provider abstraction (Claude default; OpenAI, Gemini) — *from Phase 6*
- **Data:** PostgreSQL 16 + pgvector, Redis 7
- **Infra:** Docker / docker-compose · GitHub Actions CI

## Running it

```bash
# full stack (Postgres+pgvector, Redis, API, worker, frontend)
docker compose up --build -d
curl -fsS http://localhost:8000/health        # -> {"status":"ok"}
# API docs at http://localhost:8000/docs, frontend at http://localhost:3000

# backend checks without Docker (needs uv + a reachable Postgres/Redis)
cd backend && uv run ruff check . && uv run lint-imports && uv run mypy app && uv run pytest
```

`just` targets: `just up` / `just down` / `just migrate` / `just ci` / `just smoke`.
Copy `.env.example` to `.env` first; the LLM/embeddings providers default to deterministic
fakes so the whole stack runs offline.

**Production:** `compose.prod.yml` builds multi-stage images and runs the stack
behind an nginx reverse proxy with TLS, a one-shot Alembic `migrate` service,
and healthcheck-gated startup. `just prod-up` / `just seed` / `just smoke-prod`;
full procedure (certs, backup, restore, rollback) in
[`docs/runbook.md`](docs/runbook.md).
