# Phase 12b — Career insights (frontend) design addendum

> Delta over master `2026-08-30-mana-career-design.md` §1.3 (Career Insights surface), §3.2 J5 (Plan learning), §6.2 routes (`insights`), §9 row 12. Phase 12a shipped the backend (`GET /insights`, `/roadmaps` + SSE, `/learning-resources`, `POST /skill-gaps/aggregate`) — `main@9792c3c`, CI-green. This phase is the UI.

## 0. Goal

An `/insights` page that answers "Where is my career going?": recommended next step, strengths, skills to develop, a learning roadmap whose milestones stream in as the planner builds them, plus trending skills and suggested projects. Marking a milestone done closes the matching skill gap (backend already does the re-scoring).

## 1. Backend surface consumed (all shipped in 12a)

- `GET /insights` → `{ strengths: SkillMention[], skills_to_develop: SkillGapOut[], recommended_next_step: NextStep | null, trending_skills: SkillMention[], suggested_projects: string[], roadmap_summary: RoadmapSummary | null }`. `SkillMention{skill_slug, skill_label, detail: string|null}`. `NextStep{kind, title, reason, entity_type: string|null, entity_id: string|null}`. `RoadmapSummary{id, title, next_step: string|null, milestones_done: number, milestones_total: number}`. `SkillGapOut` = the existing FE `SkillGap` type (`id, scope, job_match_id|null, skill_slug, skill_label, severity, frequency, rationale|null, status`).
- `POST /skill-gaps/aggregate` → **200** `SkillGap[]` (a manual "recompute my gap rollup").
- `POST /roadmaps` `{scope?, job_id?, constraints?}` → **202** `{id}`.
- `GET /roadmaps` → `{items: Roadmap[]}`. `GET /roadmaps/{id}` → `RoadmapDetail` = `Roadmap & {milestones: Milestone[]}`. `Roadmap{id, scope, job_id|null, title, summary|null, next_step|null, status, created_at, updated_at}`. `Milestone{id, order_index, skill_slug, skill_label, title, why_it_matters, resource_ids: string[], est_hours: number|null, practice_project: string|null, checkpoint: string|null, status, completed_at: string|null}`.
- `GET /roadmaps/{id}/events` → SSE. Frames: `event: milestone` (data = one `Milestone`), then a terminal `event: done` (`{status:"active"|"archived", id}`) or `event: error` (`{message, status:"archived"}`). On connect the relay **replays** every milestone already written, then the terminal frame if the roadmap is no longer `planning`.
- `PATCH /roadmaps/{id}` `{status: "active"|"archived"}` → `Roadmap`.
- `PATCH /roadmaps/{id}/milestones/{mid}` `{status: "not_started"|"in_progress"|"done"}` → `Milestone`.

## 2. Rulings

**R1 — "Insights" nav entry.** `components/layout/nav-items.ts`: insert `{ href: "/insights", label: "Insights", icon: Compass, ready: true }` after the `applications` item, before `assistant`. Import `Compass` from `lucide-react`.

**R2 — `/insights` is one client page composed of sections, all fed by one `useQuery`.** `app/(app)/insights/page.tsx` (`"use client"`) → `<RequireAuth>` + header + `<InsightsView />`. `InsightsView` runs `useQuery({ queryKey: qk.insights, queryFn: () => api.insights.get() })` and renders, in order: `<NextStepCard>`, a two-column `<SkillPanels>` (Strengths | Skills to develop), `<RoadmapSection>`, `<TrendingAndProjects>`. `isPending` → skeletons; `isError` → `<ErrorState onRetry={refetch}>`; the six-key payload always renders (empty arrays get their own tiny empty copy per section — never a bare blank).

**R3 — `<NextStepCard>` is pure; the link mapping is deliberately small.** Props `{ step: NextStep | null }`. `null` → nothing (or a one-line "You're all caught up."). Otherwise a `<Card>` with `step.title` (heading) + `step.reason` (muted). A CTA `<Link>` only for `entity_type === "application"` → `/applications/{entity_id}`; every other `kind` (`refresh_gaps`, `start_milestone`, `add_job`, `follow_up` without an app id) renders text only — no guessed routes. (`refresh_gaps` could wire to the R5 refresh button, but keep the card pure — the Skills panel already surfaces that action.)

**R4 — `<SkillPanels>` — Strengths read-only, Skills-to-develop has a Refresh.** Props `{ strengths: SkillMention[], gaps: SkillGap[] }`. Strengths: chips/rows of `skill_label` + muted `detail`. Skills-to-develop: rows of `skill_label` + a severity badge (`critical`/`important`/`nice_to_have` → danger/warning/muted token) + `rationale`. A `<Button variant="outline" size="sm" loading={...}>Refresh</Button>` on the Skills-to-develop panel header → `useMutation(() => api.skillGaps.aggregate())` → `onSuccess` invalidate `qk.insights`. Empty gaps → "No gaps rolled up yet — Refresh to compute them from your job matches."

**R5 — `<RoadmapSection>` owns the roadmap lifecycle.** Props `{ summary: RoadmapSummary | null }`. Local `const [pendingId, setPendingId] = useState<string | null>(null)`.
- `summary == null && pendingId == null` → empty state: "No learning roadmap yet." + `<Button loading={createMut.isPending}>Build my roadmap</Button>` → `useMutation(() => api.roadmaps.create())` → `onSuccess(ref) => setPendingId(ref.id)` (then the streaming timeline mounts on `pendingId`).
- `pendingId != null` (just created) → `<RoadmapTimeline recommendationId={pendingId} live />` — streams milestones as the planner builds them.
- `summary != null` → header (`summary.title`, a `milestones_done / milestones_total` progress bar, `summary.next_step` line) + `<RoadmapTimeline recommendationId={summary.id} />`.

**R6 — `<RoadmapTimeline>` merges a REST read with the SSE stream.** Props `{ recommendationId: string; live?: boolean }`.
- `roadmapQuery = useQuery({ queryKey: qk.roadmap(recommendationId), queryFn: () => api.roadmaps.get(recommendationId) })`.
- `events = useRoadmapEvents(live || roadmapQuery.data?.status === "planning" ? recommendationId : null)`.
- Milestone list = `events.status === "streaming" || events.milestones.length > (roadmapQuery.data?.milestones.length ?? 0) ? events.milestones : roadmapQuery.data?.milestones ?? []`. When `events.status === "done"` → `roadmapQuery.refetch()` once (a `useEffect` keyed on `events.status`), then render from the query.
- Each row = `<MilestoneRow milestone={m} onStatusChange={(s) => moveMut.mutate({ id: m.id, status: s })} busy={movingId === m.id} />`.
- `moveMut = useMutation({ mutationFn: ({id,status}) => api.roadmaps.patchMilestone(recommendationId, id, status), onMutate: optimistic write into qk.roadmap(recommendationId), onError: rollback + toast, onSettled: invalidate qk.roadmap(recommendationId); additionally on a → "done" transition, invalidate qk.insights })`.
- While `events.status === "streaming"` show a subtle "Building your roadmap…" spinner under the list.

**R7 — `useRoadmapEvents(recommendationId: string | null)`.** New `hooks/useRoadmapEvents.ts` — adaptation of `usePrepareRunEvents` (own `parseFrame` copy, `authedStream(\`/api/v1/roadmaps/${id}/events\`, { headers: { Accept: "text/event-stream" } })`, `/\r\n\r\n|\n\n/` frame split, single-attempt no-reconnect, `cancelled` guard in the effect cleanup). Returns `{ milestones: Milestone[]; status: "idle" | "streaming" | "done" | "error"; error: string | null }`. Frame handling: `milestone` → append to `milestones` **deduped by `id`** (the relay replays), sorted by `order_index`; `done` → `status: "done"` (unless already `error`); `error` → `status: "error"`, `error: message`. On stream close without a terminal frame while still `streaming` → leave `status: "streaming"` is wrong; set `"done"` (the planner may have finished a 0-milestone roadmap and the relay closed) — mirror `usePrepareRunEvents`'s "lost the connection" only when `milestones` is empty AND no terminal frame; otherwise `"done"`.

**R8 — `<MilestoneRow>` is pure.** Props `{ milestone: Milestone; onStatusChange: (s: RoadmapMilestoneStatus) => void; busy?: boolean }`. Renders `order_index + 1`, `skill_label` (chip), `title` (heading), `why_it_matters` (muted), a details line (`est_hours ? "~Nh" : null` · `resource_ids.length` resources · `checkpoint`), `practice_project` in a sub-block, and a native `<select aria-label="Milestone status">` (`Not started` / `In progress` / `Done`) bound to `milestone.status`, `disabled={busy}`, `onChange → onStatusChange(e.target.value)`. `status === "done"` → a check + `completed_at` local date.

**R9 — `<TrendingAndProjects>` is pure, read-only.** Props `{ trending: SkillMention[]; projects: string[] }`. Trending: chips of `skill_label` + `detail` ("in N roles"). Projects: a bulleted list of the strings. Each with its own empty copy.

## 3. Frontend surface

- `lib/api/types.ts` — `SkillMention`, `NextStep`, `RoadmapSummary`, `Insights`, `Roadmap`, `Milestone`, `RoadmapDetail`, `RoadmapMilestoneStatus`, `LearningResource` (the last only if R11's client method is added).
- `lib/api/endpoints.ts` — `api.insights = { get() }`; `api.roadmaps = { list(), get(id), create(body?), patch(id, status), patchMilestone(recId, mid, status) }`; extend `api.skillGaps` with `aggregate()`. (`api.learningResources.list(params?)` optional — R11.)
- `lib/query.ts` — `qk.insights = ["insights"]`, `qk.roadmap = (id) => ["roadmap", id]`, `qk.roadmaps = ["roadmaps"]`.
- `hooks/useRoadmapEvents.ts`.
- `components/insights/`: `NextStepCard.tsx`, `SkillPanels.tsx`, `RoadmapSection.tsx`, `RoadmapTimeline.tsx`, `MilestoneRow.tsx`, `TrendingAndProjects.tsx`, plus `InsightsView.tsx` (the composed body) if the page file gets large.
- `app/(app)/insights/page.tsx`.
- Tests: `tests/api/endpoints.test.ts` (extend); `tests/insights/use-roadmap-events.test.ts`; `tests/insights/next-step-card.test.tsx`; `tests/insights/milestone-row.test.tsx`; `tests/insights/roadmap-timeline.test.tsx`; `tests/insights/insights-page.test.tsx`.

## 4. Conventions (verified against the repo)

- Gates: `pnpm lint` (= `next lint`; NEVER `pnpm exec eslint`), `pnpm exec tsc --noEmit`, `pnpm vitest run`.
- SSE hook: `authedStream` from `useAuth()`; one hook per consumer with its own `parseFrame` copy and `/\r\n\r\n|\n\n/` split; single-attempt, no reconnect (`usePrepareRunEvents` / `useTailorRunEvents` are the models).
- `useMutation` optimistic pattern: `onMutate` cancels + snapshots + writes `qk.roadmap(id)`, `onError` restores + `toast({ variant: "danger" })`, `onSettled` invalidates. Mirror `applications/page.tsx`'s board move.
- Semantic Tailwind tokens only (`accent`, `positive`, `warning`, `danger`, `text`, `text-muted`, `border`, `surface`, …) — no `brand`, no raw palette.
- JSX-text apostrophes must be `&apos;` (`react/no-unescaped-entities`). Attribute-string apostrophes are fine.
- `RequireAuth` from `@/components/auth/RequireAuth`; `ErrorState{title?, onRetry?}`; `Card`/`CardBody`; `Button{variant, size, loading}`; `Skeleton{className}`; `buttonVariants`; `useToast()` → `{ toast }`; `useAuth()` → `{ api }`.
- Test util: `renderWithProviders(ui, { api, authValue, route })` from `@/test/utils`; `mockPush`; RULING R11 (from 10b/11b) — the page-under-test never mocks `useParams`; `@/test/utils` makes it `() => ({})`; import `@/test/utils` **before** the page-under-test so the hoisted `next/navigation` mock registers first.

## 5. Out of scope (→ later)

Drag-and-drop milestone reordering. A roadmap archive/regenerate UI (a small "Archive" link is optional; `PATCH {status:"archived"}` exists but no task needs it). The `POST /roadmaps` `constraints` form (always `{}`). Per-job roadmaps (always `scope="aggregate"`). A `/learning-resources` browse page. Wiring `recommended_next_step` deep-links beyond the `application` case. Insights on the dashboard (this page only).
