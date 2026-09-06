# Phase 10b — Human approval workflow (frontend) design addendum

> Delta over master `2026-08-30-mana-career-design.md` §7 (roadmap row 10's "7-step Builder UI + approval card + success state") and the Phase 10a backend as shipped (`main@0e03726`). Backend is complete and CI-green — this phase only adds the UI that drives `POST /applications` → the `human_approval` pause → `POST /approvals/{id}` → the send.

## 0. Goal

A "Prepare application" flow: from a Job Detail page, kick off the full `prepare_application` agent run, watch it stream to the approval pause, show the user the exact cover letter + email that would be sent, and — only on their explicit approval — resume the run to send it. Then a success state.

## 1. Rulings

**R1 — a dedicated `usePrepareRunEvents` hook, not an extension of `useTailorRunEvents`.** Phase 8b's `useTailorRunEvents` is shipped and consumed by `TailorButton`; the repo convention (established in 8b) is one SSE hook per consumer with its own `parseFrame` copy, not a shared/parameterized one. The new hook is `useTailorRunEvents` plus one more `frame.event === "approval"` branch → `status: "awaiting_approval"`, `approvalId: string | null`. Same **single-attempt, no-reconnect** design and rationale (the AI relay forwards live Redis pub/sub with no replay).

**R2 — the post-approval "sending" phase POLLS, it does not re-watch the SSE.** After `POST /approvals/{id}`, `resume_agent` is enqueued with `_defer_by=1.0` and re-publishes to the same `sse:ai:{run_id}` channel — but reconnecting an SSE to a no-replay pub/sub channel in that ~1s window is a race (documented in `useTailorRunEvents`'s own comment). Instead: once approved, the Builder switches to `useQuery({ queryKey: qk.application(id), queryFn: () => api.applications.get(id), refetchInterval })` and stops when `application.status` leaves `"awaiting_approval"` — `"applied"` → the success state, anything else → an error/stopped state. Race-free, and `GET /applications/{id}` is a plain owner-scoped read the backend already ships.

**R3 — the Builder learns `application_id` from `GET /approvals/{id}`, not the SSE.** The `approval` SSE frame carries only `{approval_id}` (Phase 10a R4 — kept the interrupt payload small). `GET /approvals/{id}` returns `application_id` in its body; the Builder fetches the approval on the `approval` event and reads `application_id` off it for the R2 poll.

**R4 — no block rendering.** `respond` emits a block only on the *completed* path (a "your application was sent" `TextBlock`), and never during the pause. The Builder is driven entirely by SSE `step`/`approval`/`error`/`done` frames + the `GET /approvals/{id}` and `GET /applications/{id}` REST reads. The `block-registry` is untouched this phase. (`ApplicationDraftBlock` — 4 optional fields, already in `lib/api/types.ts` from Phase 9 — also stays unused by this phase.)

**R5 — the Builder is its own route, `applications/new/[jobId]`, not `applications/[id]/prepare`.** The master's `applications/[id]/prepare` route can't be the entry point: `POST /applications` doesn't return an `application_id` (the `application_prep` node mints it mid-run). `applications/new/[jobId]` takes the job id it already has. The Job Detail page gets a "Prepare application" link to it, placed right after the existing `<TailorButton>`. No `applications/[id]` detail route this phase — the success state lives on the Builder page (a tracker detail page is Phase 11).

**R6 — reject and error are terminal on the Builder page.** No revise loop (Phase 10a R8 already made the backend `reject` terminal). A rejected run shows "You didn't approve this application" + a link back to the job. A dropped SSE or a failed decision shows an error with a retry that restarts the whole flow (a fresh `POST /applications`).

**R7 — the approval card copy is mandated verbatim in one spot.** Per the master (§4.7 step 3): the card renders the exact preview (role, company, to, full body) **plus** the line "Nothing will be sent until you approve it." — include that sentence literally.

## 2. Frontend surface

- `lib/api/types.ts` — `Application` (mirrors `ApplicationOut`: `id, job_id, resume_version_id|null, cover_letter_id|null, application_email_id|null, status, match_score|null, source, applied_at|null, last_status_change_at, created_at, updated_at`); `ApprovalPayloadSnapshot` (`{ job: {title, company}, resume_version_id: string|null, cover_letter: {id, content}, email: {id, to_email: string|null, to_name: string|null, subject, body} }`); `ApprovalRequest` (`id, application_id, action_type, payload_snapshot: ApprovalPayloadSnapshot, status, decided_at|null, decision_note|null, created_at`); `ApprovalRequestList` (`{items: ApprovalRequest[]}`); `ApprovalDecision` (`{decision: "approve"|"reject", note?: string}`). `RunRef` already exists (`{run_id, session_id}`).
- `lib/api/endpoints.ts` — `api.applications` (`create(body: {job_id: string}) -> RunRef`, `get(id) -> Application`); `api.approvals` (`list(status?: string) -> ApprovalRequestList`, `get(id) -> ApprovalRequest`, `decide(id, body: ApprovalDecision) -> void`).
- `lib/query.ts` — `qk.application(id)`, `qk.approval(id)`, `qk.approvals(status)`.
- `hooks/usePrepareRunEvents.ts` — `(sessionId, runId) -> { steps, status: "idle"|"streaming"|"awaiting_approval"|"done"|"error", approvalId: string|null, error: string|null }`.
- `components/applications/ApprovalCard.tsx` — pure/presentational: `{ snapshot: ApprovalPayloadSnapshot, submitting: boolean, onApprove: () => void, onReject: () => void }`. Role + company header, the cover letter (`whitespace-pre-line`), the email block (to / subject / body), the R7 sentence, Approve (primary) / Reject (outline) buttons disabled while `submitting`.
- `components/applications/PrepareApplicationBuilder.tsx` — `{ jobId: string }`. Orchestrates: `POST /applications` on mount → `usePrepareRunEvents` → a step-progress checklist (a `node → label` map: `resume_tailoring` "Tailoring your résumé", `cover_letter` "Writing your cover letter", `email_draft` "Drafting your email", `application_prep` "Getting it ready for your review") → on `awaiting_approval`, `useQuery(qk.approval(approvalId))` → `<ApprovalCard>` → `api.approvals.decide` → poll `qk.application(id)` (`refetchInterval` while `status === "awaiting_approval"`, stop otherwise) → success ("Application sent" + `applied_at` local time) / rejected / error (with "Start over" → remount via a `key` bump).
- `app/(app)/applications/new/[jobId]/page.tsx` — `RequireAuth` + `<PrepareApplicationBuilder jobId={params.jobId} />` + a header.
- `app/(app)/jobs/[id]/page.tsx` — a `<Link href={\`/applications/new/${id}\`}>` styled as a primary `Button` (`asChild`-style or a plain `<Link>` with button classes — match how other nav-as-button links in this app are done), right after `<TailorButton jobId={id} />`.
- Tests: `endpoints.test.ts` extend; `tests/applications/use-prepare-run-events.test.ts`; `tests/applications/approval-card.test.tsx`; `tests/applications/prepare-builder.test.tsx`.

## 3. Out of scope

The Kanban tracker, `applications` list/detail/timeline/notes, `PATCH /applications` (Phase 11). Edits/reconfirm on an approval (Phase 10a R9 — no backend support). Any real-send configuration (`console` only). Mana AI panel changes.
