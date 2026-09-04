# Phase 8b — Résumé tailoring (frontend) design addendum

> Delta over `2026-09-04-phase-8-resume-tailoring.md` §9, written against the
> Phase 8a backend as it actually shipped (`main@8430ae9` + two pre-flight
> hotfixes below), not the summary's assumptions. Master spec: 2026-08-30
> `mana-career-design.md` §4.3/§5.3.

## 0. Goal (roadmap row 8, continued)

Let a user turn a tailored-résumé agent run (kicked off from a Job Detail
page) into something they can see, understand, and download: a live progress
view while the run streams, a field-level diff against the base résumé, and
a render in the format they want.

## 1. Two backend fixes made during pre-flight (already on `main`)

Both surfaced while tracing the real request/response shapes this phase
depends on — not scope, bug fixes to Phase 8a's own contract:

- **`RunRefOut` had no `session_id`.** `POST /resumes/{id}/tailor` creates a
  *new* `ai_session` per run and returns only `{run_id}`, but watching that
  run needs `GET /ai/sessions/{session_id}/events?run_id=...`, which requires
  a session id the frontend never received. Fixed: `RunRefOut` now carries
  `session_id: str` (both `post_goal` and the tailor route populate it).
  Commit `55fe27c`.
- **`resume_tailoring` ignored `inputs.resume_id`.** The node always tailored
  the primary-or-first-confirmed résumé regardless of which `resume_id` the
  route validated, so a user tailoring a non-primary résumé would silently
  get the wrong one tailored. Fixed: the node now honors an explicit
  `resume_id` (falling back to the old pick only when one isn't given).
  Commit `da13755`. This phase's `TailorButton` depends on the fix being in
  place — it always sends the specific résumé it resolved.

## 2. Scope cut from the master spec's §9 sketch

Two things the original summary assumed exist do not, and building them for
real is out of scope here:

- **No "Résumé Workspace 3-pane shell."** `/resume` today is a single-column
  upload → review → confirm → list flow
  ([resume/page.tsx](../../../frontend/app/(app)/resume/page.tsx)). This
  phase adds a "Tailored versions" section to that existing page instead of
  building a new workspace shell. A dedicated workspace is a later-phase
  polish item, not blocking here.
- **No `resume_suggestions` table/API.** The table exists (migration
  `0011`) but 8a writes no rows to it — `ResumeSuggestionBlock.suggestion_id`
  is actually the new `ResumeVersion`'s id, reused as "a tailored version is
  ready" (8a's own out-of-scope note called this "8b decides"). There is no
  `PATCH` endpoint to accept/dismiss a suggestion, and building one is a new
  backend feature this phase does not add. Decision: the block renders as a
  **view-only** card — "your résumé was tailored, view what changed" — with
  no Accept/Edit/Dismiss affordance. A version is not a proposal that needs
  disposing of; it is already-persisted history the user can always find
  again under "Tailored versions", so nothing is lost by not having a
  dismiss action.

## 3. Confirmed real contracts this phase builds against

`GET /resumes/{resume_id}/versions` → `{ items: ResumeVersionOut[] }`;
`GET /resumes/versions/{id}` → `ResumeVersionOut & { content: ResumeExtraction }`;
`GET /resumes/versions/{id}/diff?against=<uuid|"base">` → `{ deltas: FieldDeltaOut[] }`
(defaults to the version's parent, or the base snapshot);
`GET /resumes/versions/{id}/render?fmt=md|html|pdf|docx` → raw body
(`text/markdown` / `text/html` / `application/pdf` /
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`),
**409** `{code:"render_unavailable"}` on `pdf`/`docx` when unavailable.
`POST /resumes/{resume_id}/tailor` body `{job_id}` → **202**
`{run_id, session_id}`. `GET /ai/sessions/{session_id}/events?run_id=...` →
the same `step`/`block`/`error`/`done` SSE frame shapes `useAgentStream`
already parses (Phase 7b).

`ResumeVersionOut.claim_validation` is `{}` for `base_snapshot`/`manual_edit`
versions (only `ai_tailored` versions carry `{checked, unsupported,
supported_ratio, passed}` — mirror `ClaimReport.as_dict()`,
[tailoring.py:47](../../../backend/app/domain/resume/tailoring.py)) — render
the claim-validation banner only when the fields are actually present.

`FieldDeltaOut.path` shapes (from
[version_service.py](../../../backend/app/domain/resume/version_service.py)):
a bare field name for a top-level scalar (`"summary"`) or the top-level
`skills` list; `"{section}[{i}]"` for a whole added/removed entry
(`experiences`/`projects`/`education`/`certifications`); `"{section}[{i}].{field}"`
for a changed sub-field, including list sub-fields (`highlights`, `tech`).
The diff UI groups by the text before the first `[` or `.`.

## 4. Frontend surface (final — supersedes the master spec's §9 sketch)

- `lib/api/types.ts` — `RunRef` gains `session_id: string` (was `{run_id}`
  only). New: `ClaimValidation`, `ResumeVersion`, `ResumeVersionDetail`,
  `FieldDelta`, `ResumeDiff`. `ResumeSuggestionBlock` is carved out of
  `StubBlock` the same way `JobCardBlock`/`InsufficientInfoBlock` were in
  Phase 7a; `StubBlock`'s kind union drops `"resume_suggestion"`.
- `lib/api/endpoints.ts` — `api.resumes` gains `tailor`, `versions`,
  `version`, `diff`, `renderUrl` (returns a path string, like the SSE
  hooks' pattern — not a JSON call, since render bodies aren't JSON).
- `lib/query.ts` — `qk.resumeVersions(resumeId)`, `qk.resumeVersion(id)`,
  `qk.resumeDiff(id, against)`.
- `hooks/useTailorRunEvents.ts` — watches an in-flight tailor run
  (`GET /ai/sessions/{sessionId}/events?run_id=...`), same frame parsing as
  `useAgentStream` (`step`/`block`/`error`/`done`) but the
  watch-with-reconnect shape of `useJobEvents`/`useResumeEvents` (the run is
  already started; this hook only watches it — a fresh `parseFrame` copy per
  the established repo convention, not an extraction).
- `components/resume/VersionDiff.tsx` — renders a `ResumeDiff` grouped by
  section, each delta as an op-badged row (added/removed/changed/reordered),
  before/after stacked for `changed`; a claim-validation banner when present.
- `components/ai/blocks/ResumeSuggestionBlockView.tsx` — fetches
  `api.resumes.version(block.suggestion_id)` (mirrors `JobCardBlockView`'s
  own-fetch pattern) and renders a compact "résumé tailored for `{job
  title}`" card linking to the diff page. Registered in `block-registry.tsx`.
- `components/resume/TailorButton.tsx` — resolves the confirmed résumé to
  tailor (primary-confirmed, else first-confirmed, else disabled with a
  link to `/resume`), calls `api.resumes.tailor`, watches the run inline via
  `useTailorRunEvents`, and once a `resume_suggestion` block arrives shows
  it via `<BlockView>` (no separate render path — one block, one view).
  Replaces the disabled "Prepare application" placeholder on
  [jobs/[id]/page.tsx:161](../../../frontend/app/(app)/jobs/[id]/page.tsx).
- `/resume` page — a "Tailored versions" section (visible once the primary
  confirmed résumé has any `ai_tailored` versions) listing them newest
  first, each linking to its diff page.
- `app/(app)/resume/versions/[id]/page.tsx` — `<VersionDiff>` plus a format
  switcher (md/html/pdf/docx) that fetches via `authedStream` and opens
  (md/html/pdf, via a Blob object URL in a new tab) or downloads (docx, via
  a synthesized `<a download>` click) the result; a 409 shows a toast
  instead of attempting the print fallback the master sketch proposed
  (simpler, same outcome — nudge to another format).

## 5. Out of scope (unchanged from 8a's own note, now confirmed still true)

- `resume_suggestions` accept/edit/dismiss and its API — no backend support;
  see §2.
- A dedicated 3-pane Résumé Workspace — later polish.
- `resume_chunks` retrieval — Phase 12.
- Persisting rendered files to `FileStore` — later polish; renders stay
  on-demand.
