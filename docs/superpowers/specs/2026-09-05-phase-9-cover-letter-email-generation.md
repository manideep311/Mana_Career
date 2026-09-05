# Phase 9 — Cover letter + email generation (backend) design addendum

> Delta over master `2026-08-30-mana-career-design.md` §4.2/§4.3/§5.3/§9 (roadmap row 9), written against the codebase as it actually stands after Phase 8b (`main@7d79310`), not the master's indicative sketch. Frontend/UI is explicitly out of scope — see §6.

## 0. Goal (roadmap row 9)

Two new bounded agent nodes — `cover_letter` and `email_draft` — that turn a tailored résumé into a grounded cover letter and a drafted application email, behind a new `prepare_application` goal. Plus a `generation` eval suite (deterministic groundedness/keyword-coverage + an LLM-judge plumbing check) added to `/eval`.

**Explicitly NOT this phase** (roadmap rows 10+): `application_prep`, `human_approval` (the interrupt), `email_external_action` (actually sending), the `applications` table, `approval_requests`, and any UI. The `prepare_application` goal's graph chain this phase builds stops at `respond` — Phase 10 extends the *same* goal's chain further (adding `application_prep → human_approval → email_external_action` after `email_draft`), it does not introduce a new goal.

## 1. Rulings made before any task was planned

**R1 — generalize `ClaimValidator`, don't duplicate it.** `ClaimValidator.check()` currently takes a `ResumeExtraction` and extracts résumé-shaped claim lines internally ([tailoring.py:80](../../../backend/app/domain/resume/tailoring.py)). The master spec reuses `claim_validator` as a generic step after *both* `resume_tailoring` and `cover_letter` (§4.2), so the checker itself must become domain-agnostic. Fix: extract the résumé-specific claim-line extraction into a standalone `_resume_claim_lines(tailored: ResumeExtraction) -> list[str]`; `ClaimValidator.check()` now takes `claim_lines: list[str]` directly. `tailor_resume()` becomes `validator.check(_resume_claim_lines(tailored))`; the résumé `claim_validator` node updates its one call site the same way. `ClaimValidator`/`ClaimReport`/`_split_sentences`/`_STOPWORDS`/`_MIN_SUPPORT` stay in `app/domain/resume/tailoring.py` (no file move — moving them to `generation/` would be a bigger, unnecessary diff for a signature change) and `app/domain/generation/cover_letter.py` imports `ClaimValidator`, `ClaimReport`, `_split_sentences` from there. This is allowed by the import-linter contracts: `generation` importing from `resume` is the same shape as the already-approved `documents → resume` import for `ResumeExtraction` (Phase 8a spec §1's Global Constraints).

**R2 — reuse `resume_tailoring`, don't fork it.** `prepare_application`'s chain starts with the *same* `resume_tailoring` node Phase 8a built — no new résumé-tailoring code. The node already honors `inputs.resume_id` (Phase 8b hotfix `da13755`) and is goal-agnostic (it never reads `state["goal"]`).

**R3 — a second `claim_validator`-shaped node, not a parameterized one.** The existing `claim_validator` node re-reads `state["tailored_resume_version_id"]` specifically ([claim_validator.py](../../../backend/app/domain/agents/nodes/claim_validator.py)) — it is not currently reusable by name because LangGraph node registration is per-name, and this node's job (re-check + log) is intentionally single-purpose per the existing file's own docstring. Rather than branch one function on which artifact it's checking, add a sibling `letter_claim_validator` node with the same "re-check + log a summary" shape but reading `state["cover_letter_id"]` and checking the letter's content against the same sources `write_cover_letter` used. A tiny shared helper (`_log_claim_summary`) avoids duplicating the summary-string/status logic between the two node files.

**R4 — reuse `ApplicationDraftBlock`, extend it.** `app/domain/agents/blocks.py` already declares `ApplicationDraftBlock(kind="application_draft", application_id: uuid.UUID)` (Phase 7a) — but no `applications` row exists until Phase 10. Mirrors Phase 8a's `ResumeSuggestionBlock.suggestion_id` reuse exactly: extend the block to `application_id: uuid.UUID | None = None`, `resume_version_id: uuid.UUID | None`, `cover_letter_id: uuid.UUID | None`, `email_draft_id: uuid.UUID | None`. `respond`'s new branch populates the three artifact ids and leaves `application_id` `None`; Phase 10 populates it once `application_prep` exists. This is an additive, backward-compatible field change (nothing currently constructs `ApplicationDraftBlock`).

**R5 — no `applications` FK yet.** `cover_letters.application_id` and `application_emails.application_id` are bare nullable `uuid` columns with no FK — identical precedent to `resume_versions.application_id` (migration `0011`, [resume_version.py:51](../../../backend/app/models/resume_version.py)). `cover_letters.resume_version_id` is likewise a bare nullable `uuid` (no FK) for the same "loose optional cross-reference" reason, even though `resume_versions` itself already exists — keeping every optional cross-reference in this schema uniformly FK-less avoids ON-DELETE-semantics questions with no present benefit.

**R6 — `application_emails.to_email`/`to_name`/`provider` are nullable, contra the master's indicative (non-`?`) column list.** Phase 9 has no recipient-inference or send capability — a `draft`-status email genuinely has no recipient yet and no provider yet. Nullable is more honest than a placeholder empty string; Phase 10's review step is exactly where a human fills these in before approval.

**R7 — no new API endpoint this phase.** Unlike `tailor_resume` (Phase 8a), which needed a `POST /resumes/{id}/tailor` because a real "Tailor résumé for this job" button already existed to call it from, `prepare_application` has no UI trigger yet — the real "Prepare Application" button is a Phase 10 deliverable (its Builder UI is explicitly Phase 10's own roadmap-row scope). Building a trigger endpoint now means guessing at a URL shape Phase 10 might reshape anyway (e.g. once `applications` exists, the natural route is probably `POST /applications` or `POST /jobs/{id}/prepare-application`, not decidable yet). Verified instead via a worker-level DB integration test that calls `AgentService.start_run(goal="prepare_application", ...)` + `run_agent(...)` directly, mirroring `tests/worker/test_tailoring_task.py` exactly. `AgentService.start_run` already accepts any `AgentGoal` value with no allowlist (verified in Phase 7a), so no service-layer change is needed to make this callable.

**R8 — the `generation` eval suite gates CI on deterministic metrics only.** Under `LLM_PROVIDER=fake`, `FakeLLMProvider.complete(schema=X)` (no `scripted` list configured) returns every field stubbed to its type's zero-value ([fake.py:9](../../../backend/app/domain/llm/adapters/fake.py)) — so a fake-provider cover letter is `content=""`. There is no lexical-fallback arm here the way retrieval's tsv search gives a real signal under fake embeddings ([retrieval.py:1](../../../backend/eval/suites/retrieval.py) docstring) — generation has literally nothing to draft without a real model. So: the suite always runs the full pipeline (deterministic groundedness + keyword-coverage metrics, *and* an LLM-judge call proving that leg of the pipeline works end-to-end and persists a score), but `passed` under the default/CI tier is computed from a floor calibrated to what `fake` actually produces (trivially satisfied — this is a plumbing check, not a quality gate, exactly like every other `fake`-provider test in this repo per the Global Constraint "tests assert plumbing, never LLM output quality"). A separate `QUALITY_*` floor tier (unused in CI, mirrors retrieval's `QUALITY_RECALL_AT_10` etc.) is defined for a future manual run against a real provider.

## 2. New/changed types and signatures

`app/domain/resume/tailoring.py` — `ClaimValidator.check(self, claim_lines: list[str]) -> ClaimReport` (was `check(self, tailored: ResumeExtraction)`); new `_resume_claim_lines(tailored: ResumeExtraction) -> list[str]` (the extracted body of the old `check`); `tailor_resume()`'s one call site becomes `validator.check(_resume_claim_lines(tailored))`.

`app/domain/generation/cover_letter.py` (new):
```python
class CoverLetterDraft(BaseModel):
    content: str  # full letter body, plain text, paragraphs separated by \n\n

async def write_cover_letter(
    *, gen: GenerationService, base: ResumeExtraction, profile_summary: str,
    job_brief: str, tone: str = "professional",
) -> tuple[CoverLetterDraft, GenerationMeta]: ...
```
Same reprompt-loop shape as `tailor_resume` (`MAX_CLAIM_REPROMPTS` reused from `app.domain.resume.tailoring`), same `_collect_sources`-style source-gathering (a *new*, cover-letter-local `_collect_sources` — job posting text is also a valid grounding source for a cover letter, unlike a résumé tailoring where the job is what you're tailoring *toward*, not a claim source; keep this one local rather than sharing tailoring.py's, since the source sets legitimately differ).

`app/domain/generation/email_draft.py` (new):
```python
class EmailDraft(BaseModel):
    subject: str
    body: str

async def draft_email(
    *, gen: GenerationService, job_title: str, company: str,
    applicant_name: str, cover_letter_content: str,
) -> tuple[EmailDraft, GenerationMeta]: ...
```
Single `gen.generate()` call, no reprompt loop, no `ClaimValidator` (node catalog: `email_draft` has no `claim_validator` after it — an email that restates an already-grounded cover letter introduces no new claims worth re-checking).

`app/domain/agents/blocks.py` — `ApplicationDraftBlock` gains `application_id: uuid.UUID | None = None`, `resume_version_id: uuid.UUID | None = None`, `cover_letter_id: uuid.UUID | None = None`, `email_draft_id: uuid.UUID | None = None` (all now optional; the class keeps its existing `kind` literal).

`app/domain/agents/state.py` — no new `ManaState` keys (`cover_letter_id`/`email_draft_id`/`application_id` already exist, unused, from Phase 7a) and no new `AgentGoal` value (`"prepare_application"` already exists, unused). Only `NODE_ORDER` gains `"cover_letter", "letter_claim_validator", "email_draft"` inserted before `"respond"`.

## 3. Migration `0012_application_documents` + models

`app/models/application.py` (new; `models/__init__` imports it as `application` right after `ai`, before `audit` — alphabetical).

**`cover_letters`**: `id` uuid pk `gen_random_uuid()` · `user_id` FK `users.id` CASCADE not null · `job_id` uuid not null (no FK — mirrors `resume_versions.job_id`) · `application_id` uuid null (no FK, R5) · `resume_version_id` uuid null (no FK, R5) · `tone` String(24) not null server_default `'professional'` · `content` Text not null · `content_json` JSONB not null `'{}'` · `rendered_refs` JSONB not null `'{}'` (unpopulated this phase — no cover-letter renderer yet, same "declared, not yet used" pattern as `resume_chunks` in Phase 8a) · `generation_meta` JSONB not null `'{}'` · `version` Integer not null server_default `1` · `supersedes_id` uuid null (no FK) · `created_by` String(16) not null server_default `'mana_ai'` + CHECK `in ('user','mana_ai')` · `TimestampMixin`. Indexes: `ix_cover_letters_user` (`user_id`, `created_at DESC`), `ix_cover_letters_job` (`job_id`). `updated_at` trigger.

**`application_emails`**: `id` · `user_id` FK CASCADE not null · `application_id` uuid null (no FK, R5) · `job_id` uuid not null (no FK) · `to_email` String(320) null (R6) · `to_name` String(200) null · `cc` `text[]` not null `'{}'` · `bcc` `text[]` not null `'{}'` · `subject` String(300) not null · `body` Text not null · `body_format` String(8) not null server_default `'plain'` + CHECK `in ('plain','html')` · `attachment_refs` JSONB not null `'{}'` · `status` String(16) not null server_default `'draft'` + CHECK `in ('draft','awaiting_approval','approved','sending','sent','failed','canceled')` · `provider` String(16) null (R6) · `provider_message_id` String(200) null · `sent_at` timestamptz null · `send_error` Text null · `generation_meta` JSONB not null `'{}'` · `TimestampMixin`. Indexes: `ix_application_emails_user` (`user_id`, `created_at DESC`), `ix_application_emails_job` (`job_id`). `updated_at` trigger. `cc`/`bcc` use `sqlalchemy.dialects.postgresql.ARRAY(Text)` — mirror the existing `profile_experiences.highlights`/`job.responsibilities` precedent ([profile.py:51](../../../backend/app/models/profile.py), [job.py:103](../../../backend/app/models/job.py)) exactly, including `server_default=text("'{}'")`.

Migration: `revision="0012_application_documents"`, `down_revision="0011_resume_tailoring"`. Create order `cover_letters` → `application_emails`; downgrade reversed with `DROP TRIGGER IF EXISTS` before each `drop_table`. Mirror `0011_resume_tailoring.py`'s style exactly (it is the freshest, most-reviewed precedent).

## 4. Agent nodes + graph wiring

`app/domain/agents/nodes/cover_letter.py` — mirrors `resume_tailoring.py`'s shape: loads the job (via `JobService`), the same résumé/profile summarization already exists in `resume_tailoring.py`'s `_summarise_profile`/`_summarise_job` — **do not duplicate them**; this node imports and reuses both (they are already generic and take a `Job`/`CareerProfile`, not résumé-specific data). Loads the tailored résumé from `state["tailored_resume_version_id"]` (falls back to the base résumé's `ResumeExtraction` if the goal ever runs with no prior tailoring step — defensive, though `prepare_application`'s chain always runs `resume_tailoring` first). Calls `write_cover_letter`, persists a `cover_letters` row, sets `state["cover_letter_id"]`, logs an action, bumps budget inline (Phase-7a convention, no helper).

`app/domain/agents/nodes/letter_claim_validator.py` — re-checks the persisted cover letter's content against the same sources, logs a summary. Never halts (matches the résumé `claim_validator`'s contract).

`app/domain/agents/nodes/email_draft.py` — loads the cover letter + job, calls `draft_email`, persists an `application_emails` row (`status="draft"`), sets `state["email_draft_id"]`, logs an action, bumps budget inline.

`app/domain/agents/nodes/supervisor.py` — add `if goal == "prepare_application": return {"_route": "resume_tailoring", "_summary": "Routing: prepare an application"}`.

`app/domain/agents/graph.py` — add the 3 new nodes (guard-wrapped, same as every worker node). Replace the flat `claim_validator → respond` edge with a goal-aware router:
```python
def _after_resume_claim_check(state: ManaState) -> str:
    if state.get("status") in {"halted", "error"}:
        return "halted"
    return "cover_letter" if state.get("goal") == "prepare_application" else "respond"
```
`claim_validator`'s conditional-edges map becomes `{"cover_letter": "cover_letter", "respond": "respond", "halted": "halted"}`. Then `cover_letter → letter_claim_validator → email_draft → respond`, each via the existing `_halt_or(...)` helper (unchanged). Module docstring's node/worker-node counts get another refresh (now 13 nodes / 11 worker nodes).

`app/domain/agents/nodes/respond.py` — new FIRST branch (checked before the existing `tailored_resume_version_id` branch, since a `prepare_application` run has both set): `if state.get("email_draft_id"): blocks = [TextBlock(...), ApplicationDraftBlock(resume_version_id=..., cover_letter_id=..., email_draft_id=..., application_id=None)]`.

## 5. Generation eval suite

`eval/datasets/generation/golden_v1.jsonl` — 4-5 cases, each `{id, resume: <ResumeExtraction-shaped dict>, job: {title, company, description, required_skills}, expected_keywords: [...]}` (the job's own required-skill labels + a couple of job-title/company tokens — words a grounded cover letter *should* plausibly mention).

`eval/suites/generation.py` — `run_generation_suite(session, *, llm_provider: str, write_db: bool, git_sha: str) -> GenerationEvalReport`, mirroring `run_retrieval_suite`'s shape (`ensure_corpus`-equivalent: get-or-create an eval user, no seeding needed — cases carry their own résumé/job payloads inline, not DB rows). Per case: call `write_cover_letter` + `draft_email` through a real `GenerationService(get_llm_provider(settings))`; compute `groundedness = ClaimValidator(sources).check(_split_sentences(content)).supported_ratio`; compute `keyword_coverage = len(matched) / len(expected_keywords)` (case-insensitive substring match of each expected keyword against the letter+email body); call a `JudgeVerdict` schema (`{score: float, rationale: str}`) through the same `GenerationService` as the "LLM-judge" leg (R8 — its score is not gated in CI). `passed = groundedness >= GROUNDEDNESS_FLOOR and keyword_coverage >= KEYWORD_COVERAGE_FLOOR` per case; aggregate `passed = all(...)`.

`eval/thresholds.py` gains `GROUNDEDNESS_FLOOR = 1.0`, `KEYWORD_COVERAGE_FLOOR = 0.0`, `QUALITY_GROUNDEDNESS = 0.85`, `QUALITY_KEYWORD_COVERAGE = 0.5` (R8 — the non-quality floors are calibrated to what `fake` deterministically produces: an empty letter has `checked=0` claim lines → `ClaimReport.supported_ratio` is defined as `1.0` when `checked == 0` ([tailoring.py:102-104](../../../backend/app/domain/resume/tailoring.py)), and zero keyword matches → coverage `0.0`; both floors are set to exactly what `fake` yields, same calibration philosophy as retrieval's own comment about its golden set).

`eval/run.py` — `choices=["retrieval", "generation"]`; dispatch to `run_generation_suite` when selected, printing its own metric/floor table.

`.github/workflows/ci.yml` `eval` job — add `- run: uv run python -m eval.run generation --write-db` (same env block as the existing retrieval step) after the retrieval step.

`app/api/v1/schemas/eval.py` `EvalRunIn.suite` widens from `Literal["retrieval"]` to `Literal["retrieval", "generation"]`; `app/api/v1/eval.py`'s `create_eval_run` dispatches on `body.suite` instead of hardcoding `run_retrieval_suite`.

## 6. Out of scope (frontend + everything Phase 10 owns)

No new UI, no new API trigger endpoint (R7). No `applications`/`approval_requests` tables. No `application_prep`/`human_approval`/`email_external_action` nodes. No cover-letter or email rendering (`DocumentRenderer` stays résumé-only; `cover_letters.rendered_refs` stays `{}`). No recipient-address inference. All of the above are Phase 10's roadmap-row scope and will extend the *same* `prepare_application` goal's graph, not introduce a new one.
