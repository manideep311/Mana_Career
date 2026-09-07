# Phase 12a — Career insights (backend) design addendum

> Delta over master `2026-08-30-mana-career-design.md` §1.4 (Next Best Action), §1.5 (`roadmap/`), §3.2 J5, §6.2 (`/skill-gaps`, `/roadmaps`, `/insights`, `/learning-resources`), §9 row 12. Phase 12 is the forward-looking guidance layer. This addendum covers the **backend**; Phase 12b is the Insights page + roadmap timeline UI.

## 0. Goal (roadmap row 12, backend)

Everything the Insights page and the learning-roadmap flow read or mutate: aggregate skill-gap rollup, a seeded `learning_resources` catalog, a `RoadmapPlanner` that turns ranked gaps into sequenced milestones grounded in real catalog entries (streamed milestone-by-milestone), the `/roadmaps` + `/learning-resources` APIs, and the `/insights` composition endpoint.

## 1. Rulings

**R1 — split.** Phase 12 → **12a** (this addendum, backend) + **12b** (Insights page, roadmap timeline UI, streamed-milestone consumer, mark-done). No behaviour in 12a depends on 12b.

**R2 — skill-gap aggregate is deterministic, synchronous, delete-then-insert.** `POST /skill-gaps/aggregate` (200, not 202 — it is a cheap DB rollup, no LLM, no queue). `MatchService.aggregate_skill_gaps(user_id)`:
1. `DELETE FROM skill_gaps WHERE user_id = :u AND scope = 'aggregate'`.
2. Select every `scope='job'` gap for the user (join through `job_matches` for ownership). Group by `skill_id`: `skill_slug`/`skill_label` from any row; `frequency` = count of **distinct `job_match_id`** with that skill gapped; `severity` = the most severe across the group (`critical` > `important` > `nice_to_have`); `rationale` = `f"Missing in {frequency} of your job matches."`.
3. Insert one `scope='aggregate'` row per skill (`job_match_id=NULL`, `status='open'`, `addressed_by_roadmap_id=NULL`).
No new index — the existing `uq_skill_gaps_job_skill` is on `(job_match_id, skill_id)` and does not constrain `job_match_id IS NULL` rows in Postgres, so nothing conflicts; ordering/uniqueness of aggregate rows is guaranteed by the delete-first step. `GET /skill-gaps?scope=aggregate` already works (the router passes `scope` straight through) — verify `MatchService.list_skill_gaps` orders aggregate rows by severity rank then `frequency DESC`.

**R3 — `learning_resources` is a seeded shared catalog.** New table (migration `0015`). Seed data is hand-authored `app/domain/roadmap/learning_resources.json` (~50 entries spanning the taxonomy's most-gapped skills — courses, docs, books, a few "build X" projects). `seed_learning_resources(session=None)` in `app/seed.py`, same dual-path shape as `seed_skills`: for each entry embed `f"{title}. {summary} Skills: {', '.join(skills)}"` via `get_embeddings_provider(settings)`, `insert(...).on_conflict_do_update(index_elements=["url"], set_=...)`. `python -m app.seed learning` + folded into the `all` branch. Columns: `id · title String(200) · provider String(120) · url String(500) unique · type CHECK in ('course','book','doc','video','article','project') · skills text[] not null default '{}' · level CHECK in ('beginner','intermediate','advanced') · est_hours int null · cost CHECK in ('free','paid','freemium') · summary text not null · embedding Vector(1024) · is_active bool not null default true · TimestampMixin`. Indexes: HNSW `vector_cosine_ops` on `embedding`, GIN on `skills`, btree on `level`.

**R4 — `RoadmapPlanner` lives in a new `app/domain/roadmap/` package; direct pgvector, one LLM call per milestone.** `RoadmapPlanner(session, *, llm: LLMProvider, embeddings: EmbeddingsProvider)`. `async plan(user_id, *, scope, job_id, constraints, publish) -> uuid.UUID` where `publish: Callable[[dict], Awaitable[None]]` emits SSE frames:
1. Load the recommendation row (created by the route, status `planning`).
2. Pull the user's aggregate `skill_gaps` (run R2's rollup first if none exist), take the top **6** by severity-rank then `frequency DESC`.
3. Per gap, in order: embed `f"Learn {skill_label}"`, `SELECT ... FROM learning_resources WHERE is_active ORDER BY embedding <=> :q LIMIT 8`, then keep the ≤3 whose `skills` array overlaps the gap's `skill_slug` OR (if none overlap) the top 3 by distance. ONE `llm.complete(...)` call with a strict JSON schema → `{why_it_matters: str, est_hours: int, practice_project: str, checkpoint: str}`, prompt includes ONLY the retrieved resources (id, title, provider, url, summary) and instructs "recommend only from this list". Drop the milestone entirely if the model returns empty `why_it_matters`; clamp `est_hours` to `[1, 200]`.
4. Insert the `roadmap_milestones` row (`order_index` = loop index, `resource_ids` = the retrieved ids, `status='not_started'`), `flush`, then `await publish({"event": "milestone", "milestone": <serialised>})`.
5. After the loop: set `learning_recommendations.status='active'`, `summary` = `f"{n} milestones to close your top skill gaps."`, `next_step` = the first milestone's `title`, `flush`, `await publish({"event": "done", "status": "active", "id": str(rec_id)})`.
On any exception: set `status='archived'`, `generation_meta={"error": str(e)}`, `await publish({"event": "error", "message": "We couldn't build your roadmap."})`, re-raise so ARQ records the failure. `RoadmapPlanner` is a `domain` leaf: imports `app.core.*`, `app.models.*`, `app.domain.llm.*`, `app.domain.embeddings.*` (all same layer / lower). It does **not** import `app.domain.rag` (a direct `embedding <=> :q` query is enough) → `lint-imports` stays `3 kept, 0 broken`.

**R5 — `/roadmaps` API + a dedicated SSE relay, mirroring `/jobs/{id}/events`.**
- `POST /roadmaps` `{scope: "aggregate"|"job", job_id?: uuid, constraints?: dict}` → **202** `RoadmapRefOut{id}`. Creates the `learning_recommendations` row (`status='planning'`, `title` = `"Learning roadmap"` or `f"Roadmap for {job.title}"` when `job_id` resolves), `await db.commit()`, enqueues `plan_roadmap` with `_job_id=f"plan_roadmap:{rec_id}"`.
- `GET /roadmaps` → `RoadmapListOut{items: RoadmapOut[]}` (the user's recommendations, `status != 'planning'` optional filter, newest first).
- `GET /roadmaps/{id}` → `RoadmapDetailOut` = `RoadmapOut` + `milestones: MilestoneOut[]` (ordered by `order_index`).
- `GET /roadmaps/{id}/events` → `EventSourceResponse`. Ownership check in a short-lived `AsyncSessionLocal` (404 non-owners before streaming), then relay `roadmap_channel(id)` via a `status_stream`-style loop with `terminal={"active","archived"}`. On `open`, read the current `status` + any milestones already written and replay them as `milestone` frames (so a late subscriber isn't stuck), then stream live frames.
- `PATCH /roadmaps/{id}` `{status: "active"|"archived"}` → `RoadmapOut`.
- `PATCH /roadmaps/{id}/milestones/{mid}` `{status: "not_started"|"in_progress"|"done"}` → `MilestoneOut`. On `done`: set `completed_at = now()`; for each `skill_slug` the milestone targets, set the user's matching `scope='aggregate'` `skill_gaps` row to `status='closed'`, `addressed_by_roadmap_id = <rec_id>` (the minimal re-scoring hook — master J5). On any other status: clear `completed_at`; if it was `done`, reopen the gap (`status='open'`, `addressed_by_roadmap_id=NULL`).

**R6 — `/learning-resources` is a shared read.** `GET /learning-resources?skills=<csv>&level=<one>` → `list[LearningResourceOut]` (cap 50). Filters: `is_active`, `skills &&` array-overlap when `skills` given, `level =` when given. Auth required (`CurrentUser`) but **not** user-scoped. Order by `level` then `est_hours NULLS LAST`.

**R7 — `/insights` `GET /` is pure composition, no LLM, one endpoint.** New `app/domain/insights/` package: `ranker.py` (`next_best_action(session, user_id) -> NextStep | None`) + `InsightsService(session).compose(user_id) -> InsightsOut`. `InsightsOut`:
- `strengths: list[SkillMention]` — from the user's `job_matches` `strengths` jsonb across their most recent scored matches, deduped by skill, cap 6. `SkillMention{skill_slug, skill_label, detail}`.
- `skills_to_develop: list[SkillGapOut]` — aggregate `skill_gaps` (lazily run R2's rollup if zero aggregate rows AND `≥1` job match), severity-rank then `frequency DESC`, cap 8.
- `recommended_next_step: NextStep | None` — `NextStep{kind, title, reason, entity_type, entity_id}`. Ranker candidates, first match wins: (a) an `applications` row in `awaiting_approval` → "Review an application that's ready to send"; (b) `≥1` job match but zero aggregate gaps → "Refresh your skill-gap analysis"; (c) an active `learning_recommendation` with a `not_started` milestone → "Start your next learning milestone"; (d) `<3` jobs tracked → "Add a job you're interested in"; (e) an `applied` application with `last_status_change_at` older than 14 days → "Follow up on a stale application"; else `None`.
- `trending_skills: list[SkillMention]` — most frequent slugs in `jobs.required_skills` across `status='ready'` jobs (seed + the user's), cap 10, `detail = f"in {count} roles"`.
- `suggested_projects: list[str]` — `practice_project` of the user's active roadmap's `not_started`/`in_progress` milestones, cap 4.
- `roadmap_summary: RoadmapSummary | null` — `{id, title, next_step, milestones_done, milestones_total}` from the newest `status='active'` `learning_recommendation`, else `null`.

`InsightsService`/`ranker` are `domain` leaves (import `app.core.*`, `app.models.*` only — **not** sibling domains; the ranker reads tables directly). `lint-imports` stays 3/0.

**R8 — one migration, `0015_learning_roadmap`.** Creates `learning_resources`, `learning_recommendations`, `roadmap_milestones` (+ their `set_updated_at` triggers, since all three carry `TimestampMixin` — mirror `0013`'s `op.execute("CREATE TRIGGER trg_..._set_updated_at ...")`). No change to `skill_gaps`.

## 2. API surface

New router `app/api/v1/roadmaps.py` (`/roadmaps` + `/learning-resources` — one module, two prefixes via two routers, or one router with both path groups), `app/api/v1/insights.py`, and additions to `app/api/v1/skill_gaps.py`. Register all in `app/api/v1/router.py`.

- `POST /skill-gaps/aggregate` → **200** `list[SkillGapOut]` (the freshly-built aggregate rows). (R2)
- `GET /skill-gaps?scope=aggregate` — already routed; confirm ordering. (R2)
- `POST /roadmaps` `{scope, job_id?, constraints?}` → **202** `RoadmapRefOut{id}`. (R5)
- `GET /roadmaps` → `RoadmapListOut`. `GET /roadmaps/{id}` → `RoadmapDetailOut`. `GET /roadmaps/{id}/events` → SSE. (R5)
- `PATCH /roadmaps/{id}` `{status}` → `RoadmapOut`. `PATCH /roadmaps/{id}/milestones/{mid}` `{status}` → `MilestoneOut`. (R5)
- `GET /learning-resources?skills=&level=` → `list[LearningResourceOut]`. (R6)
- `GET /insights` → `InsightsOut`. (R7)

Schemas in new `app/api/v1/schemas/roadmaps.py` + `app/api/v1/schemas/insights.py`. `RoadmapOut{id, scope, job_id|null, title, summary|null, next_step|null, status, created_at, updated_at}`. `MilestoneOut{id, order_index, skill_slug, skill_label, title, why_it_matters, resource_ids: list[uuid], est_hours|null, practice_project|null, checkpoint|null, status, completed_at|null}`. `LearningResourceOut{id, title, provider, url, type, skills: list[str], level, est_hours|null, cost, summary}`.

## 3. Worker + events

- `app/worker/tasks/roadmap.py`: `async def plan_roadmap(ctx, rec_id: str) -> None` — opens `AsyncSessionLocal`, loads the recommendation (guard: not found / not `planning` → return), builds `publish` = a closure that `redis.publish(roadmap_channel(rec_id), json.dumps(frame))`, calls `RoadmapPlanner(session, llm=get_llm_provider(s), embeddings=get_embeddings_provider(s)).plan(...)`, `await session.commit()`. Register in `app/worker/main.py` `WorkerSettings.functions` and `app/worker/tasks/__init__.py` `__all__` (sorted).
- `app/core/events.py`: add `def roadmap_channel(rec_id: str) -> str: return f"sse:roadmap:{rec_id}"`.
- `AgentService.enqueue` is the generic enqueue; roadmaps use the same `enqueue("plan_roadmap", rec_id, _job_id=...)` helper the other domains use (`app.domain.*.service.enqueue`). Put the enqueue call in a tiny `app/domain/roadmap/service.py` `RoadmapService` (create row + enqueue + the PATCH/list/get reads) so the route stays thin and the autouse `_no_enqueue` conftest fixture can patch `app.domain.roadmap.service.enqueue`.

## 4. Out of scope (→ 12b or later)

The Insights page, the roadmap timeline component, the streamed-milestone hook, mark-done UI (all 12b). LLM-written Next-Best-Action framing (12a returns the deterministic `reason` string). Roadmap re-generation / milestone re-run. Per-`job` scoped roadmaps beyond storing `job_id` (the planner still uses aggregate gaps in 12a). `learning_resources` admin CRUD. Real course-catalog integration (the seed JSON is the catalog). Spaced-repetition / calendar. `trending_skills` time-windowing.
