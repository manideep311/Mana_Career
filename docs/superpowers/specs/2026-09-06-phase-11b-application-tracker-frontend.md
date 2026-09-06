# Phase 11b — Application tracker (frontend) design addendum

> Delta over master `2026-08-30-mana-career-design.md` §5.3 (Application Tracker), §6.1 J7, §9 roadmap row 11, and the Phase 11a backend as shipped (`main@d402183`, CI green). Phase 11a delivered the full `/applications` resource; this phase is its UI: a Kanban board, an application-detail page with the merged timeline, and the "Applications" nav entry going live.

## 0. Goal

From a signed-in user's point of view: **"Where does each application stand?"** — a board with a column per pipeline stage, cards that move between stages, and a detail view per application showing the tailored résumé / cover letter / sent email, the full merged timeline (`application_events` + `ai_actions` + notes), and a note composer.

## 1. Rulings

**R1 — status change is a `<select>` on the card, not drag-and-drop.** The master (§45, J7) says "drag card between columns". The repo has **no DnD library** and **no `Select`/`DropdownMenu` UI primitive** (only button/card/field/input/label/skeleton/spinner/textarea/toast), and no drag interaction anywhere in the app. Adding `@dnd-kit` + building an accessible drag surface is a large dependency + review cost that the lean-review directive does not justify for this phase. Instead: each `ApplicationCard` carries a native `<select>` of the 6 user-settable statuses; changing it fires the same `PATCH /applications/{id} {status}` a drag would have. The board is still visually columned, and a card animates to its new column on change (CSS only). **Real drag-and-drop is an explicit fast-follow, not in this phase.** This satisfies J7's real requirement ("column move = status change + `application_events` + audit" — the mechanism) and §488's keyboard reachability (a `<select>` is natively keyboard-operable) without the gesture.

**R2 — optimistic move with rollback.** On `<select>` change: `useMutation` with `onMutate` writing the new `status` + `last_status_change_at=now` into every cached `qk.applications(*)` list entry (and `qk.application(id)` if present), `onError` rolling back from the snapshot + a `toast({ variant: "danger" })`, `onSettled` invalidating `qk.applications` and `qk.application(id)`. Mirrors §470 ("optimistic UI on tracker moves … with rollback on error") and the `skill-gaps` patch precedent.

**R3 — client-component pages, matching the repo.** Every existing `app/(app)/*/page.tsx` is `"use client"` + `RequireAuth` + TanStack Query (jobs, resume, profile, dashboard). The master's aspirational "RSC for first paint of lists/detail" (§470) is **not** how this app is built — follow the repo. `/applications` and `/applications/[id]` are `"use client"` pages.

**R4 — six columns, pipeline order, two muted.** Columns left→right: **Saved · Applied · Interview · Offer · Rejected · Withdrawn**. `Rejected` and `Withdrawn` render with muted headers (they're terminal/negative) but are real drop targets in the `<select>`. `preparing` / `awaiting_approval` (agent-internal) are **not** columns — an application in those states (a `prepare` run mid-flight) is simply not shown on the board yet; it appears once the agent lands it in `applied` (post-approval) or the user saves it. The board fetches `GET /applications?limit=100` (one page; a "Load more" is a fast-follow) and buckets client-side by `status`.

**R5 — the detail timeline is read-only and merges server-side already.** `GET /applications/{id}/timeline` returns `{items: TimelineItemOut[]}` already merged + newest-first (Phase 11a R5). The detail page renders that list as-is — each item: an icon/dot by `kind` (`status_change` / `note` / `ai_action` / `email_sent` / `interview_scheduled`), the `title`, a relative timestamp (`at`), and `detail` rendered as a small key/value list when non-empty. No client-side merging.

**R6 — note composer prepends optimistically.** The detail page has a `<textarea>` + "Add note" (`react-hook-form` + `zod`, `body` 1–4000 to mirror `ApplicationNoteIn`). On submit: `POST /applications/{id}/notes` → `onMutate` prepends a synthetic `{kind:"note", at:now, title:"Note added", detail:{body}}` to `qk.applicationTimeline(id)`, `onError` rolls back + toast, `onSettled` invalidates. The endpoint returns the created `TimelineItemOut` (201) so `onSuccess` can swap the synthetic item for the real one (or just let `onSettled`'s refetch do it).

**R7 — "Save to tracker" joins "Prepare application" on the Job Detail page.** Currently `/jobs/[id]` has `<TailorButton>` + a "Prepare application" link (Phase 10b). Add a secondary **"Save to tracker"** button next to it: `POST /applications {job_id, intent:"save"}` → 201 `Application` → `toast` + `router.push("/applications")` (the card is in the Saved column). This is the no-agent path into the board.

**R8 — nav entry goes live.** `components/layout/nav-items.ts`: the `/applications` item flips `ready: false` → `ready: true`. No other nav change.

**R9 — delete is a per-card / per-detail "Remove from tracker" with confirm.** `DELETE /applications/{id}` (soft, 204). On the card: a small overflow affordance is overkill for this phase — put "Remove from tracker" only on the **detail page**, behind a `window.confirm`, → `router.push("/applications")` + invalidate. (Card stays lean: title, company, match, status `<select>`, "Open".)

## 2. Frontend surface

### `lib/api/types.ts`
- `Application` gains `notes: string | null` and `ai_session_id: string | null` (Phase 11a added both to `ApplicationOut`).
- New:
  ```ts
  export interface ApplicationListResponse { items: Application[]; total: number; limit: number; offset: number }
  export interface TimelineItem { kind: string; at: string; title: string; detail: Record<string, unknown> }
  export interface ApplicationTimeline { items: TimelineItem[] }
  export type ApplicationStatus = "saved" | "applied" | "interview" | "offer" | "rejected" | "withdrawn";
  ```

### `lib/api/endpoints.ts` — `api.applications` gains (keep existing `create`/`get`):
- `list(params?: { status?: string; sort?: string; limit?: number; offset?: number }) → ApplicationListResponse` (`GET /api/v1/applications?…`, drop empty params like `jobs.list` does)
- `save(job_id: string) → Application` (`POST /api/v1/applications`, body `{ job_id, intent: "save" }`)
- `patch(id, body: { status?: ApplicationStatus; notes?: string }) → Application` (`PATCH /api/v1/applications/${id}`)
- `remove(id) → void` (`DELETE`, 204)
- `addNote(id, body: string) → TimelineItem` (`POST /api/v1/applications/${id}/notes`, body `{ body }`, 201)
- `timeline(id) → ApplicationTimeline` (`GET /api/v1/applications/${id}/timeline`)

`create` stays `create(body: { job_id }) → RunRef` (Phase 10b's `PrepareApplicationBuilder` depends on it; the `save` path is separate).

### `lib/query.ts` — `qk` gains:
- `applications: (params?: Record<string, unknown>) => ["applications", "list", params ?? {}] as const`
- `applicationTimeline: (id: string) => ["application", id, "timeline"] as const`
(`qk.application(id)` already exists from Phase 10b.)

### Components (`components/applications/`)
- `StatusSelect.tsx` — pure. `{ value: ApplicationStatus; onChange: (s: ApplicationStatus) => void; disabled?: boolean }`. Native `<select>` styled as a pill, 6 options with human labels (`Saved`, `Applied`, `Interview`, `Offer`, `Rejected`, `Withdrawn`).
- `ApplicationCard.tsx` — `{ application: Application; jobTitle?: string; company?: string; onStatusChange: (s: ApplicationStatus) => void; busy?: boolean }`. Title + company (falls back to "Job {short id}" when the job lookup isn't loaded), match-score pill when `match_score != null`, relative "moved {last_status_change_at}", `<StatusSelect>`, and a `<Link href={/applications/${id}}>` "Open".
- `KanbanBoard.tsx` — `{ applications: Application[]; jobs: Record<string, { title: string; company: string }>; onMove: (id: string, status: ApplicationStatus) => void; movingId: string | null }`. Renders the 6 columns (R4), buckets by `status`, each column shows a count + its cards (or a tiny empty hint). Horizontal scroll on narrow viewports (`overflow-x-auto`), never body scroll.
- `Timeline.tsx` — `{ items: TimelineItem[] }`. Pure. Vertical list, newest first, dot/icon by `kind`, `title`, relative `at`, `detail` as a `<dl>` when non-empty. Empty → "No history yet."
- `AddNoteForm.tsx` — `{ onSubmit: (body: string) => Promise<void>; submitting: boolean }`. `react-hook-form` + `zod` (`body` min 1 max 4000), `<textarea>` + "Add note", clears on success.

### Pages
- `app/(app)/applications/page.tsx` — `"use client"` + `RequireAuth`. `useQuery(qk.applications(), () => api.applications.list({ limit: 100 }))`. Collects the distinct `job_id`s and fetches the jobs it doesn't have cached (one `useQuery` per id via `api.jobs.get`, or a small `useQueries`) to fill titles/companies — **best-effort**, cards render without them. `<KanbanBoard>` + the R2 optimistic move mutation. Loading → `<Skeleton>` columns. Error → `<ErrorState onRetry>`. Empty (no applications) → `<EmptyState>` "No applications yet — save a job to start tracking." with a `<Link href="/jobs">`.
- `app/(app)/applications/[id]/page.tsx` — `"use client"` + `RequireAuth`. `useParams<{id}>`. `useQuery(qk.application(id))` + `useQuery(qk.applicationTimeline(id))` + a `useQuery(qk.job(application.job_id))` (enabled once the application loads) for the header. Header: job title / company, `<StatusSelect>` (same optimistic patch), "Remove from tracker" (R9). Body: a small "Documents" panel linking résumé version (`/resume/versions/${resume_version_id}` when set), cover letter / email are shown as presence chips only (no dedicated viewer route this phase — the Prepare flow already showed them; a full viewer is a fast-follow). Then `<AddNoteForm>` (R6) and `<Timeline>`.

### `components/layout/nav-items.ts`
- `/applications` item: `ready: false` → `ready: true`.

### Tests (`tests/applications/`)
- `endpoints.test.ts` (or extend the existing) — the 6 new `api.applications.*` calls hit the right method + URL + body.
- `status-select.test.tsx` — renders 6 options, fires `onChange` with the picked value.
- `kanban-board.test.tsx` — buckets a fixture of applications into the right columns with counts; changing a card's `<select>` calls `onMove(id, status)`.
- `applications-page.test.tsx` — optimistic move: pick a new status → the card is in the new column immediately; a rejected `patch` (mock throws) → it snaps back + a toast. Empty state renders the link.
- `application-detail.test.tsx` — renders the timeline items in order with kinds; `AddNoteForm` submit optimistically prepends a "Note added" row; the status select on the header patches.
- `timeline.test.tsx` — pure: renders items newest-first, shows `detail` as a `<dl>`, empty copy.

## 3. Out of scope

Real drag-and-drop (R1 — fast-follow). A "Load more" / pagination control on the board (R4 — backend caps at 100, fine for now). A structured "Log interview" form (`interview_scheduled` has no endpoint yet — Phase 11a §3). Dedicated cover-letter / email viewer routes on the detail page (presence chips only this phase). Bulk actions, board-level filters beyond the columns, board search. Mana AI panel changes. `withdrawn`/`rejected` auto-archival.
