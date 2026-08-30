# Mana Career — System Design Spec

- **Date:** 2026-08-30
- **Status:** Approved for implementation (brainstorming complete)
- **Tagline:** "Your career. Your next move. Smarter with AI."
- **Core principle:** AI recommends → AI prepares → **Human decides.** The AI never makes an irreversible external decision without explicit human approval.

---

## 0. Summary

Mana Career is a human-first AI career agent for AI/ML/software professionals. It parses a résumé into a structured career profile, lets the user ingest job descriptions, computes an **explainable** résumé↔job match score, identifies missing skills, generates a grounded learning roadmap, tailors résumés and writes cover letters + application emails, and — through an agent ("Mana AI") — prepares complete applications that a human reviews and approves before anything is sent.

**Chosen architecture:** modular monolith — one FastAPI app + one ARQ worker (shared domain library, separate processes) + a Next.js frontend, one repository, strict internal module boundaries, every external dependency behind an interface with adapters. Replaceability comes from the interfaces, not from network splits.

**Scope:** portfolio/demo grade — real authentication, per-user data isolation, production patterns throughout, but not operated at scale. No multi-tenant orgs, no billing.

---

## 1. Product Architecture

### 1.1 Operating principle, enforced in code

| Layer | Rule |
|---|---|
| Data | Every stored fact carries a `source` (`user`, `resume_extraction`, `job_extraction`, `web_research`, `seed`). |
| Computation | Scores are deterministic and reproducible from stored inputs; the LLM narrates them, never produces them. |
| Action | Anything leaving the system (email) requires an `approval_requests` row in `approved` state, created by a human action; no code path bypasses it. |
| UI | Three visually distinct treatments — **retrieved fact**, **calculated score**, **AI suggestion** — plus a real "I don't have enough information to determine this." state. |

### 1.2 Persona

Primary: a mid-to-senior AI/ML or software professional running an active or passive job search. Technical, skeptical of AI hand-waving, wants leverage on the repetitive parts (tailoring, drafting, tracking) while keeping judgment.

### 1.3 Product surfaces

| Surface | Answers | Primary components |
|---|---|---|
| Dashboard | "What should I focus on today?" | Next Best Action, profile/résumé strength, best matches, apps in progress, skill gaps, AI Activity feed |
| Profile | "Does the system understand me?" | Structured career-profile editor, preferences, goals |
| Résumé Workspace | "Is my résumé strong, and strong *for this*?" | 3-pane: sections editor / live preview / Mana AI suggestions (Accept·Edit·Dismiss) |
| Job Discovery | "What roles fit me?" | Search + filters, job cards with match % and skill chips |
| Job Detail | "*Why* does this fit, and what's missing?" | Full JD, explainable match breakdown, strengths, gaps, recommended prep, `Prepare Application` CTA |
| Application Builder | "Get this application ready." | 7-step guided flow with visible progress and a hard approval stop |
| Application Tracker | "Where does each application stand?" | Kanban (Saved·Applied·Interview·Offer·Rejected) + per-application detail |
| Career Insights | "Where is my career going?" | Strengths, skills to develop, recommended next step, learning roadmap, suggested projects |
| Mana AI | "Help me think and act." | Docked conversational panel that renders typed **response blocks** alongside text |
| AI Activity | "What did the AI just do?" | Chronological, plain-language log linked to the artifact each step produced |

### 1.4 Next Best Action engine

A deterministic ranker (not an LLM) scores candidate actions each time the dashboard loads: review a ready application, recompute profile gaps, tailor résumé for a high-match job, add a job, start a roadmap milestone, follow up on a stale application. Rule-based urgency/impact ordering (e.g. `applications` in `awaiting_approval` outrank everything). The LLM writes only the one-sentence framing of the top item.

### 1.5 Capability map (Mana AI's 12 capabilities → module)

Résumé analysis → `resume/`; job discovery → `jobs/` + `rag/`; job matching + skill-gap analysis → `matching/`; career recommendations + learning recommendations → `roadmap/` + ranker; résumé customization + cover-letter + application-email generation → `generation/`; application preparation → `agents/`; application tracking → `applications/`; career Q&A → `rag/` + `conversations/`.

### 1.6 Knowledge sources for RAG

Résumé content · job descriptions · extracted skills · projects · certifications · company/market notes (web research, stored + embedded) · curated `learning_resources` catalog. Each is chunked and embedded into a per-source vector table with `source` + `owner_id` metadata for filtered retrieval.

### 1.7 Job data model decision

Manual-only ingestion (paste/upload); **no scraping, no job-board APIs.** The app ships with a curated **demo job dataset** (~60–100 realistic AI/ML/software postings, labeled sample data) loaded at setup so Discovery, Matching, and the Tracker are demonstrable on first launch. The "Job Research Agent" performs company/market **enrichment via web search** over jobs already in the system — it does not source new postings.

### 1.8 Out of scope (YAGNI)

Live job-board / ATS integrations · auto-apply · multi-tenant orgs / team seats · payments/billing · recruiter-side features · native mobile apps · real-time collaborative résumé editing.

---

## 2. System Architecture

### 2.1 Layers

- **Client — Next.js (App Router).** API-only consumer. RSC for first paint; client components for interactivity + SSE. Replaceable without backend changes.
- **API — FastAPI.** Thin. Validates input (Pydantic v2), enforces auth + per-user scoping, enqueues heavy work to Redis, streams via SSE. No LLM calls or parsing inline. One router per domain. A repository layer injects `user_id` into every query.
- **Domain library.** Ten packages with enforced dependency direction, each exposing a `service.py` public interface; imported identically by API and worker.
- **Worker — ARQ.** Async-native, same domain library. Idempotent tasks (keyed by entity id + input hash), retry with backoff, dead-letter to `task_failures`. Long agent runs and all LLM calls live here.
- **PostgreSQL 16 + pgvector.** Relational data + embedding columns (HNSW) + `tsvector` (hybrid search) + LangGraph checkpoints. **Redis** = queue + ephemeral cache only.
- **Object storage.** Original uploads via a `FileStore` interface (local volume in dev, S3-compatible adapter for deploy).

### 2.2 Domain packages

| Package | Does | Interfaces it owns |
|---|---|---|
| `resume/` | PDF → text → validated structured profile; section-aware chunking | `ResumeParser` (PyMuPDF default, OCR fallback), `ResumeExtractor` |
| `jobs/` | Pasted/uploaded JD → cleaned text → structured requirements; chunking | `JobIngestor`, `JobExtractor` |
| `embeddings/` | Text ↔ vectors | `EmbeddingsProvider` (Voyage/Anthropic, OpenAI, local, fake) |
| `rag/` | Hybrid retrieval (vector + keyword, RRF), metadata filters, MMR/rerank, token-budgeted context **with citations** | `VectorStore` (pgvector), `Retriever`, `Reranker` (optional) |
| `matching/` | **Deterministic** 0–100 score + component breakdown + evidence spans; ranked skill gaps | `MatchScorer` (pure), `MatchExplainer` (LLM narrates, never scores) |
| `roadmap/` | Ranked gaps + constraints → sequenced milestones grounded in the `learning_resources` KB | `RoadmapPlanner` |
| `generation/` | Tailored résumé + cover letter + email; every claim mapped to a source span or rejected; render to PDF/MD/DOCX | `DocumentGenerator`, `ClaimValidator`, `DocumentRenderer` |
| `agents/` | LangGraph supervisor + sub-agents; Postgres checkpointer; `interrupt` before any outbound action | tool registry, graph + state |
| `conversations/` | Chat + agent-run history, tool calls, citations, token/cost | — |
| `skills/` | Controlled skill taxonomy, alias normalization, semantic near-match | — |
| `profile/` | Career-profile assembly + strength scoring | — |

Cross-cutting `core/`: pydantic-settings config (env only, secrets redacted from logs), structlog JSON logging with request/run/user IDs + PII filter, typed errors + `problem+json` handlers, OpenTelemetry traces + token/cost meter, auth utils, base `Repository`, SSE helpers, Redis rate limiter.

### 2.3 LLM provider abstraction

`domain/llm/provider.py` defines `LLMProvider` — `complete(messages, schema?, tools?)`, `stream(messages)`, `capabilities()`. Adapters: **`AnthropicAdapter` (default)**, `OpenAIAdapter`, `GeminiAdapter`, `FakeAdapter` (tests). Selected by `LLM_PROVIDER`. A `policy.py` model map routes work by task: `extraction` → fast/cheap, `explanation` → mid, `generation` → best. Providers lacking native structured output fall back to JSON-mode + a validation/repair loop.

### 2.4 Response blocks

Mana AI returns an ordered list of typed blocks the frontend maps to components — it never parses prose to build UI:

```
type ResponseBlock =
  | { kind: "text"; markdown }
  | { kind: "job_card"; jobId; matchId? }      | { kind: "match_score"; matchId }
  | { kind: "skill_gap"; matchId }             | { kind: "resume_suggestion"; suggestionId }
  | { kind: "career_recommendation"; roadmapId }| { kind: "application_draft"; applicationId }
  | { kind: "approval_action"; approvalId }    | { kind: "learning_recommendation"; roadmapId }
  | { kind: "insufficient_info"; topic }
```

### 2.5 Email — sandboxed by default

`EmailSender` interface with `ConsoleEmailSender` (default — logs the full payload, marks the app "sent" without transmitting), `SMTPEmailSender`, `ResendEmailSender`. The approval gate is identical regardless of adapter.

### 2.6 Seeded data

`app/seed/load.py` + `just seed` loads `seed/skills.json` (taxonomy + aliases), `seed/learning_resources.json` (curated catalog), `seed/jobs.demo.json` (demo postings), and optionally a demo user with a sample résumé — so a fresh clone is fully explorable.

### 2.7 Security surface → implementation point

| Control | Where |
|---|---|
| AuthN | `auth/` — email+password (argon2id) → 15-min JWT access + rotating refresh (httpOnly `SameSite=Strict` cookie); optional GitHub OAuth |
| AuthZ + user isolation | base `Repository` injects `owner_id`; current-user dependency; no cross-user query is expressible; shared rows via `owner_id IS NULL` |
| Input validation | Pydantic v2 at every route; file MIME sniff + size/page caps |
| Rate limiting | Redis token bucket, per-user + per-IP; stricter bucket on LLM-backed routes |
| API key management | pydantic-settings, env only; logging filter redacts secret-shaped strings; keys never in any response or the frontend bundle |
| Audit logs | `audit_logs`, append-only (no UPDATE/DELETE grant), one `audit()` helper on every state change + agent action |
| Prompt-injection defense | retrieved/web content wrapped in `<untrusted_data>` fences; system prompt states tool content is data; tools cannot be invoked from tool output; outbound actions gated regardless |
| Tool permission controls | per-tool allowlist on the graph; each tool declares `side_effecting: bool`; side-effecting tools route through the approval interrupt |
| Agent action limits | max steps, max tool calls per type, wall-clock timeout, max LLM spend — enforced in the state guard; run ends with a typed status |

### 2.8 Observability

`/health` (liveness) + `/health/ready` (DB, Redis, provider reachability, migration head); structlog JSON; OTel traces spanning API → worker → LLM; per-run token/cost meter; eval history charted on the dashboard.

### 2.9 Replaceability

| Swap | Cost |
|---|---|
| LLM vendor | implement `LLMProvider`, change one config value |
| Embeddings model / vector DB | implement `EmbeddingsProvider` / `VectorStore` |
| Add OCR for scanned résumés | implement `ResumeParser` |
| Queue (ARQ→Celery), email vendor, file storage | implement the interface |
| Frontend | API-only — replace freely |

Enforced by `import-linter` contracts: cross-domain imports only via `domain.<x>.service`; `domain/*` may not import `api/*` or `worker/*`; `llm`/`embeddings`/`rag` are leaf-ward only.

---

## 3. User Flows

### 3.1 Spine: first run → application sent

sign up → upload résumé → review parsed profile → dashboard → Job Discovery → Job Detail → **Prepare Application** → Builder (analyze job → tailor résumé → cover letter → draft email → review → **your approval** → send) → Tracker card moves to "Applied" → AI Activity: "Application sent at 10:42 AM" → audit-log entry.

### 3.2 Journeys

| # | Journey | Key steps | Async / states |
|---|---|---|---|
| J1 | Onboarding | sign up → upload PDF → 3-stage parse/extract/index stepper → review extracted profile → edit/confirm → dashboard populates | upload progress bar; skeleton profile cards; corrections saved inline; corrections become extraction-eval labels |
| J2 | Understand a job | Discovery search + filters → job cards (match % + skill chips) → Job Detail → "Why this match?" → per-dimension breakdown, strengths ✓, gaps △, recommended prep | skeleton grid during search; "Scoring…" on card until match cached; fact / score / AI-explanation visually separated |
| J3 | Prepare an application | Job Detail → Prepare Application → Builder auto-runs each step with check-marks → step 5 full review → step 6 approval card (role/company/to/attachments/full body + "Nothing will be sent until you approve it" + [Edit Draft] [Approve & Send]) → step 7 send → timestamped success | each step: spinner + plain-language status; agent run streamed via SSE into stepper + AI Activity; approval is a server-side pause, not just UI |
| J4 | Improve résumé | Résumé Workspace 3-pane → suggestion appears with [Accept] [Edit] [Dismiss] → Accept creates a **new résumé version** → preview updates | suggestions load async per section; optimistic accept + toast; dismiss remembered |
| J5 | Plan learning | Career Insights → strengths + skills to develop → Generate roadmap → milestones stream in (skill · why · resources from catalog · effort · practice project · checkpoint) → mark milestone done → strength + future scores reflect it | skeleton timeline; streamed milestone-by-milestone; resources are real catalog entries only |
| J6 | Ask Mana AI | docked panel → suggested prompt or typed → response streams as text + blocks → act on a block inline | panel keeps session context; token streaming for text; blocks pop in when data resolves; explicit "I don't have enough information…" block on grounding gaps |
| J7 | Track applications | Kanban → drag card between columns → open card → detail (résumé version, cover letter, sent email, timeline, AI reasoning, notes) → add note / log interview | column move = optimistic + persisted + audit; detail timeline merges `ai_actions` + `application_events` + notes |

### 3.3 Global rules

Skeletons for content, labelled spinners for AI work, never a bare "Loading…". Every list has a designed empty state with a next action. Typed API errors → toast + inline + retry; agent failures surface in AI Activity with a "Try again". Nothing user-visible is destroyed — résumé edits create versions, tracker moves are logged, dismissed suggestions are recoverable.

---

## 4. AI Agent Architecture

### 4.1 Design stance

The brief's node chain is a **pipeline of mostly-bounded steps**, not twelve free-roaming agents. Of the twelve, **only `job_research` iterates** (LLM + web search, capped). Everything else is either **deterministic** (retrieval, scoring, assembly) or a **single bounded LLM call** against a schema. This is the primary defense against loops, redundant tool calls, and cost.

### 4.2 The graph

One **supervisor** graph. The user's goal selects a goal-scoped path through shared nodes; the full chain runs only for `prepare_application`.

```
user goal ──▶ SUPERVISOR (deterministic router)
   ├─ analyze_profile:     resume_analyzer → profile_builder
   ├─ understand_job:      job_research? → job_retrieval? → match_analysis → skill_gap → recommendation
   ├─ enrich_job:          job_research
   └─ prepare_application: job_research? → match_analysis → skill_gap
                           → resume_tailoring → claim_validator
                           → cover_letter → claim_validator
                           → email_draft → application_prep
                           → HUMAN_APPROVAL (interrupt)
                              ├─ approve → EMAIL_EXTERNAL_ACTION (assert approved + hash) → send · audit · status=completed
                              └─ reject  → REVISE (one loop back to tailoring/letter with feedback) or STOP

every node wrapped by guard(): budget check → run → increment → checkpoint
any BudgetExceeded / node error → HALTED (records partial results, typed status)
```

Checkpointer: Postgres. Every transition persists state, so a run survives worker restarts and can pause indefinitely at approval. `?` = skipped when a fresh artifact already exists (input-hash freshness check).

### 4.3 Node catalog

| Node | Type | Writes | Tools | Interrupt |
|---|---|---|---|---|
| `supervisor` | deterministic router | route decision | — | no |
| `resume_analyzer` | parse + 1 LLM call | résumé text, structured extraction | `parse_pdf` | no |
| `profile_builder` | deterministic merge + light LLM normalize | `career_profiles` row | — | no |
| `job_research` | iterative LLM (≤4 tool calls) | `company_research` (embedded, `source=web_research`) | `web_search` | no |
| `job_retrieval` | deterministic hybrid search | ranked job id list | `vector_search` | no |
| `match_analysis` | deterministic scoring + 1 LLM explanation | `job_matches` + `match_components` | — | no |
| `skill_gap` | deterministic rank + 1 LLM rationale | `skill_gaps` | — | no |
| `recommendation` | RAG + 1 LLM call (schema) | `learning_recommendations` | — | no |
| `resume_tailoring` | RAG + LLM section-by-section | draft `resume_versions` | — | no |
| `cover_letter` | RAG + 1 LLM call | `cover_letters` | — | no |
| `email_draft` | 1 LLM call (schema) | `application_emails` (draft) | — | no |
| `claim_validator` | deterministic | pass / unsupported claims → re-prompt (≤2) | — | no |
| `application_prep` | deterministic assembly | `applications` (awaiting_approval) + `approval_requests` (pending) with full payload snapshot + hash | — | no |
| `human_approval` | **interrupt** | — (pauses) | — | **yes** |
| `email_external_action` | deterministic + side effect | `EmailSender.send`, `audit_logs`, `applications.status=applied`, `ai_actions` | `send_email` (`side_effecting`) | no |
| `halted` | terminal | run status + reason | — | no |

### 4.4 Shared state object

```python
class Budget(TypedDict):
    max_steps: int; steps_taken: int                     # default 24
    max_llm_calls: int; llm_calls_made: int              # default 12
    tool_call_caps: dict[str, int]                        # {"web_search": 4, "vector_search": 6}
    tool_calls_made: dict[str, int]
    deadline_ts: float                                    # now + 180s
    max_cost_usd: float; cost_usd: float                  # default 0.75

class ManaState(TypedDict):
    run_id: str; user_id: str; goal: Literal[...]
    inputs: dict
    resume_extraction: Extraction | None
    profile: ProfileRef | None
    research_notes: list[NoteRef]
    retrieved_jobs: list[str]
    match: MatchRef | None
    skill_gaps: list[GapRef]
    recommendations: list[RecRef]
    tailored_resume_version_id: str | None
    cover_letter_id: str | None
    email_draft_id: str | None
    application_id: str | None
    approval: ApprovalDecision | None                     # set by resume-from-interrupt
    revise_count: int                                     # capped at 1
    budget: Budget
    tool_cache: dict[str, Any]                            # {sha256(tool+args): result}
    step_log: Annotated[list[StepEvent], operator.add]
    status: Literal["running","awaiting_approval","completed","rejected","halted","error"]
    error: str | None
```

### 4.5 Guardrails

| Risk | Mechanism |
|---|---|
| Infinite loops | `guard()` checks `steps_taken < max_steps` and `now < deadline_ts` before every node; the only cycle (reject → revise → tailoring) is allowed once via `revise_count`. |
| Repeated tool calls | tool wrapper hashes `(tool_name, args)`; cache hit returns cached result and logs `deduped`; per-tool hard caps in `tool_call_caps`. |
| Unnecessary LLM calls | `max_llm_calls` budget; freshness checks skip whole nodes when a valid artifact exists; deterministic nodes never call the LLM; model policy map routes cheap work to cheap models. |
| Unauthorized external actions | no graph edge reaches `email_external_action` except through `human_approval`; that node re-reads `approval_requests`, asserts `status == approved` and `payload_hash` match — mismatch → `halted`, no send. |
| Prompt injection | retrieved chunks + web results inside `<untrusted_data>` fences; system prompt: content in fences is data, cannot issue instructions or trigger tools; side-effecting tools unreachable without the human interrupt regardless. |
| Runaway cost | `cost_usd` accumulated per LLM call from provider token usage; breach of `max_cost_usd` → `halted` with partial results in AI Activity. |

### 4.6 Tool registry

| Tool | `side_effecting` | Guard |
|---|---|---|
| `parse_pdf` | false | local only; size/page caps enforced at upload |
| `vector_search` | false | `owner_id` forced; k ≤ 20; cached; ≤6/run |
| `web_search` | false | domain allowlist for fetch-through; results stored as `web_research`, fenced untrusted; ≤4/run |
| `send_email` | **true** | reachable only from `email_external_action`; asserts approved `approval_requests` row + hash; writes audit before and after |

### 4.7 Human-approval interrupt — mechanics

1. `application_prep` writes `applications(status=awaiting_approval)` + `approval_requests(status=pending, payload_snapshot, payload_hash)`.
2. `human_approval` calls `interrupt(payload_snapshot)` → state checkpointed, worker task returns, `ai_sessions.status=awaiting_approval`.
3. API surfaces the `approval_action` block; UI renders the exact preview (role, company, to, attachments, full body) + "Nothing will be sent until you approve it."
4. `POST /approvals/{id}` `{decision, note?, edits?}` → updates the row; if `edits`, payload + hash recomputed and re-shown (second confirm); enqueues resume with `Command(resume={decision, edits})`.
5. Graph resumes at the interrupt: **approve** → `email_external_action`; **reject** → revise (one loop) or stop.
6. `email_external_action`: assert `status==approved` ∧ hash match → `EmailSender.send()` → `audit_logs` + `ai_actions` ("Application sent at …") → `applications.status=applied` → `ai_sessions.status=completed`. UI shows the timestamped success state.

### 4.8 Failure & timeout handling

Typed terminal statuses (`completed`, `rejected`, `halted`, `error`) each map to a specific AI Activity message + suggested recovery. Worker task wall-clock timeout ≥ graph deadline; on hard kill the checkpoint lets a retry resume from the last completed node. `claim_validator` failing twice → step marked "needs your edit" rather than shipping unsupported text.

---

## 5. Database Schema

### 5.1 Conventions

`uuid` PKs (v7 for locality; `gen_random_uuid()` fallback) · `created_at timestamptz default now()`, `updated_at` via trigger · enums as `text` + `CHECK` · soft delete (`deleted_at`) on user content, hard-cascade on derived rows · every user-scoped table has `user_id`/`owner_id NOT NULL`; shared rows use `owner_id IS NULL`; repository filter always `user_id = :me OR owner_id IS NULL` · `EMBED_DIM` fixed per deployment, `embed_model` + `embed_dim` stored on every chunk row · HNSW (`m=16, ef_construction=64`, `vector_cosine_ops`) on all embeddings; GIN on `tsvector` + `text[]`/`jsonb` filter columns; `pg_trgm` on `jobs.title/company` · Alembic; bootstrap migration enables `vector`, `pg_trgm`, `citext`, `pgcrypto` · money = integer whole-currency units + `currency` + `period` · `audit_logs` has no UPDATE/DELETE grant for the app role.

### 5.2 Entity map

```
users ─1:1─ career_profiles ─1:N─ profile_experiences / _education / _projects / _certifications
  │                          └─1:N─ profile_skills ─N:1─ skills (shared taxonomy)
  ├─1:N─ resumes ─1:N─ resume_versions ─1:N─ resume_chunks (vector)
  │                          └─ resume_suggestions
  ├─1:N─ jobs ──1:N─ job_chunks (vector)              jobs(owner NULL) = seed dataset
  │        └─1:N─ company_research (vector, TTL)
  ├─1:N─ job_matches ─1:N─ match_components           (score = deterministic)
  │        └─1:N─ skill_gaps ─N:1─ skills
  ├─1:N─ learning_recommendations ─1:N─ roadmap_milestones ─N:M─ learning_resources (shared)
  ├─1:N─ applications ─1:1─ resume_versions / cover_letters / application_emails
  │        ├─1:N─ application_events
  │        └─1:1─ approval_requests   ◄── HITL gate
  ├─1:N─ ai_sessions ─1:N─ messages / ai_actions / agent_steps
  │                   └─ langgraph checkpoint tables (library-managed)
  └─1:N─ audit_logs (append-only)     +  task_failures, eval_runs / eval_results
```

### 5.3 Tables (columns are indicative; full DDL in migrations)

**Identity & auth**
- `users` — id · email `citext unique` · password_hash (argon2id) · full_name · status(`active`/`disabled`) · is_admin · email_verified_at · last_login_at · ts
- `auth_identities` — id · user_id · provider(`github`) · provider_account_id · unique(provider, provider_account_id)
- `refresh_tokens` — id · user_id · token_hash(sha256) · family_id · expires_at · revoked_at · ip · user_agent — idx(user_id), unique(token_hash), idx(family_id)

**Career profile**
- `career_profiles` — id · user_id `unique` · location · github_url · linkedin_url · portfolio_url · preferred_roles `text[]` · preferred_locations `text[]` · work_modes `text[]` · expected_salary_min/max · salary_currency · salary_period · years_experience · seniority · career_goals · profile_strength · completeness `jsonb` · ts
- `profile_experiences` — id · user_id · profile_id · company · title · employment_type · start_date · end_date · is_current · location · description · highlights `text[]` · tech `text[]` · source · order_index
- `profile_education` — id · user_id · profile_id · institution · degree · field · start_date · end_date · grade · source · order_index
- `profile_projects` — id · user_id · profile_id · name · description · url · highlights `text[]` · tech `text[]` · start_date · end_date · source · order_index
- `profile_certifications` — id · user_id · profile_id · name · issuer · issued_date · expires_date · credential_id · url · source · order_index

**Skills**
- `skills` *(shared, seeded)* — id · slug `unique` · label · category · aliases `text[]` · embedding `vector` — idx GIN(aliases), HNSW(embedding)
- `profile_skills` — id · user_id · profile_id · skill_id · proficiency · years · source · evidence_refs `jsonb` — unique(profile_id, skill_id)

**Résumés**
- `resumes` — id · user_id · title · original_filename · file_ref · content_type · size_bytes · page_count · status(`uploaded`→…→`indexed`/`failed`) · parse_error · extracted_text · extraction `jsonb` · is_primary · deleted_at · ts — idx(user_id, created_at desc), partial-unique(user_id) where is_primary
- `resume_versions` — id · user_id · resume_id · job_id? · application_id? · parent_version_id? · label · kind(`base_snapshot`/`manual_edit`/`ai_tailored`) · content `jsonb` (canonical structured résumé) · rendered_refs `jsonb` · generation_meta `jsonb` (model, provider, prompt_version, prompt_hash, token_usage, cost_usd, claim_validation) · created_by · ts
- `resume_chunks` *(vector)* — id · resume_version_id `cascade` · owner_id · chunk_index · section · ref_id (source sub-entity, for evidence) · content · token_count · embed_model · embed_dim · embedding `vector` · tsv `tsvector` — idx HNSW(embedding), GIN(tsv)
- `resume_suggestions` — id · user_id · resume_version_id · section · target_ref_id? · suggestion_type · title · body · proposed_change `jsonb` · status(`open`/`accepted`/`edited`/`dismissed`) · resulting_version_id? · source(`mana_ai`) · generation_meta `jsonb` · ts

**Jobs**
- `jobs` — id · user_id? (NULL = seed) · is_seed · source(`user_paste`/`user_upload`/`seed`) · source_ref · raw_text · title · company · company_domain · location · work_mode · employment_type · seniority · experience_min/max_years · salary_min/max · salary_currency · salary_period · salary_source · description · responsibilities `text[]` · required_skills `jsonb` (`[{skill_id,slug,label,weight}]`) · preferred_skills `jsonb` · structured `jsonb` · status · extraction_meta `jsonb` · posted_at · deleted_at · ts — idx(user_id), (is_seed), GIN(structured), trigram(title, company), (seniority), (work_mode)
- `job_chunks` *(vector)* — id · job_id `cascade` · owner_id? · chunk_index · section · content · token_count · embed_model · embed_dim · embedding `vector` · tsv `tsvector` — idx HNSW, GIN(tsv)
- `company_research` *(vector, TTL)* — id · job_id? · user_id · company · company_domain · topic · content · citations `jsonb` · source(`web_research`) · confidence · embedding `vector` · expires_at · created_at — idx HNSW, (company_domain), (expires_at)

**Matching**
- `job_matches` — id · user_id · resume_version_id · job_id · score `numeric(5,2)` · band(`strong`/`good`/`partial`/`weak`) · dimension_scores `jsonb` · strengths `jsonb` · gaps `jsonb` · explanation · explanation_meta `jsonb` · inputs_hash · scorer_version · computed_at — unique(resume_version_id, job_id, scorer_version), idx(user_id, score desc)
- `match_components` — id · job_match_id `cascade` · dimension(`skill`/`experience`/`education`/`project`/`technology`/`location`/`role`/`seniority`/`salary`/`semantic`) · raw_score(0–1) · weight · contribution(points) · detail `jsonb` · evidence `jsonb` (`[{kind,ref_id,snippet}]`)
- `skill_gaps` — id · user_id · scope(`job`/`aggregate`) · job_match_id? · skill_id · skill_slug · skill_label · severity(`critical`/`important`/`nice_to_have`) · frequency · rationale · status(`open`/`learning`/`closed`) · addressed_by_roadmap_id? · ts

**Learning**
- `learning_recommendations` — id · user_id · scope · job_id? · title · constraints `jsonb` · summary · next_step · status(`active`/`archived`) · generation_meta `jsonb` · ts
- `roadmap_milestones` — id · recommendation_id `cascade` · user_id · order_index · skill_id? · skill_slug · skill_label · title · why_it_matters · resource_ids `uuid[]` (→ learning_resources, real only) · est_hours · practice_project · checkpoint · status(`not_started`/`in_progress`/`done`) · completed_at
- `learning_resources` *(shared, seeded)* — id · title · provider · url · type · skills `text[]` · level · est_hours · cost · summary · embedding `vector` · is_active — idx HNSW, GIN(skills)

**Applications & documents**
- `applications` — id · user_id · job_id · resume_version_id? · cover_letter_id? · application_email_id? · status(`saved`/`preparing`/`awaiting_approval`/`applied`/`interview`/`offer`/`rejected`/`withdrawn`) · match_score(snapshot) · source(`user`/`mana_ai`) · ai_session_id? · applied_at · last_status_change_at · notes · deleted_at · ts — idx(user_id, status), (user_id, updated_at desc)
- `application_events` — id · application_id `cascade` · user_id · kind(`status_change`/`note`/`interview_scheduled`/`ai_action`/`email_sent`) · from_status · to_status · body · meta `jsonb` · occurred_at
- `cover_letters` — id · user_id · job_id · application_id? · resume_version_id? · tone · content · content_json `jsonb` · rendered_refs `jsonb` · generation_meta `jsonb` (+ claim_validation) · version · supersedes_id? · created_by · ts
- `application_emails` — id · user_id · application_id? · job_id · to_email · to_name · cc `text[]` · bcc `text[]` · subject · body · body_format(`plain`/`html`) · attachment_refs `jsonb` · status(`draft`/`awaiting_approval`/`approved`/`sending`/`sent`/`failed`/`canceled`) · provider(`console`/`smtp`/`resend`) · provider_message_id · sent_at · send_error · generation_meta `jsonb` · ts
- `approval_requests` *(HITL)* — id · user_id · application_id · ai_session_id · run_id · action_type(`send_application_email`) · payload_snapshot `jsonb` · payload_hash(sha256) · status(`pending`/`approved`/`rejected`/`superseded`/`expired`) · decided_by? · decided_at · decision_note · edits `jsonb`? · expires_at · ts — idx(user_id, status), partial-unique(run_id, action_type) where status='pending'

**AI sessions, actions, trace**
- `ai_sessions` — id · user_id · kind(`chat`/`agent_run`) · goal? · title · context `jsonb` · status · run_id? · budget `jsonb` · totals `jsonb` · error · started_at · ended_at · ts — idx(user_id, created_at desc), (status), (run_id)
- `messages` — id · ai_session_id `cascade` · user_id · role(`user`/`assistant`/`tool`/`system`) · content(markdown) · blocks `jsonb` (`ResponseBlock[]`) · tool_calls `jsonb` · tool_call_id · citations `jsonb` · token_usage `jsonb` · model_id · provider · created_at — idx(ai_session_id, created_at)
- `ai_actions` *(user-facing feed)* — id · user_id · ai_session_id? · run_id? · node · action_key · summary(plain language) · detail `jsonb` · entity_type · entity_id · status(`ok`/`warning`/`error`) · latency_ms · cost_usd · occurred_at — idx(user_id, occurred_at desc)
- `agent_steps` *(internal trace)* — id · ai_session_id `cascade` · run_id · step_index · node · input_summary `jsonb` · output_summary `jsonb` · llm_calls · tool_calls `jsonb` · tokens_in/out · cost_usd · status(`ok`/`deduped`/`skipped_fresh`/`error`/`budget_exceeded`) · error · started_at · ended_at · duration_ms

**Audit & ops**
- `audit_logs` *(append-only)* — id · actor_type(`user`/`mana_ai`/`system`) · actor_user_id? · on_behalf_of_user_id? · action · resource_type · resource_id · ip · user_agent · request_id · before `jsonb`? · after `jsonb`? (redacted) · result(`success`/`failure`) · meta `jsonb` · created_at — idx(actor_user_id, created_at desc), (resource_type, resource_id), (action, created_at)
- `task_failures` — id · task_name · args_hash · payload `jsonb`(redacted) · error · traceback · attempts · first_failed_at · last_failed_at · resolved_at?
- `eval_runs` — id · suite(`retrieval`/`generation`/`matching`) · dataset_ref · dataset_version · git_sha · provider · model_ids `jsonb` · config `jsonb` · metrics `jsonb` · status · started_at · ended_at
- `eval_results` — id · eval_run_id `cascade` · case_id · input `jsonb` · expected `jsonb` · actual `jsonb` · scores `jsonb` · passed · judge_meta `jsonb`

### 5.4 Vector & retrieval strategy

| Table | Search mode | Indexes |
|---|---|---|
| `resume_chunks` | hybrid (cosine + tsv), filter `owner_id` | HNSW + GIN(tsv) |
| `job_chunks` | hybrid, filter `owner_id IS NULL OR = me` | HNSW + GIN(tsv) |
| `company_research` | cosine, filter `company_domain`, `expires_at > now()` | HNSW |
| `learning_resources` | cosine + `skills` array overlap | HNSW + GIN(skills) |
| `skills` | cosine (near-match in scorer) | HNSW |

Hybrid = vector top-N ∪ tsv top-N → reciprocal-rank fusion → optional MMR / cross-encoder rerank → token-budgeted context with citation refs.

---

## 6. API Architecture

### 6.1 Conventions

Base `/api/v1`; OpenAPI 3.1 at `/api/openapi.json`, frontend client generated from it. `Authorization: Bearer <access>` (15 min); rotating refresh in httpOnly `SameSite=Strict` cookie; `POST /auth/refresh`. Long operations return `202` + a domain resource carrying `status`; client polls `GET` or subscribes to `.../events` (SSE) — raw task ids never exposed. Errors: RFC 9457 `application/problem+json` `{type,title,status,detail,instance,code,errors[]}` with a stable machine `code`. Cursor pagination `?limit=&cursor=` → `{items, next_cursor}`. `Idempotency-Key` on expensive/side-effecting POSTs. `RateLimit-*` headers; `429` + `Retry-After`. `X-Request-ID` on every response, propagated API → worker → LLM.

### 6.2 Endpoint catalog

**`/auth`** — `POST /register` · `POST /login` · `POST /refresh` · `POST /logout` · `GET /me` · `POST /password/change` · `POST /oauth/github/start` + `GET /oauth/github/callback` *(optional)*

**`/profile`** — `GET /` · `PUT /` · `GET /strength`; sub-resources `/experiences` `/education` `/projects` `/certifications` each `GET`/`POST`/`PATCH {id}`/`DELETE {id}`/`POST /reorder`; `GET/POST/PATCH/DELETE /skills`; `GET /api/v1/skills?query=` (taxonomy autocomplete)

**`/resumes`** — `POST /` (multipart) → 202 · `GET /` · `GET /{id}` · `GET /{id}/events` (SSE) · `PATCH /{id}` · `POST /{id}/reprocess` · `DELETE /{id}` · `GET /{id}/extraction` · `POST /{id}/confirm-profile`

**`/resume-versions`** — `GET /?resume_id=&job_id=` · `GET /{id}` · `POST /` · `PATCH /{id}` (creates child version) · `GET /{id}/render?format=pdf|md|docx` · `GET /{id}/suggestions` · `POST /{id}/suggestions/refresh` · `POST /suggestions/{id}/accept` · `POST /suggestions/{id}/dismiss` · `POST /suggestions/{id}/apply-edited`

**`/jobs`** — `POST /` (`{raw_text}` or multipart) → 202 · `GET /?q=&role=&location=&work_mode=&seniority=&salary_min=&skills=&has_match=&sort=match|recent` · `GET /{id}` · `GET /{id}/events` (SSE) · `PATCH /{id}` · `DELETE /{id}` *(user jobs only)* · `POST /{id}/research` → 202 · `GET /{id}/research`

**`/matches`** — `POST /` `{resume_version_id?, job_id}` → 202/200 · `GET /?job_id=&min_score=&sort=` · `GET /{id}` · `GET /{id}/components` · `POST /recompute` `{scope: all|job_id}`

**`/skill-gaps`** — `GET /?scope=job|aggregate&job_match_id=` · `POST /aggregate` → 202 · `PATCH /{id}` `{status}`

**`/roadmaps`** — `POST /` `{scope, job_id?, constraints}` → 202 · `GET /` · `GET /{id}` · `GET /{id}/events` (SSE) · `PATCH /{id}` `{status}` · `PATCH /{id}/milestones/{mid}` `{status}` · `GET /api/v1/learning-resources?skills=&level=`

**`/insights`** — `GET /` → `{strengths[], skills_to_develop[], recommended_next_step, trending_skills[] (labeled sample), suggested_projects[], roadmap_summary}`

**`/applications`** — `POST /` `{job_id, intent: save|prepare}` → 201/202 · `GET /?status=&sort=` · `GET /{id}` · `PATCH /{id}` `{status, notes}` · `GET /{id}/events` (SSE) · `GET /{id}/timeline` · `POST /{id}/notes` · `DELETE /{id}`; **Builder** `POST /{id}/prepare` → 202 · `POST /{id}/steps/{step}/rerun` `{note?}` · `GET /{id}/draft`

**`/approvals`** *(humans only)* — `GET /?status=pending` · `GET /{id}` · `POST /{id}` `{decision: approve|reject, note?, edits?}` (edits → `{status: needs_reconfirm, payload_snapshot}`, client re-POSTs) · `POST /{id}/cancel`

**`/ai`** — `POST /sessions` `{kind: chat, context?}` · `GET /sessions` · `GET /sessions/{id}` · `POST /sessions/{id}/messages` `{content}` → SSE (`token`|`block`|`done`) · `POST /sessions/{id}/goal` `{goal, inputs}` → 202 · `GET /sessions/{id}/events` → SSE · `POST /sessions/{id}/stop`

**`/activity`** — `GET /?cursor=&entity_type=` · `GET /{id}`

**`/audit`** — `GET /?action=&resource_type=&from=&to=` (caller's own, read-only)

**`/eval`, `/ops`** *(admin)* — `POST /eval/runs` · `GET /eval/runs` · `GET /eval/runs/{id}` · `GET /eval/runs/{id}/results` · `GET /ops/tasks/failures`

**Health** — `GET /health` · `GET /health/ready`

### 6.3 Authorization model

One app role `user`; every fetch via `get_owned_or_shared(model, id, user)` — cross-user access not expressible. `is_admin` gates `/eval`, `/ops`, seed management. The agent runs as actor `mana_ai` with `on_behalf_of_user_id` and has **no path** to `/approvals` decisions — only a human bearer token can approve. `send_email` has no HTTP surface.

### 6.4 SSE event contract

```
event: status    data: {resource, id, status, message}
event: step      data: {node, action_key, summary, latency_ms}
event: token     data: {text}
event: block     data: <ResponseBlock>
event: approval  data: {approval_id, payload_snapshot}
event: done      data: {status, totals}
event: error     data: {code, message}
```

### 6.5 Rate-limit tiers (Redis token bucket, per-user + per-IP)

`/auth/*` 10/min/IP · uploads 20/hour/user · LLM-backed (`/matches`, `/roadmaps`, `/ai/*`, `/applications/*/prepare`) 60/hour/user + 10/min burst · reads 240/min/user.

---

## 7. UI Architecture

### 7.1 Route map (Next.js App Router)

`(marketing)/page.tsx` · `(auth)/login` `(auth)/register` · `(app)/layout.tsx` (AppShell: sidebar / mobile bottom nav + docked ManaPanel) → `dashboard` · `jobs` · `jobs/[id]` · `resume` · `applications` · `applications/[id]` · `applications/[id]/prepare` · `insights` · `activity` · `profile` · `settings`.

### 7.2 Rendering & data strategy

RSC for first paint of lists/detail; **TanStack Query** in client components for mutations, polling, cache invalidation. `useSSE` hook (auth, backoff, reconnect) → events map to query-cache invalidations. Thin client state: auth/session context, Mana AI panel context, URL search params for all filters/tabs; **no global store.** Forms: `react-hook-form` + `zod` mirroring backend Pydantic; server `problem+json` `errors[]` maps back onto fields. Optimistic UI on tracker moves, suggestion accept/dismiss, note add, with rollback on error.

### 7.3 Component layers

`components/ui/` shadcn primitives → `components/common/` (EmptyState, ErrorState, Skeletons, ProblemToast, ScoreMeter, SkillChip, **SourceBadge**) → `components/<domain>/` → `components/ai/blocks/` (one per `ResponseBlock` kind) + `block-registry.ts` → `components/layout/` (AppShell, Sidebar, MobileNav, ManaPanelDock).

**Trust treatment** via `<SourceBadge>`: *retrieved fact* (plain text + "from your résumé/the job post" + citation), *calculated score* (mono numerals + meter + "how this is calculated"), *AI suggestion* (indigo left rule + "Mana AI suggestion" + always paired with Accept/Edit/Dismiss or a citation), *insufficient info* (muted card + what's missing).

### 7.4 Mana AI panel

Not a full-screen chatbot. Desktop: right-docked, collapsible, ~380px, persists across routes. Mobile: full-height Sheet from the bottom-nav tab. Context-aware (seeds prompts + carries `job_id` etc. in session `context`). Blocks are interactive inline. Responses stream `token` events interleaved with `block` events.

### 7.5 Loading / empty / error

Skeletons for lists/detail; labelled spinners for AI work; designed empty states with a next action and brief §19 microcopy; `problem+json` → `ProblemToast` + inline + retry; agent failures in AI Activity with "Try again"; transitions respect `prefers-reduced-motion`.

### 7.6 Accessibility

Full keyboard reachability (roving tabindex in Kanban + block lists); visible token-based focus rings; `aria-live=polite` for streaming text + toasts; focus trap + restore in dialogs/sheets; WCAG AA color pairs verified in the token file; fluid `clamp()` type scale; `prefers-reduced-motion`; the approval card fully operable on mobile with large tap targets and no horizontal scroll.

### 7.7 Design tokens (`styles/tokens.css`)

`--bg` warm off-white · `--text` deep charcoal · `--surface` white · `--text-muted` slate · `--accent` indigo/blue · `--positive` green · `--warning` amber · `--danger` red (errors only) · `--border` hairline · `--ring` accent@40% · `--radius` 14px · `--shadow-1/2` subtle. Font: Inter (fallback Geist, Manrope, system-ui). Generous spacing; max content width ~1200px. Single light theme ships; tokens structured for a later dark drop-in.

---

## 8. Folder Structure

```
mana-career/
├─ docker-compose.yml   compose.prod.yml   justfile   .env.example
├─ README.md   SECURITY.md
├─ docs/  superpowers/specs/  adr/  runbook.md  threat-model.md
├─ backend/
│  ├─ pyproject.toml  ruff.toml  mypy.ini  alembic.ini
│  ├─ alembic/versions/
│  └─ app/
│     ├─ main.py
│     ├─ core/       config logging errors security db telemetry rate_limit events
│     ├─ api/        deps · v1/{auth,profile,resumes,resume_versions,jobs,matches,
│     │              skill_gaps,roadmaps,insights,applications,approvals,ai,activity,
│     │              audit,eval,health,router} · schemas/
│     ├─ domain/
│     │  ├─ llm/         provider policy adapters/{anthropic,openai,gemini,fake}
│     │  ├─ embeddings/  provider adapters/{voyage,openai,local,fake}
│     │  ├─ rag/         vector_store retriever rerank chunking context
│     │  ├─ resume/      parser/{pymupdf,ocr} extractor service
│     │  ├─ jobs/        ingestor extractor service
│     │  ├─ matching/    scorer weights explainer gaps service
│     │  ├─ roadmap/     planner service
│     │  ├─ generation/  resume_tailor cover_letter email_draft claim_validator render/ service
│     │  ├─ agents/      graph state guards checkpointer nodes/ tools/{web_search,vector_search,parse_pdf,send_email}
│     │  ├─ applications/ service tracker events
│     │  ├─ conversations/ service blocks
│     │  ├─ skills/      taxonomy normalize
│     │  └─ profile/     service strength
│     ├─ infra/     storage/{base,local,s3}  email/{base,console,smtp,resend}  search/web  cache
│     ├─ models/    SQLAlchemy ORM per domain group; __init__ imports all → one MetaData
│     ├─ worker/    main  tasks/*  dead_letter
│     └─ seed/      load.py  (reads ../../seed/*.json)
│  └─ tests/  unit/ integration/ e2e/ prompt_injection/ fixtures/ conftest.py
├─ frontend/
│  ├─ package.json tsconfig.json tailwind.config.ts
│  ├─ app/  (marketing)/ (auth)/ (app)/…
│  ├─ components/  ui/ common/ layout/ ai/ <domain>/
│  ├─ lib/  api/ sse.ts query-keys.ts auth.ts format.ts
│  ├─ hooks/  use-sse use-agent-run use-approval use-match
│  ├─ styles/  globals.css tokens.css
│  └─ tests/  (vitest + RTL)   e2e/ (Playwright)
├─ seed/  skills.json  learning_resources.json  jobs.demo.json
└─ eval/  datasets/{retrieval,generation,matching}/  suites/  run.py
```

Boundary enforcement: `import-linter` contracts — cross-domain imports only via `domain.<x>.service`; `domain/*` may not import `api/*`/`worker/*`; `llm`/`embeddings`/`rag` are leaf-ward only.

---

## 9. Implementation Roadmap

Every phase ends with the brief §26 report: **what changed · why · files changed · how to test · regression check.** Cross-cutting tracks (observability, a11y, empty/loading/error states, ADRs) advance every phase.

| Phase | Goal | Key deliverables | "Done when" |
|---|---|---|---|
| **0 · Foundations** | runnable skeleton | monorepo; `docker-compose` (api/worker/db+pgvector/redis/frontend); `core/`; health checks; Alembic bootstrap (extensions); base `Repository`; `LLMProvider`/`EmbeddingsProvider` + `fake` adapters; CI (ruff, mypy, pytest, eslint, tsc, vitest) | `docker compose up` → `/health/ready` green; `pnpm dev` renders themed shell |
| **1 · Design system + auth + profile** | sign in and describe yourself | `tokens.css` + shadcn + `common/` primitives; auth (register/login/refresh/logout, argon2id, JWT rotation, rate limit, audit); `career_profiles` + sub-entities CRUD + `profile_strength`; `AppShell`; landing page | login → profile editable → strength shown; refresh rotation works |
| **2 · Résumé upload + parsing** | résumé → structured extraction | `FileStore` (local); `POST /resumes` + validation; ARQ `parse_resume`→`extract_resume`; `ResumeParser` (PyMuPDF) + OCR stub; `ResumeExtractor` (LLM+schema); SSE status; review screen; `confirm-profile` merge | upload PDF → review → confirm → profile populated |
| **3 · Career profile generation** | clean normalized profile | `profile_builder` normalization; skill taxonomy + alias normalization; evidence linking; strength breakdown; Résumé Workspace 3-pane shell | manual + résumé-derived profile coexist; skills map to taxonomy |
| **4 · Job ingestion + search** | browsable job corpus | seed loader; `POST /jobs`; `ingest_job`; `JobExtractor`; `job_chunks` embeddings; Discovery (search + filters + cards); Job Detail (JD only) | fresh clone shows demo jobs; paste a JD → appears structured |
| **5 · Job matching engine** | explainable score | deterministic `scorer` (10 dimensions + `weights`); `match_components` + evidence; `MatchExplainer` (narrates only); `skill_gaps` (job scope); "Why this match?" UI; bands | job card + detail show a 92%-style score with ✓/△ and narrative |
| **6 · RAG system** | grounded retrieval + retrieval eval | hybrid retriever (vector + tsv + RRF); MMR; optional rerank; token-budget context + citations; `<untrusted_data>` fencing; retrieval eval (recall@k/MRR/nDCG) + `/eval` + golden set v1 | matching's semantic dimension routes through `rag`; eval report generated in CI with thresholds |
| **7 · Mana AI agent** | the orchestrator | LangGraph graph + `ManaState` + Postgres checkpointer; supervisor router; deterministic nodes → domain services; `job_research` node (capped `web_search`); guards; `POST /ai/sessions`; `messages` SSE; `sessions/{id}/goal`; `ai_actions` feed; block registry; Mana AI panel; AI Activity page | "find jobs that match my experience" → text + job-card blocks; AI Activity logs steps |
| **8 · Résumé tailoring** | job-specific résumé | `resume_tailoring` node + `generation` service; `ClaimValidator` (claim→source span, reject+reprompt ≤2); `resume_versions` (`ai_tailored`); diff view; `DocumentRenderer` (md→pdf/docx); `resume_suggestions` in Workspace | tailor for a job → new version, diff visible, no unsupported claims |
| **9 · Cover letter + email generation** | application documents | `cover_letter` node; `email_draft` node; `application_emails` (draft); generation eval (LLM-judge rubrics + deterministic groundedness/keyword coverage) added to `/eval` | builder steps 3–4 produce a grounded letter + drafted email |
| **10 · Human approval workflow** | the gate | `application_prep` node; `approval_requests` (snapshot + hash); `human_approval` `interrupt`; `/approvals` (approve/reject/edits→reconfirm); `email_external_action` (assert approved + hash); `EmailSender` console default; resume-from-interrupt; audit + `ai_actions` on send; 7-step Builder UI + approval card (desktop + mobile) + success state | Prepare Application → review → Approve & Send → "sent at 10:42 AM" + audit log; no send without approved row; hash mismatch halts |
| **11 · Application tracker** | pipeline visibility | Kanban (Saved/Applied/Interview/Offer/Rejected); drag = status change + `application_events` + audit; application detail (résumé version, letter, email, timeline, AI reasoning, notes); notes | approved application lands in "Applied"; detail shows full history |
| **12 · Career insights** | forward-looking guidance | aggregate `skill_gaps`; `roadmap` planner (RAG over `learning_resources`, streamed milestones); `/insights` composition; Insights page; milestone progress → re-scoring | Insights shows real strengths/gaps; roadmap milestones link to catalog entries |
| **13 · Testing + security hardening** | production confidence | coverage raise (unit/integration/e2e); prompt-injection suite; rate-limit tests; authz/isolation tests; secret-redaction tests; agent action-limit tests; load smoke; `pip-audit`/`npm audit`; `SECURITY.md`; threat model | CI gates on lint/types/coverage/eval thresholds/no criticals |
| **14 · Docker + deployment** | one-command bring-up | multistage Dockerfiles; `compose.prod.yml` + nginx/TLS; migration entrypoint; healthcheck-gated startup; `seed` command; complete `.env.example`; backup notes; runbook; deploy doc | clean machine: `docker compose -f compose.prod.yml up` → smoke passes |

---

## 10. Cross-cutting: Evaluation, Observability, Security

### 10.1 Evaluation (`eval/`)

- **Retrieval** — recall@k, precision@k, MRR, nDCG against a labeled query→relevant-chunk golden set (`eval/datasets/retrieval/`). Gate in CI from Phase 6.
- **Generation** — LLM-as-judge rubrics (groundedness/faithfulness, relevance, completeness, tone) + deterministic checks (claim-to-source coverage %, forbidden-fabrication scan, schema validity, JD keyword coverage). Gate from Phase 9.
- **Matching** — monotonicity/sanity tests on synthetic pairs; stability under paraphrase; explainer-doesn't-move-the-number assertion. From Phase 5.
- **Online** — thumbs up/down + edit-distance between generated doc and the exported version, captured as implicit labels.
- Runs as `eval/run.py` (CLI) + CI job + `POST /eval/runs`; writes `eval_runs`/`eval_results`; dashboard charts quality over time.

### 10.2 Observability

structlog JSON logs with `request_id`/`run_id`/`user_id` + PII redaction filter; OpenTelemetry traces spanning API → worker → LLM; per-call token + cost meter aggregated onto `ai_sessions.totals` and `agent_steps`; `/health/ready` checks DB, Redis, provider reachability, migration head; `task_failures` dead-letter table + `/ops/tasks/failures`.

### 10.3 Security

Per §2.7 table. Additionally: dependency scanning in CI (`pip-audit`, `npm audit`) as a gate from Phase 13; `threat-model.md` covering résumé PII, prompt injection via JD/web content, approval-gate bypass attempts, and cross-user access; secrets only via env + a redaction test that fails if a secret-shaped string reaches logs.

---

## 11. Decisions Log

| # | Decision | Rationale |
|---|---|---|
| D1 | Modular monolith (FastAPI API + ARQ worker + Next.js), one repo, strict internal boundaries | Satisfies every architecture requirement without microservice ops tax at portfolio scale; isolation via interfaces. |
| D2 | Portfolio/demo scope — real auth + per-user isolation, not operated at scale | Matches stated goal; avoids multi-tenant/billing complexity. |
| D3 | Manual-only job ingestion + shipped **demo job dataset** (Option A) | Keeps the no-scraping decision intact while making Discovery/Matching/Tracker demonstrable on first launch. |
| D4 | LLM behind `LLMProvider` — Anthropic default, OpenAI + Gemini + fake adapters | Brief §22; enables offline tests and vendor swap via one env var. |
| D5 | Agent may draft **and send** application emails, only after an `approved` `approval_requests` row with a matching `payload_hash` | Brief §7; the gate is structural, not advisory. |
| D6 | `EmailSender` console/sandbox adapter is the default | Demos never email real recruiters; real send is one env var. |
| D7 | Deterministic scorer; LLM only narrates | Brief §4 — the score must be explainable and reproducible. |
| D8 | Mana AI returns typed **response blocks**, not markdown-to-parse | Brief §3/§16 — conversation + interactive UI without brittle prose parsing. |
| D9 | ARQ worker (Celery is a documented swap) | Async-native, lighter; swap is an interface reimplementation. |
| D10 | Next.js App Router + TS + Tailwind + shadcn/ui + Lucide + TanStack Query | Brief §22. |
| D11 | pgvector for both relational + vector + LangGraph checkpoints; Redis is ephemeral only | One durable store; simpler ops. |
| D12 | 15 named tables from brief §24 kept; supporting tables added (`resume_chunks`, `job_chunks`, `match_components`, `approval_requests`, `messages`, `agent_steps`, `application_events`, `company_research`, `learning_resources`, `roadmap_milestones`, `task_failures`, `eval_*`) | Named tables are the spine; the rest are required by the flows. |

---

## 12. Open items (resolve during their phase, not blocking)

- Embedding model + `EMBED_DIM` final choice (Phase 0/6) — parameterized; changing means a reindex.
- OCR adapter implementation vs stub (Phase 2 ships a stub; real OCR optional later).
- GitHub OAuth (optional, Phase 1 — email/password is the baseline).
- `pdf` rendering library for generated documents (Phase 8 — evaluate WeasyPrint vs a headless approach).
- Demo job dataset authoring (Phase 4 — ~60–100 postings, hand-curated, labeled sample data).
