# Real Email Sending Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the human-approved application email over real SMTP, safely enough for a public portfolio deployment, with the résumé attached and at-most-once delivery.

**Architecture:** A pure MIME builder and an SMTP adapter sit behind the existing `EmailSender` protocol. One domain module, `app/domain/applications/sending.py`, owns the approval-recipient step and the at-most-once send (used by the agent node and a manual-retry endpoint). Delivery mode (`redirect`/`live`) and daily caps are settings.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, stdlib `smtplib`/`email`, ARQ worker, Next.js + TanStack Query, vitest, Mailpit (dev + CI).

**Spec:** `docs/superpowers/specs/2026-09-30-real-email-sending-design.md`

## Global Constraints

- No commits or pushes until the user says so (standing instruction, 2026-09-30).
- Console sender stays the default; nothing leaves the box unless `EMAIL_PROVIDER=smtp`.
- `EMAIL_DELIVERY` defaults to `redirect`; `live` must be set explicitly.
- Never resend automatically once a send has been attempted (`sending` committed).
- Approval must cover the recipient: hash re-verified before writing it, recomputed after.
- Header values must not contain CR/LF; recipient validated with the existing `EMAIL_RE`.
- No new runtime dependencies (stdlib `smtplib`, `email`).
- Keep import-linter contracts: domain never imports api/worker.

---

### Task 1: Settings for SMTP, delivery mode and caps

**Files:** Modify `backend/app/core/config.py`; Test `backend/tests/domain/email/test_sender.py`, `backend/tests/core/test_config.py`.

**Produces:** `Settings.email_provider: Literal["console","smtp"]`, `smtp_host: str|None`, `smtp_port: int=587`, `smtp_username: str|None`, `smtp_password: SecretStr|None`, `smtp_security: Literal["starttls","ssl","none"]="starttls"`, `smtp_timeout_seconds: float=20`, `email_from_address: str|None`, `email_from_name: str="Mana Career"`, `email_delivery: Literal["redirect","live"]="redirect"`, `email_daily_limit_per_user: int=5`, `email_daily_limit_total: int=100`.

- [ ] Replace `test_unbuilt_email_providers_are_rejected_at_startup` with: smtp without host/from rejected; smtp with host+from accepted; unknown provider rejected; prod + `SMTP_SECURITY=none` rejected.
- [ ] Implement fields + `_validate` rules:

```python
if self.email_provider == "smtp":
    if not (self.smtp_host or "").strip():
        raise ValueError("SMTP_HOST is required when EMAIL_PROVIDER=smtp")
    if not EMAIL_ADDRESS_RE.match((self.email_from_address or "").strip()):
        raise ValueError("EMAIL_FROM_ADDRESS must be a valid address when EMAIL_PROVIDER=smtp")
# in _validate_production:
if self.email_provider == "smtp" and self.smtp_security == "none":
    raise ValueError("SMTP_SECURITY=none is only for local test servers, not production")
```

- [ ] Run `uv run pytest --no-cov -q tests/domain/email tests/core/test_config.py`; expect PASS.

### Task 2: Message model, MIME builder, SMTP sender, factory

**Files:** Modify `backend/app/domain/email/types.py`, `sender.py`, `factory.py`; Create `backend/app/domain/email/mime.py`, `backend/app/domain/email/smtp.py`; Test `backend/tests/domain/email/test_mime.py`, `test_sender.py`.

**Produces:**
```python
@dataclass(frozen=True)
class EmailAttachment: filename: str; content_type: str; data: bytes

@dataclass(frozen=True)
class EmailMessage:
    to_email: str; to_name: str | None; subject: str; body: str
    body_format: str = "plain"
    from_name: str | None = None        # display name; address comes from settings
    reply_to: str | None = None
    bcc: tuple[str, ...] = ()
    attachments: tuple[EmailAttachment, ...] = ()

class InvalidEmailMessage(ValueError): ...
def build_mime(message: EmailMessage, *, from_address: str) -> email.message.EmailMessage
class SmtpEmailSender:  # __init__(settings: Settings); async send(message) -> EmailSendResult(provider="smtp", provider_message_id=<Message-ID>)
class EmailDeliveryError(RuntimeError): ...  # raised by SmtpEmailSender on any SMTP/socket failure, message safe to show
```

- [ ] Tests (`test_mime.py`): From shows `"<name> via ..."`-style display name and settings address; To with name; Reply-To; Bcc not in headers but returned recipients include it; attachment present with filename and `application/pdf`; `\r\n` in subject / name / address raises `InvalidEmailMessage`; Message-ID set.
- [ ] Implement `build_mime` with `email.message.EmailMessage(policy=email.policy.SMTP)`, `formataddr`, `make_msgid(domain=<from domain>)`; reject any header value containing `\r` or `\n`; attachments via `add_attachment(data, maintype, subtype, filename=...)`.
- [ ] Implement `SmtpEmailSender.send`: build MIME, then `await asyncio.to_thread(self._deliver, mime, recipients)`; `_deliver` opens `smtplib.SMTP_SSL` (ssl) or `smtplib.SMTP` (+`starttls()` when starttls), logs in when username set, `send_message(mime, to_addrs=recipients)`; wrap `smtplib.SMTPException | OSError` into `EmailDeliveryError` with a short reason (no secrets).
- [ ] Factory: `smtp` → `SmtpEmailSender(settings)`, else console. Console logs to/subject/attachment count.
- [ ] Unit-test `SmtpEmailSender` against a fake `smtplib.SMTP` (monkeypatched) asserting starttls/login/send_message calls and error wrapping.

### Task 3: `delivered_to` column (migration 0016)

**Files:** Create `backend/alembic/versions/0016_email_delivered_to.py`; Modify `backend/app/models/application.py`.

```python
revision = "0016_email_delivered_to"; down_revision = "0015_learning_roadmap"
def upgrade(): op.add_column("application_emails", sa.Column("delivered_to", sa.String(320), nullable=True))
def downgrade(): op.drop_column("application_emails", "delivered_to")
```
- [ ] Model: `delivered_to: Mapped[str | None] = mapped_column(String(320))`.
- [ ] Migration round-trip runs in CI (`alembic upgrade head` in the test DB fixture).

### Task 4: Domain send service (recipient, at-most-once, redirect, caps, attachment)

**Files:** Create `backend/app/domain/applications/sending.py`; Modify `backend/app/domain/agents/nodes/email_external_action.py`; Test `backend/tests/domain/applications/test_sending.py` (DB), `test_sending_pure.py` (pure).

**Produces:**
```python
class RecipientError(ValidationAppError)
async def set_approval_recipient(session, *, approval: ApprovalRequest, to_email: str, to_name: str | None) -> None
    # verify current snapshot hash == approval.payload_hash (else ConflictError "changed since you reviewed it"),
    # write email.to_email/to_name, rebuild snapshot, store approval.payload_snapshot + payload_hash
@dataclass(frozen=True)
class SendOutcome: status: Literal["sent","failed","halted"]; message: str; delivered_to: str | None = None
async def send_approved_application(session, *, user_id, application: Application, sender: EmailSender, settings: Settings) -> SendOutcome
def compose_message(*, applicant_name, applicant_email, email_row, delivery, attachment) -> tuple[EmailMessage, str]  # pure: returns message + delivered_to
```
Rules inside `send_approved_application`:
1. Load approval (approved, else halted), letter, email; re-verify snapshot hash (else halted).
2. `email.status == "sent"` → `SendOutcome("sent", "Already sent", email.delivered_to)` (no send).
3. `email.status == "sending"` → set `failed`, `send_error="An earlier attempt was interrupted; it may or may not have been delivered. Check your inbox before sending again."`, return failed (no send).
4. No `to_email` → failed "Add who this goes to before sending."
5. Caps: count `ApplicationEmail.status=="sent"` with `sent_at >= today 00:00 UTC` for the user and overall → failed with a clear message when reached.
6. Render résumé PDF from `application.resume_version_id` (TailoringService.get_version → DocumentRenderer PDF); on `RenderUnavailable`/missing record `attachment_refs={"resume": "unavailable"}`.
7. Mark `status="sending"`, `session.commit()`.
8. `sender.send(message)`: success → `sent`, provider, message id, `sent_at`, `delivered_to`, application `applied` + `applied_at` + `last_status_change_at`, audit `application.email_sent` with `redirected` flag; `EmailDeliveryError` → `failed`, `send_error=str(exc)`, audit failure.

`compose_message` (pure): redirect → `to=applicant_email`, prepend note
`"Mana Career demo: in the live product this email would be delivered to {name} <{addr}>. It was sent to you instead so you can see exactly what the employer would receive.\n\n---\n\n"`, no bcc; live → to=recipient, bcc=(applicant_email,). Both: `from_name=f"{applicant_name} via Mana Career"` (or "Mana Career"), `reply_to=applicant_email`.

- [ ] Pure tests for `compose_message` (redirect vs live, note text, bcc, reply-to).
- [ ] DB tests: set recipient updates hash + rejects changed payload; sent → no second send (sender call count 0); sending → failed without send; failure → failed + send_error; success → applied + delivered_to; cap reached → failed; another user's application can't be sent (NotFound via application lookup in API).
- [ ] Node delegates to `send_approved_application` and maps outcome: sent → `{"status":"completed"}` (+ `_log_action` "Application sent…"); failed/halted → `{"status":"halted","error":..., "_summary": message}`.

### Task 5: API — decision with recipient, delivery status, manual send, meta

**Files:** Modify `backend/app/api/v1/schemas/approvals.py`, `approvals.py`, `schemas/applications.py`, `applications.py`, `meta.py`; Test `backend/tests/api/test_approvals.py`, `tests/api/test_application_delivery.py`, `tests/api/test_meta_and_docs.py`.

- `ApprovalDecisionIn`: `to_email: str | None`, `to_name: str | None (max 200)`; validator: stripped, `EMAIL_RE`, no CR/LF; model validator: `decision == "approve"` requires `to_email` (422).
- `decide_approval`: on approve call `set_approval_recipient(...)` before marking approved.
- `GET /applications/{id}/delivery` → `ApplicationDeliveryOut{status, intended_to, delivered_to, redirected, sent_at, error}` (status `none` when no email).
- `POST /applications/{id}/send` (202-free, returns delivery) → only when email `failed`; runs `send_approved_application` with `get_email_sender(settings)`; 409 otherwise. Rate-limited by the existing llm bucket? No: add path to `_bucket` upload/llm → use `llm` bucket (POST `/applications/.../send`). (Already matched: POST `/applications` prefix → llm.)
- `/meta.email_delivery`: `"console"` when provider console, else `settings.email_delivery`.
- [ ] Update existing decide test to send `to_email` and seed a real snapshot hash; add 422-without-recipient test; delivery/send tests; meta test.

### Task 6: Mailpit round-trip (dev + CI)

**Files:** Modify `docker-compose.yml`, `.github/workflows/ci.yml` (backend job service + `MAILPIT_URL`, `MAILPIT_SMTP_PORT`); Create `backend/tests/integration/test_smtp_mailpit.py`.

- Mailpit image pinned `axllent/mailpit:v1.21`; ports 1025 (SMTP), 8025 (HTTP).
- Test: skip unless `MAILPIT_URL`; send via `SmtpEmailSender` (security none, host localhost, port 1025) with a PDF attachment; poll `GET {MAILPIT_URL}/api/v1/messages` then `GET /api/v1/message/{ID}`; assert subject, Reply-To, attachment filename.

### Task 7: Frontend — recipient on approval card, delivery states, retry

**Files:** Modify `frontend/lib/api/types.ts`, `endpoints.ts`, `lib/query.ts`, `components/applications/ApprovalCard.tsx`, `PrepareApplicationBuilder.tsx`; Test `frontend/tests/applications/approval-card.test.tsx`, `prepare-builder.test.tsx`.

- Types: `ApprovalDecision {decision; note?; to_email?; to_name?}`, `AppMeta.email_delivery: "console"|"redirect"|"live"`, `ApplicationDelivery`.
- Endpoints: `applications.delivery(id)`, `applications.send(id)`; qk `applicationDelivery(id)`.
- ApprovalCard: controlled "Send to" email (required) + name; inline error "Enter the hiring contact's email" on approve without a valid address; delivery note from `delivery` prop.
- Builder: pass recipient in decide; after approve poll `delivery` every 2 s until `sent`/`failed`; sent → "Sent to X" or "Delivered to your inbox (demo) — in the live product it goes to X"; failed → error + "Try sending again" (calls send, then polls again).

### Task 8: Docs + verification

**Files:** `.env.example`, `backend/.env.example` (regenerate), `docs/runbook.md` (Email section: Gmail app password, Brevo, Mailpit, redirect vs live, caps, SPF/DKIM note).
- [ ] Backend: ruff, mypy, lint-imports, pytest (non-DB locally). Frontend: tsc, lint, vitest.
- [ ] No commit (user gate).
