# Real email sending — design

Date: 2026-09-30. Status: approved in chat ("yes"). Context: portfolio deployment.

## Goal

The human-approved application email is actually delivered over SMTP, safely
enough to leave a public portfolio deployment running, with the tailored résumé
attached and no chance of a duplicate send.

## Current state (read before changing)

- `app/domain/email/`: `EmailSender` protocol, `ConsoleEmailSender` (logs only),
  `get_email_sender()` always returns the console sender; `EMAIL_PROVIDER` only
  accepts `console`.
- `email_external_action` (agent node) re-checks approval + payload hash, then
  calls `deps.email_sender.send(...)`. It sends to `email.to_email or ""`:
  **no screen or step ever sets a recipient**, so the approval card shows
  "To: —".
- `ApplicationEmail` already has `to_email`, `to_name`, `cc`, `bcc`,
  `attachment_refs`, `status` (`draft…sending…sent…failed`), `provider`,
  `provider_message_id`, `sent_at`, `send_error`.
- A worker retry re-runs the node; a real sender would send twice.
- The frontend polls `GET /applications/{id}` until `status != awaiting_approval`;
  a failed send would poll forever.

## Decisions

1. **SMTP adapter** (stdlib `smtplib` in a thread, 20 s timeout) behind the
   existing `EmailSender` protocol. Works with a Gmail app password, Brevo,
   Resend, Postmark, SES. `EMAIL_PROVIDER=smtp` + `SMTP_HOST`, `SMTP_PORT`
   (587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SECURITY`
   (`starttls`|`ssl`|`none`), `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`
   ("Mana Career"). Startup fails if `smtp` is chosen without host/from; prod
   refuses `SMTP_SECURITY=none`. Console stays the default.
2. **Delivery mode** `EMAIL_DELIVERY=redirect|live`, default `redirect`.
   - `redirect`: the email goes to the applicant's own account address, with a
     short note at the top naming the employer address it would reach in the
     live product. No copy (they are the recipient).
   - `live`: goes to the entered recipient; the applicant gets a BCC copy.
   - Always: `From: "<Applicant> via Mana Career" <EMAIL_FROM_ADDRESS>`,
     `Reply-To: <applicant>`.
   - Caps: `EMAIL_DAILY_LIMIT_PER_USER` (5) and `EMAIL_DAILY_LIMIT_TOTAL`
     (100) sends per UTC day; over the cap the send fails with a clear message.
3. **Recipient at review time.** Approving requires `to_email` (validated
   address, no CR/LF) and optional `to_name`. The server first checks the
   unchanged content still matches the hash the user reviewed, then writes the
   recipient, rebuilds the snapshot and stores the new hash, so the approval
   covers exactly what was shown plus the address typed.
4. **Attachment.** The approved résumé version is rendered to PDF
   (`DocumentRenderer`) and attached as `<Name> - Resume.pdf`. If rendering is
   unavailable the email is sent without it and `attachment_refs` records why.
5. **At most once.** One domain function, `send_approved_application`, used by
   the agent node and the manual retry:
   - `sent` → no-op success; `sending` (earlier attempt, outcome unknown) →
     mark `failed` ("may or may not have been delivered"), never resend
     automatically.
   - Otherwise mark `sending` and **commit** before talking to SMTP, then
     `sent` (+ `delivered_to`, message id, `sent_at`, application `applied`) or
     `failed` (+ `send_error`).
6. **Manual retry.** `POST /applications/{id}/send` re-runs the same function
   for a `failed` email (re-verifies approval + hash). `GET
   /applications/{id}/delivery` returns `{status, intended_to, delivered_to,
   redirected, sent_at, error}`; the UI polls this and stops on `sent`/`failed`.
7. **Schema:** migration `0016` adds `application_emails.delivered_to`
   (String 320).
8. **Meta:** `/api/v1/meta` gains `email_delivery`: `console`|`redirect`|`live`
   so the approval card can say where the email will go.

## UI

- Approval card: "Send to" email (required) + name; a line explaining delivery
  ("Demo: delivered to your own inbox, you@x.com, so you can see exactly what
  the employer would get" / console: "Sending is off on this server").
- After approval: "Sending…" → "Sent to X" (or "Delivered to your inbox as a
  demo of the email to X") → on failure the reason and "Try sending again".

## Testing

- Unit: MIME building (headers, Reply-To, BCC, redirect note, attachment,
  header-injection rejection), config validation, caps.
- DB (CI): decision endpoint writes recipient + new hash and rejects a changed
  payload; at-most-once states; retry endpoint; tenant isolation.
- Real SMTP (CI): Mailpit service container; send through `SmtpEmailSender`
  and read it back from Mailpit's API (subject, Reply-To, attachment). Skips
  locally unless `MAILPIT_URL` is set. Dev `docker-compose.yml` gains Mailpit
  (UI on :8025).
- Frontend: approval card validation + delivery note, sent/failed/retry states.

## Out of scope

Password reset / verification emails (next task, reusing this sender), HTML
email bodies, bounce handling, per-user sender accounts.
