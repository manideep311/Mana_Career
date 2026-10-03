# Forgot Password + Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Password recovery and email confirmation over the existing `EmailSender`, with confirmation gating real application emails.

**Architecture:** A token store (`auth_tokens`) and an `AccountEmailService` in `app/domain/auth/account_emails.py` (issue/consume tokens, build and send the two emails). Four `/auth` endpoints; sends run as FastAPI background tasks. The application-send path checks verification when `EMAIL_PROVIDER=smtp`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Next.js App Router, TanStack Query, vitest.

**Spec:** `docs/superpowers/specs/2026-09-30-account-emails-design.md`

## Global Constraints

- No commits or pushes until the user says so.
- No account enumeration: `/password/forgot` returns the same 202 body for known and unknown emails.
- Raw tokens never stored or logged; only sha256 hashes.
- Reset revokes every session. Tokens single-use; newer token supersedes older.
- Verification enforced only when `EMAIL_PROVIDER=smtp`.
- Link tokens travel in the URL fragment (`#token=`).

---

### Task 1: Settings + token table
- `APP_BASE_URL: str = "http://localhost:3000"`; validator: `http(s)://` required, strip trailing `/`; prod requires `https://`.
- Model `AuthToken` in `app/models/auth.py`; migration `0017_auth_tokens` (index on `(user_id, purpose, created_at)`, unique `token_hash`, check `purpose in ('password_reset','email_verify')`).
- Tests: config (bad scheme rejected, prod needs https, trailing slash stripped).

### Task 2: Account email service
`app/domain/auth/account_emails.py`:
```python
Purpose = Literal["password_reset", "email_verify"]
TTL = {"password_reset": timedelta(minutes=30), "email_verify": timedelta(hours=48)}
MAX_PER_HOUR = 3
def reset_email(*, name: str, email: str, link: str) -> EmailMessage      # pure
def verify_email(*, name: str, email: str, link: str) -> EmailMessage     # pure
class AccountEmailService(session, settings):
    async def issue(user, purpose) -> str | None       # raw token, or None when throttled
    async def consume(raw, purpose) -> User            # AppError(400, invalid_token) on bad/used/expired/inactive
    def link(purpose, raw) -> str
async def deliver(message: EmailMessage, settings) -> None   # background: get_email_sender(settings).send, log failures
```
- Pure tests for the two builders (subject, link present, expiry wording, ignore line) and `link`.
- DB tests: supersede, throttle, consume once, expired, wrong purpose.

### Task 3: Auth endpoints + register hook + UserOut.email_verified
- `AuthService.reset_password(user, new)`: hash, revoke all refresh tokens, set `email_verified_at` if unset, audit `auth.password_reset`.
- Routes: forgot (202 `{"detail": FORGOT_SENT}`), reset (204), verify (204), resend (202, auth). Register schedules the verify email.
- Rate-limit: all under `/auth` → auth bucket (already).
- DB API tests incl. no-enumeration and session revocation.

### Task 4: Verification gate on real sends
- `app/domain/applications/sending.py`: `ensure_can_send(user, settings)` raising `ConflictError("Confirm your email address first...", code="email_unverified")` when smtp and unverified; called in `set_approval_recipient`'s caller (approvals route, before approve) and inside `send_approved_application` (fail outcome).
- Tests (DB): approve refused under smtp when unverified; allowed under console.

### Task 5: Frontend
- `UserOut.email_verified`; endpoints `auth.forgotPassword`, `auth.resetPassword`, `auth.verifyEmail`, `auth.resendVerification`.
- Pages: `(auth)/forgot-password`, `(auth)/reset-password`, `(auth)/verify-email`; "Forgot your password?" on login.
- `VerifyEmailBanner` in `AppShell` (meta.email_delivery != console && !user.email_verified).
- ApprovalCard: `canSend` prop → disabled approve + explanation.
- Tests for each.

### Task 6: Docs + verification
- `.env.example` / `backend/.env.example`: `APP_BASE_URL`. Runbook email section: account emails.
- Backend ruff/mypy/lint-imports/pytest; frontend tsc/lint/vitest. No commit.
