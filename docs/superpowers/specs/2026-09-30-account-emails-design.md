# Forgot password + email verification — design

Date: 2026-09-30. Status: approved in chat ("yes"). Builds on
`2026-09-30-real-email-sending-design.md` (reuses its `EmailSender`).

## Goal

People can recover a forgotten password by email, and confirm their address.
A confirmed address is required before real application emails are sent, so a
public deployment can't be used to email someone whose address was typed in at
sign-up.

## Decisions

1. **One token table** `auth_tokens` (migration 0017): `id`, `user_id` (FK,
   cascade), `purpose` (`password_reset`|`email_verify`), `token_hash`
   (sha256, unique), `expires_at`, `used_at`, `created_at`. Raw tokens are 32
   random bytes (url-safe) and exist only in the email link.
   - Issuing a token marks every earlier unused token of the same purpose for
     that user as used (superseded).
   - TTL: reset 30 minutes, verify 48 hours. Single use.
   - Throttle: at most 3 tokens per user per purpose per rolling hour; beyond
     that nothing is sent (the API response is unchanged).
2. **Endpoints** (all under `/auth`, rate-limited by the existing auth bucket):
   - `POST /password/forgot {email}` → 202, identical body whether or not the
     account exists. The email is sent after the response (FastAPI background
     task), so timing doesn't reveal it either.
   - `POST /password/reset {token, new_password}` → 204. Sets the password,
     consumes the token, revokes every session (all refresh tokens), marks the
     email verified (the link proved inbox ownership), audits. Invalid, used or
     expired token → 400 `invalid_token` with one generic message.
   - `POST /email/verify {token}` → 204; sets `email_verified_at`.
   - `POST /email/verify/resend` (signed in) → 202; no-op if already verified.
   - Sign-up issues a verify token and sends the email in the background.
3. **Links** use a new `APP_BASE_URL` (default `http://localhost:3000`; must be
   http(s); `https` required in production):
   `{APP_BASE_URL}/reset-password#token=…`, `{APP_BASE_URL}/verify-email#token=…`.
   The token is in the fragment so it never reaches server logs or Referer
   headers; the page reads it, then removes it from the address bar.
4. **Verification gate** applies only when real email is on
   (`EMAIL_PROVIDER=smtp`): approving an application email and the send itself
   refuse with "Confirm your email address first". With the console provider
   nothing is enforced (demo works with zero setup).
5. **Account emails** always go to the account's own address (the
   application-email `redirect`/`live` mode doesn't apply), plain text, sender
   `EMAIL_FROM_NAME <EMAIL_FROM_ADDRESS>`, say what was requested, when the
   link expires, and "If you didn't ask for this, you can ignore it."
6. `UserOut` gains `email_verified: bool`.

## UI

- Sign-in page: "Forgot your password?" link.
- `/forgot-password`: email form → "If an account exists for that address,
  we've sent a link. It expires in 30 minutes."
- `/reset-password`: new password + confirm; on success → sign-in with a
  confirmation message; a bad/expired link offers "Request a new link".
- `/verify-email`: confirms on load; success / expired states.
- App banner (only when `email_delivery != console` and not verified):
  "Confirm your email to send applications. We sent a link to you@x.com.
  [Resend link]".
- Approval card: when unverified and real email is on, explains and disables
  "Approve & send".

## Testing

- Pure: token generation/hash, email text builders, `APP_BASE_URL` validation.
- DB (CI): issue supersedes older tokens; throttle; reset consumes + revokes
  sessions + verifies; used/expired/wrong-purpose tokens refused; verify;
  resend; forgot for unknown email sends nothing and returns the same body;
  approval refused when unverified under smtp; allowed under console.
- Frontend: forgot/reset/verify pages, banner, approval-card lock.

## Out of scope

Changing the email address, magic-link sign-in, 2FA.
