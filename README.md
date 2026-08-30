# Mana Career

**Your career. Your next move. Smarter with AI.**

A human-first AI career agent. Mana Career parses your résumé into a structured career
profile, lets you ingest job descriptions, computes an **explainable** résumé↔job match
score, finds your skill gaps, builds a grounded learning roadmap, tailors résumés and
drafts cover letters + application emails, and — through the **Mana AI** agent — prepares
complete applications that **you review and approve before anything is sent**.

> AI recommends → AI prepares → **Human decides.**

## Status

Pre-implementation. The full system design is in
[`docs/superpowers/specs/2026-08-30-mana-career-design.md`](docs/superpowers/specs/2026-08-30-mana-career-design.md).

Implementation follows the 15-phase roadmap in §9 of that spec. Each phase ends with a
change report (what changed, why, files, how to test, regression check).

## Stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind, shadcn/ui, Lucide, TanStack Query
- **Backend:** Python, FastAPI, ARQ worker
- **AI:** LangGraph + LangChain, RAG, provider abstraction (Claude default; OpenAI, Gemini)
- **Data:** PostgreSQL 16 + pgvector, Redis
- **Infra:** Docker / docker-compose
