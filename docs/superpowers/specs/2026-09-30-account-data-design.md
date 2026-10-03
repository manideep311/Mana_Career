# Download your data + delete your account — design

Date: 2026-09-30. Status: approved in chat ("build everything but no commits").

## Goal

A person can take a complete copy of their data with them, and can delete
their account so that nothing of theirs remains, without touching anyone else.

## Findings

- Every user-owned table has `ForeignKey("users.id", ondelete="CASCADE")`, so
  deleting the user row removes their rows.
- Not covered by the cascade:
  1. résumé PDFs on disk (`resumes/<user>/<resume>.pdf`, the only file writes);
  2. LangGraph checkpoints, stored per run (`thread_id = run_id`), holding
     agent state such as cover-letter and email text;
  3. `audit_logs` (no FK by design: the security trail outlives accounts),
     which store `ip` and `user_agent`.

## Decisions

1. **Export** `GET /api/v1/account/export` → `application/zip`
   (`mana-career-export-YYYY-MM-DD.zip`):
   - `mana-career-data.json`: `account` (email, name, created, confirmed),
     `profile` (+ experiences, education, projects, certifications, skills),
     `resumes` (metadata, what was read, extracted text), `resume_versions`,
     `saved_jobs` (their own pasted jobs), `applications` (+ cover letters,
     emails, timeline events), `roadmaps` (+ milestones),
     `mana_ai_conversations` (their messages and replies), `job_matches`
     (score, band, reasons). Columns are exported generically, minus a deny
     list: password hash, token hashes, embeddings, search vectors, payload
     hashes, internal generation metadata.
   - `resumes/<original filename or id>.pdf`: the uploaded files.
   - Tenant-scoped by `user_id` everywhere; rate-limited on the upload tier.
2. **Delete** `DELETE /api/v1/account {password, confirm: "DELETE"}` → 204:
   - Wrong password → 401 `invalid_credentials`; nothing changes.
   - Order: collect résumé file refs and run ids → delete checkpoints
     (`adelete_thread`) → blank `ip`/`user_agent` on the user's audit rows →
     write `account.deleted` audit (no personal data) → delete the user row
     (cascade) → commit → delete files (after commit, so a failure can't leave
     a half-deleted account; file errors are logged).
   - The refresh cookie is cleared; any access token stops working because the
     user no longer exists.
3. **UI** on the Profile page: "Your data" card with **Download your data**;
   "Danger zone" card with **Delete account…** opening a dialog that lists what
   is deleted and asks for the password and the word DELETE. On success: local
   sign-out, go home, toast "Your account has been deleted."

## Testing

DB (CI): after deletion no row references the user in any user-owned table,
another user is untouched, files are gone, checkpoints are gone, audit rows
keep actions but lose ip/user agent, wrong password deletes nothing. Export
contains the user's data (profile, résumé text, application letter, job),
none of the deny-listed fields, none of another user's rows. Frontend: export
button, dialog validation, success path.

## Out of scope

Delayed/soft deletion with a grace period; exporting in formats other than
JSON + PDF.
