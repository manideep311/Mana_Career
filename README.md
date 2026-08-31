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

CI is green on `main` (backend + frontend jobs, ~128 backend tests against real
Postgres + Redis, ~92% coverage).

| Phase | Scope | State |
|---|---|---|
| **0 — Foundations** | monorepo, `core/` (config, logging, `problem+json` errors, async DB + `Repository`, append-only audit log, Redis rate limiting), Alembic bootstrap, FastAPI app factory + health, ARQ worker skeleton, swappable LLM/embeddings provider seams, Docker Compose, Next.js shell + design tokens, CI | ✅ done, CI-verified |
| **1a — Authentication** | `users` + `refresh_tokens`, argon2id hashing, HS256 access JWT + opaque rotating refresh with family-wide reuse detection, `/auth` API, `get_current_user` / `get_current_admin` | ✅ done, CI-verified |
| **1b — Career profile** | `career_profiles` + experiences / education / projects / certifications, deterministic profile-strength scorer, `ProfileService`, `/profile` API (full read, partial update, strength, generic sub-entity CRUD + reorder) | ✅ done, CI-verified |
| **1c — Frontend shell** | design system + auth screens + profile editor UI | ⏳ next |
| **2–14** | résumé parsing → career profile generation → job ingestion + search → matching engine → RAG → Mana AI agent → résumé tailoring → cover letter + email → human-approval workflow → application tracker → career insights → testing/security hardening → Docker deploy | ⏳ planned (spec §9) |

Phase plans and completion reports: [`docs/superpowers/plans/`](docs/superpowers/plans/).

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
