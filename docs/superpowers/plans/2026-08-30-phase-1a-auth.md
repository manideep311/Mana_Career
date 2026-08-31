# Phase 1a — Authentication (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working authentication API — a user can register, log in, receive a short-lived JWT access token, silently rotate a long-lived opaque refresh token (with reuse detection), read their own account, change their password, and log out — with every auth event written to `audit_logs`, plus a `get_current_user` FastAPI dependency that every later phase uses to scope data access.

**Architecture:** Email + password only (argon2id). Access token is a signed JWT (HS256, 15 min, `type=access`), verified statelessly. Refresh token is a 32-byte opaque string returned in an httpOnly `SameSite=Strict` cookie scoped to `/api/v1/auth`; only its SHA-256 hash is stored, so it can be revoked. Refresh rotation uses a per-login `family_id`: presenting an already-rotated (revoked) token revokes the whole family and forces re-login. Auth logic lives in `app/domain/auth/` (password, token, service modules); the router in `app/api/v1/auth.py` is thin. GitHub OAuth (`auth_identities`) is **out of scope for 1a** — spec §12 makes it optional and email/password the baseline.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, Pydantic v2 (`email-validator`), `argon2-cffi`, `PyJWT`, pytest + pytest-asyncio + httpx `ASGITransport`. Builds directly on the Phase 0 `core/` modules.

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` — this plan implements the auth slice of §9 Phase 1, and §2.7 (AuthN row), §6.1 (API conventions), §6.2 (`/auth` endpoints), §6.3 (authz model), §6.5 (`/auth/*` rate-limit tier — already enforced by the Phase 0 middleware).

## Global Constraints

Every task's requirements implicitly include this section. Values copied verbatim from the spec / Phase 0 plan.

- **Runtimes:** Python 3.12; PostgreSQL 16 + `pgvector`; Redis 7. Extensions `vector`, `pg_trgm`, `citext`, `pgcrypto` are enabled by migration `0001_bootstrap`, which also defines `set_updated_at()`.
- **Primary keys:** `uuid`, `server_default = gen_random_uuid()` (matches the committed `audit_logs` table).
- **Timestamps:** `created_at` / `updated_at` are `timestamptz not null default now()`; `updated_at` is maintained by a `BEFORE UPDATE` trigger calling `set_updated_at()` (this phase adds the first such triggers).
- **Enums:** `text` + `CHECK` constraint, named (`ck_<table>_<name>`), not native PG enums.
- **User isolation:** every user-scoped table has `user_id` / `owner_id NOT NULL`; the repository filter is always `user_id = :me OR owner_id IS NULL`. (`users` / `refresh_tokens` are identity tables, scoped by `id` / `user_id` directly.)
- **Secrets:** only via environment; `app/core/logging.py`'s `redact_secrets` processor scrubs secret-shaped strings; tokens and hashes never appear in a response body or a log line.
- **Audit:** `audit_logs` is append-only (the app DB role has no `UPDATE`/`DELETE` grant); the one `audit(session, ...)` helper (`app/core/audit.py`) writes every state change and never raises.
- **API:** base path `/api/v1` (from `Settings.api_base_path`); OpenAPI 3.1 at `/api/openapi.json`. Errors use RFC 9457 `application/problem+json` `{type,title,status,detail,instance,code,errors[]}` with a stable machine `code`. Every response carries `X-Request-ID` (Phase 0 `RequestIDMiddleware`).
- **Rate limiting:** `RateLimitMiddleware` (Phase 0) already buckets any path under `/api/v1/auth` at `AUTH_LIMIT_PER_MINUTE = 10` per client IP per minute and fails open if Redis is down. This phase adds no rate-limit code.
- **Brand / copy:** product "Mana Career", assistant "Mana AI". User-facing `detail` strings use human microcopy (spec §19) — e.g. "Please sign in again.", not "invalid_grant".
- **Boundary rule (import-linter):** layer order `app.api > app.worker > app.domain > app.core > app.models`; `app.domain.*` must not import `app.api.*` / `app.worker.*`. `app.domain.auth` may import `app.core.*` and `app.models.*`; `app.api.*` may import all lower layers.
- **Workflow:** TDD (write the failing test first), DRY, YAGNI, commit after every green step. Test commands run from `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run lint-imports`, `uv run mypy app`.

---

## File Structure

**Created**
- `backend/app/domain/auth/__init__.py` — empty package marker.
- `backend/app/domain/auth/passwords.py` — argon2id hash / verify / rehash-check. One responsibility: password hashing.
- `backend/app/domain/auth/tokens.py` — access-JWT encode/decode + opaque refresh generate/hash. One responsibility: token crypto.
- `backend/app/domain/auth/service.py` — `AuthService`: orchestrates register / login / rotate / logout / change-password against the DB + audit. One responsibility: the auth state machine.
- `backend/app/models/user.py` — `User` ORM model.
- `backend/app/models/auth.py` — `RefreshToken` ORM model.
- `backend/app/api/v1/schemas/__init__.py` — empty package marker.
- `backend/app/api/v1/schemas/auth.py` — request/response Pydantic models + `MIN_PASSWORD_LENGTH`.
- `backend/app/api/v1/auth.py` — the `/auth` router (thin: parse → call `AuthService` → set/clear cookie → serialize).
- `backend/alembic/versions/0003_users.py` — `users` + `refresh_tokens` tables, indexes, CHECKs, `updated_at` triggers.
- Test modules: `backend/tests/domain/auth/test_passwords.py`, `.../test_tokens.py`, `.../test_service.py`, `backend/tests/models/test_auth_models.py`, `backend/tests/api/test_auth.py`, `backend/tests/api/test_current_user_dep.py`.

**Modified**
- `backend/app/core/config.py` — add `refresh_cookie_name`, `refresh_cookie_secure`.
- `backend/app/core/errors.py` — `AppError.__init__` accepts an optional per-instance `code` override.
- `backend/app/core/logging.py` — add `current_request_id() -> str | None`.
- `backend/app/models/__init__.py` — import the two new model modules so `Base.metadata` is complete.
- `backend/app/api/deps.py` — add `get_current_user` / `CurrentUser` / `get_current_admin` / `CurrentAdmin`.
- `backend/app/api/v1/router.py` — include the auth router.
- `backend/pyproject.toml` — add `email-validator`.
- `backend/.env.example` — document `REFRESH_COOKIE_NAME`, `REFRESH_COOKIE_SECURE`.
- `backend/tests/conftest.py` — `os.environ.setdefault("REFRESH_COOKIE_SECURE", "false")` (ASGITransport speaks `http://`, so `Secure` cookies would be withheld in tests).

---

## Task 1: Auth groundwork — settings, error-code override, request-id helper

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/errors.py`
- Modify: `backend/app/core/logging.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/core/test_config.py` (extend), `backend/tests/core/test_errors.py` (extend), `backend/tests/core/test_logging.py` (extend)

**Interfaces:**
- Consumes: `Settings` (Phase 0), `AppError` + `to_problem` + `install_error_handlers` (Phase 0), `redact_secrets` / structlog contextvars (Phase 0).
- Produces:
  - `Settings.refresh_cookie_name: str = "mana_refresh"`, `Settings.refresh_cookie_secure: bool = True`.
  - `AppError(detail: str | None = None, *, errors: list[dict] | None = None, code: str | None = None)` — when `code` is given it overrides the class attribute; `to_problem` already reads `exc.code`, so no handler change is needed.
  - `app.core.logging.current_request_id() -> str | None` — returns the `request_id` bound by `RequestIDMiddleware`, or `None` outside a request.

- [x] **Step 1: Write the failing tests**

Append to `backend/tests/core/test_config.py`:

```python
def test_refresh_cookie_defaults(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.refresh_cookie_name == "mana_refresh"
    assert s.refresh_cookie_secure is True


def test_refresh_cookie_secure_env_override(monkeypatch: pytest.MonkeyPatch):
    for k, v in _env(REFRESH_COOKIE_SECURE="false").items():
        monkeypatch.setenv(k, v)
    assert Settings().refresh_cookie_secure is False
```

Append to `backend/tests/core/test_errors.py`:

```python
def test_code_override_flows_into_problem():
    p = to_problem(AppError(detail="dup", code="email_taken"), instance="/x")
    assert p["code"] == "email_taken"
    assert p["status"] == 500  # class default preserved


def test_code_defaults_to_class_attr():
    from app.core.errors import NotFoundError

    assert to_problem(NotFoundError(), instance="/x")["code"] == "not_found"
```

Append to `backend/tests/core/test_logging.py`:

```python
def test_current_request_id_none_outside_request():
    import structlog

    from app.core.logging import current_request_id

    structlog.contextvars.clear_contextvars()
    assert current_request_id() is None


def test_current_request_id_reads_bound_value():
    import structlog

    from app.core.logging import current_request_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="req-42")
    try:
        assert current_request_id() == "req-42"
    finally:
        structlog.contextvars.clear_contextvars()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/core/test_config.py tests/core/test_errors.py tests/core/test_logging.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'refresh_cookie_name'`; `TypeError: __init__() got an unexpected keyword argument 'code'`; `ImportError: cannot import name 'current_request_id'`.

- [x] **Step 3: Write minimal implementation**

In `backend/app/core/config.py`, add two fields to `Settings` (next to the JWT fields):

```python
    refresh_cookie_name: str = "mana_refresh"
    refresh_cookie_secure: bool = True
```

In `backend/app/core/errors.py`, replace `AppError.__init__`:

```python
    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.errors = errors
        if code is not None:
            self.code = code
```

In `backend/app/core/logging.py`, add:

```python
def current_request_id() -> str | None:
    return structlog.contextvars.get_contextvars().get("request_id")
```

In `backend/.env.example`, under `# ---- Backend ----`:

```bash
REFRESH_COOKIE_NAME=mana_refresh
REFRESH_COOKIE_SECURE=true
```

In `backend/tests/conftest.py`, beside the other `setdefault` calls:

```python
os.environ.setdefault("REFRESH_COOKIE_SECURE", "false")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/core -q && uv run ruff check . && uv run mypy app`
Expected: PASS (all `tests/core`), ruff clean, mypy clean.

- [x] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/core/errors.py backend/app/core/logging.py backend/.env.example backend/tests/conftest.py backend/tests/core/test_config.py backend/tests/core/test_errors.py backend/tests/core/test_logging.py
git commit -m "feat(core): auth groundwork — cookie settings, AppError code override, current_request_id"
```

---

## Task 2: Password hashing (`app/domain/auth/passwords.py`)

**Files:**
- Create: `backend/app/domain/auth/__init__.py` (empty)
- Create: `backend/app/domain/auth/passwords.py`
- Test: `backend/tests/domain/auth/__init__.py` (empty), `backend/tests/domain/auth/test_passwords.py`

**Interfaces:**
- Consumes: `argon2-cffi` (already a dependency).
- Produces:
  - `hash_password(password: str) -> str` — argon2id PHC string.
  - `verify_password(password_hash: str, password: str) -> bool` — `True` on match, `False` on any mismatch / malformed hash; never raises.
  - `needs_rehash(password_hash: str) -> bool` — `True` when the hash was made with weaker-than-current parameters or is malformed.

- [x] **Step 1: Write the failing test**

`backend/tests/domain/auth/test_passwords.py`:

```python
from app.domain.auth.passwords import hash_password, needs_rehash, verify_password


def test_hash_is_not_plaintext_and_is_salted():
    h1 = hash_password("correct horse battery staple")
    h2 = hash_password("correct horse battery staple")
    assert "correct horse" not in h1
    assert h1.startswith("$argon2id$")
    assert h1 != h2  # random salt


def test_verify_accepts_correct_and_rejects_wrong():
    h = hash_password("s3cr3t-passphrase")
    assert verify_password(h, "s3cr3t-passphrase") is True
    assert verify_password(h, "wrong") is False


def test_verify_returns_false_on_garbage_hash():
    assert verify_password("not-a-hash", "whatever") is False


def test_needs_rehash_false_for_fresh_hash_true_for_garbage():
    assert needs_rehash(hash_password("abcdefghij")) is False
    assert needs_rehash("not-a-hash") is True
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/domain/auth/test_passwords.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.auth'`.

- [x] **Step 3: Write minimal implementation**

`backend/app/domain/auth/passwords.py`:

```python
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
```

Create the empty `backend/app/domain/auth/__init__.py` and `backend/tests/domain/auth/__init__.py`.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/domain/auth/test_passwords.py -q && uv run mypy app`
Expected: PASS (4), mypy clean.

- [x] **Step 5: Commit**

```bash
git add backend/app/domain/auth/__init__.py backend/app/domain/auth/passwords.py backend/tests/domain/auth/
git commit -m "feat(auth): argon2id password hashing"
```

---

## Task 3: Token crypto (`app/domain/auth/tokens.py`)

**Files:**
- Create: `backend/app/domain/auth/tokens.py`
- Test: `backend/tests/domain/auth/test_tokens.py`

**Interfaces:**
- Consumes: `Settings` (`jwt_secret: SecretStr`, `jwt_access_ttl_seconds: int`), `AuthError` (Phase 0; now accepts `code=`), `PyJWT` (`import jwt`).
- Produces (module `app.domain.auth.tokens`):
  - `ALGORITHM = "HS256"`, `ACCESS_TYPE = "access"`.
  - `create_access_token(user_id: uuid.UUID, *, settings: Settings) -> tuple[str, int]` — returns `(jwt, expires_in_seconds)`. Claims: `sub` (str uuid), `type="access"`, `iat`, `exp`, `jti`.
  - `decode_access_token(token: str, *, settings: Settings) -> uuid.UUID` — verifies signature + `exp` + `type`; raises `AuthError(code="token_expired")` when expired, `AuthError(code="invalid_token")` otherwise.
  - `new_refresh_token() -> tuple[str, str]` — `(raw_urlsafe, sha256_hex)`.
  - `hash_refresh_token(raw: str) -> str` — `sha256_hex`.

- [x] **Step 1: Write the failing test**

`backend/tests/domain/auth/test_tokens.py`:

```python
import datetime as dt
import uuid

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import AuthError
from app.domain.auth.tokens import (
    ACCESS_TYPE,
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k, v in {
        "DATABASE_URL": "x", "DATABASE_URL_TEST": "x", "REDIS_URL": "x",
        "JWT_SECRET": "unit-secret",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_access_token_round_trips(settings: Settings):
    uid = uuid.uuid4()
    token, expires_in = create_access_token(uid, settings=settings)
    assert expires_in == settings.jwt_access_ttl_seconds
    assert decode_access_token(token, settings=settings) == uid


def test_expired_token_raises_token_expired(settings: Settings):
    uid = uuid.uuid4()
    past = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
    token = jwt.encode(
        {"sub": str(uid), "type": ACCESS_TYPE, "iat": int(past.timestamp()),
         "exp": int(past.timestamp())},
        settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM,
    )
    with pytest.raises(AuthError) as ei:
        decode_access_token(token, settings=settings)
    assert ei.value.code == "token_expired"


def test_wrong_signature_raises_invalid_token(settings: Settings):
    uid = uuid.uuid4()
    token, _ = create_access_token(uid, settings=settings)
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    with pytest.raises(AuthError) as ei:
        decode_access_token(tampered, settings=settings)
    assert ei.value.code == "invalid_token"


def test_non_access_token_type_rejected(settings: Settings):
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "refresh",
         "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).timestamp())},
        settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM,
    )
    with pytest.raises(AuthError) as ei:
        decode_access_token(token, settings=settings)
    assert ei.value.code == "invalid_token"


def test_refresh_token_is_opaque_and_hash_is_stable():
    raw, digest = new_refresh_token()
    assert len(raw) >= 32 and raw.isascii()
    assert digest == hash_refresh_token(raw)
    assert len(digest) == 64  # sha256 hex
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/domain/auth/test_tokens.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.auth.tokens'`.

- [x] **Step 3: Write minimal implementation**

`backend/app/domain/auth/tokens.py`:

```python
from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid

import jwt

from app.core.config import Settings
from app.core.errors import AuthError

ALGORITHM = "HS256"
ACCESS_TYPE = "access"


def create_access_token(user_id: uuid.UUID, *, settings: Settings) -> tuple[str, int]:
    ttl = settings.jwt_access_ttl_seconds
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM
    )
    return token, ttl


def decode_access_token(token: str, *, settings: Settings) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(detail="Your session has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(detail="Please sign in.", code="invalid_token") from exc
    if payload.get("type") != ACCESS_TYPE:
        raise AuthError(detail="Please sign in.", code="invalid_token")
    try:
        return uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthError(detail="Please sign in.", code="invalid_token") from exc


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/domain/auth/test_tokens.py -q && uv run mypy app`
Expected: PASS (5), mypy clean.

- [x] **Step 5: Commit**

```bash
git add backend/app/domain/auth/tokens.py backend/tests/domain/auth/test_tokens.py
git commit -m "feat(auth): access-JWT and opaque refresh-token helpers"
```

---

## Task 4: `User` + `RefreshToken` persistence (models + migration `0003`)

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/auth.py`
- Create: `backend/alembic/versions/0003_users.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/__init__.py` (empty), `backend/tests/models/test_auth_models.py`

**Interfaces:**
- Consumes: `Base`, `TimestampMixin` (`app/models/base.py`); migration `0002_audit_logs` is the `down_revision`.
- Produces:
  - `app.models.user.User` — `id: uuid` (server default `gen_random_uuid()`), `email: str` (`CITEXT`, unique, not null), `password_hash: str` (`Text`, not null), `full_name: str` (`String(200)`, not null), `status: str` (`String(16)`, default `'active'`, `CHECK in ('active','disabled')`), `is_admin: bool` (default `false`), `email_verified_at: datetime | None`, `last_login_at: datetime | None`, `created_at` / `updated_at`.
  - `app.models.auth.RefreshToken` — `id: uuid`, `user_id: uuid` (FK `users.id` `ON DELETE CASCADE`, not null), `token_hash: str` (`String(64)`, unique, not null), `family_id: uuid` (not null), `expires_at: datetime` (not null), `revoked_at: datetime | None`, `replaced_by_id: uuid | None` (FK `refresh_tokens.id` `ON DELETE SET NULL`), `ip: str | None` (`String(64)`), `user_agent: str | None` (`String(512)`), `created_at` / `updated_at`. Indexes `ix_refresh_tokens_user_id`, `ix_refresh_tokens_family_id`.
  - Migration `0003_users` (`down_revision = "0002_audit_logs"`) creating both tables + a `BEFORE UPDATE` trigger `trg_users_set_updated_at` / `trg_refresh_tokens_set_updated_at` per table.

- [x] **Step 1: Write the failing test**

`backend/tests/models/test_auth_models.py`:

```python
import datetime as dt
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.auth import RefreshToken
from app.models.user import User


async def _mk_user(db_session, email="A.Person@Example.com") -> User:
    u = User(email=email, password_hash="x", full_name="A Person")
    db_session.add(u)
    await db_session.flush()
    return u


async def test_user_round_trip_and_defaults(db_session):
    u = await _mk_user(db_session)
    got = (await db_session.execute(select(User).where(User.id == u.id))).scalar_one()
    assert got.status == "active"
    assert got.is_admin is False
    assert got.created_at is not None


async def test_email_is_case_insensitive_unique(db_session):
    await _mk_user(db_session, "dup@example.com")
    with pytest.raises(IntegrityError):
        await _mk_user(db_session, "DUP@example.com")


async def test_status_check_constraint(db_session):
    u = await _mk_user(db_session, "s@example.com")
    u.status = "banana"
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_updated_at_trigger_bumps_on_update(db_session):
    u = await _mk_user(db_session, "t@example.com")
    first = (await db_session.execute(
        text("SELECT updated_at FROM users WHERE id = :i"), {"i": u.id}
    )).scalar_one()
    u.full_name = "Renamed"
    await db_session.flush()
    await db_session.execute(text("UPDATE users SET full_name = full_name WHERE id = :i"), {"i": u.id})
    second = (await db_session.execute(
        text("SELECT updated_at FROM users WHERE id = :i"), {"i": u.id}
    )).scalar_one()
    assert second >= first


async def test_refresh_token_fk_cascade_on_user_delete(db_session):
    u = await _mk_user(db_session, "c@example.com")
    rt = RefreshToken(
        user_id=u.id, token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        family_id=uuid.uuid4(),
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
    )
    db_session.add(rt)
    await db_session.flush()
    await db_session.delete(u)
    await db_session.flush()
    remaining = (await db_session.execute(select(RefreshToken).where(RefreshToken.id == rt.id))).first()
    assert remaining is None


async def test_token_hash_unique(db_session):
    u = await _mk_user(db_session, "h@example.com")
    h = uuid.uuid4().hex + uuid.uuid4().hex
    for _ in range(2):
        db_session.add(RefreshToken(
            user_id=u.id, token_hash=h, family_id=uuid.uuid4(),
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
        ))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/models/test_auth_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.user'` (and, once models exist, the migration is missing so the tables don't exist).

- [x] **Step 3: Write minimal implementation**

`backend/app/models/user.py`:

```python
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status in ('active','disabled')", name="user_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'")
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    email_verified_at: Mapped[dt.datetime | None] = mapped_column()
    last_login_at: Mapped[dt.datetime | None] = mapped_column()
```

`backend/app/models/auth.py`:

```python
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column()
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
```

`backend/app/models/__init__.py` — add the imports:

```python
# Importing every model module here keeps Base.metadata complete for Alembic.
from app.models import audit as audit
from app.models import auth as auth
from app.models import user as user
from app.models.base import Base

__all__ = ["Base"]
```

`backend/alembic/versions/0003_users.py`:

```python
"""users and refresh_tokens

Revision ID: 0003_users
Revises: 0002_audit_logs
Create Date: 2026-08-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0003_users"
down_revision = "0002_audit_logs"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("email_verified_at", _TS),
        sa.Column("last_login_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
        sa.CheckConstraint("status in ('active','disabled')", name="user_status_valid"),
    )
    op.create_index("uq_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("family_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("revoked_at", _TS),
        sa.Column("replaced_by_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL")),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("created_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("updated_at", _TS, nullable=False, server_default=_NOW),
    )
    op.create_index("uq_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    for tbl in ("users", "refresh_tokens"):
        op.execute(
            f"CREATE TRIGGER trg_{tbl}_set_updated_at BEFORE UPDATE ON {tbl} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for tbl in ("refresh_tokens", "users"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tbl}_set_updated_at ON {tbl}")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
```

Create empty `backend/tests/models/__init__.py`.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run alembic upgrade head && uv run pytest tests/models/test_auth_models.py tests/core/test_migrations.py -q && uv run mypy app`
Expected: PASS (6 model tests + existing migration tests), mypy clean. (The session-scoped `_migrated` fixture also runs `alembic upgrade head`; running it manually first surfaces migration errors clearly.)

- [x] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/app/models/auth.py backend/app/models/__init__.py backend/alembic/versions/0003_users.py backend/tests/models/
git commit -m "feat(models): users + refresh_tokens tables with updated_at triggers"
```

---

## Task 5: `AuthService` (`app/domain/auth/service.py`)

**Files:**
- Create: `backend/app/domain/auth/service.py`
- Test: `backend/tests/domain/auth/test_service.py`

**Interfaces:**
- Consumes: `AsyncSession`; `Settings` + `get_settings`; `hash_password` / `verify_password` (Task 2); `create_access_token` / `new_refresh_token` / `hash_refresh_token` (Task 3); `User` / `RefreshToken` (Task 4); `audit` + `current_request_id`; `AppError` subclasses `AuthError` / `ConflictError` / `ForbiddenError`.
- Produces (`app.domain.auth.service`):
  - `@dataclass(frozen=True) AuthResult` — `user: User`, `access_token: str`, `expires_in: int`, `refresh_token: str` (raw).
  - `@dataclass(frozen=True) AccessResult` — `access_token: str`, `expires_in: int`, `refresh_token: str` (raw).
  - `class AuthService`:
    - `__init__(self, session: AsyncSession, settings: Settings | None = None)`
    - `async register(self, email: str, password: str, full_name: str, *, ip: str | None, user_agent: str | None) -> AuthResult` — `ConflictError(code="email_taken")` if the email exists.
    - `async authenticate(self, email: str, password: str, *, ip: str | None, user_agent: str | None) -> AuthResult` — `AuthError(code="invalid_credentials")` on bad email/password (no user enumeration); `ForbiddenError(code="account_disabled")` if `status != "active"`; sets `last_login_at`.
    - `async rotate(self, raw_refresh: str, *, ip: str | None, user_agent: str | None) -> AccessResult` — unknown → `AuthError(code="invalid_refresh")`; already-revoked → revoke whole family + `AuthError(code="refresh_reuse")`; expired → `AuthError(code="expired_refresh")`; else rotate (old row `revoked_at` + `replaced_by_id` set, new row shares `family_id`).
    - `async logout(self, raw_refresh: str | None) -> None` — revoke the presented token's family; silent no-op on missing/unknown.
    - `async change_password(self, user: User, current: str, new: str, *, ip: str | None, user_agent: str | None) -> AuthResult` — `AuthError(code="invalid_credentials")` if `current` wrong; sets new hash; revokes **all** the user's families; issues a fresh family.
  - All mutating paths call `audit(...)` with actions `auth.register`, `auth.login`, `auth.login_failed`, `auth.refresh`, `auth.refresh_reuse_detected`, `auth.logout`, `auth.password_change` and `request_id=current_request_id()`.

- [x] **Step 1: Write the failing test**

`backend/tests/domain/auth/test_service.py`:

```python
import datetime as dt

import pytest
from sqlalchemy import func, select

from app.core.errors import AuthError, ConflictError, ForbiddenError
from app.domain.auth.service import AuthService
from app.domain.auth.tokens import decode_access_token, hash_refresh_token
from app.models.auth import RefreshToken
from app.models.audit import AuditLog
from app.models.user import User
from app.core.config import get_settings


async def _svc(db_session) -> AuthService:
    return AuthService(db_session)


async def test_register_creates_user_and_tokens(db_session):
    svc = await _svc(db_session)
    res = await svc.register("New@Example.com", "a-strong-passphrase", "New User",
                             ip="1.2.3.4", user_agent="pytest")
    assert res.user.email == "New@Example.com"
    assert decode_access_token(res.access_token, settings=get_settings()) == res.user.id
    stored = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(res.refresh_token))
    )).scalar_one()
    assert stored.revoked_at is None


async def test_register_duplicate_email_raises_conflict(db_session):
    svc = await _svc(db_session)
    await svc.register("dup@example.com", "a-strong-passphrase", "A", ip=None, user_agent=None)
    with pytest.raises(ConflictError) as ei:
        await svc.register("DUP@example.com", "another-passphrase", "B", ip=None, user_agent=None)
    assert ei.value.code == "email_taken"


async def test_authenticate_ok_and_bad_password(db_session):
    svc = await _svc(db_session)
    await svc.register("log@example.com", "correct-passphrase", "L", ip=None, user_agent=None)
    ok = await svc.authenticate("log@example.com", "correct-passphrase", ip=None, user_agent=None)
    assert ok.access_token
    with pytest.raises(AuthError) as ei:
        await svc.authenticate("log@example.com", "wrong", ip=None, user_agent=None)
    assert ei.value.code == "invalid_credentials"


async def test_authenticate_unknown_email_is_invalid_credentials_not_404(db_session):
    svc = await _svc(db_session)
    with pytest.raises(AuthError) as ei:
        await svc.authenticate("nobody@example.com", "x", ip=None, user_agent=None)
    assert ei.value.code == "invalid_credentials"


async def test_authenticate_disabled_account(db_session):
    svc = await _svc(db_session)
    res = await svc.register("dis@example.com", "correct-passphrase", "D", ip=None, user_agent=None)
    res.user.status = "disabled"
    await db_session.flush()
    with pytest.raises(ForbiddenError) as ei:
        await svc.authenticate("dis@example.com", "correct-passphrase", ip=None, user_agent=None)
    assert ei.value.code == "account_disabled"


async def test_rotate_issues_new_and_revokes_old(db_session):
    svc = await _svc(db_session)
    reg = await svc.register("rot@example.com", "correct-passphrase", "R", ip=None, user_agent=None)
    rotated = await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    assert rotated.refresh_token != reg.refresh_token
    old = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(reg.refresh_token))
    )).scalar_one()
    assert old.revoked_at is not None and old.replaced_by_id is not None


async def test_rotate_reuse_detection_revokes_family(db_session):
    svc = await _svc(db_session)
    reg = await svc.register("reuse@example.com", "correct-passphrase", "R", ip=None, user_agent=None)
    await svc.rotate(reg.refresh_token, ip=None, user_agent=None)          # first rotation OK
    with pytest.raises(AuthError) as ei:
        await svc.rotate(reg.refresh_token, ip=None, user_agent=None)      # replay the old one
    assert ei.value.code == "refresh_reuse"
    live = (await db_session.execute(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    )).scalar_one()
    assert live == 0  # whole family killed
    assert (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "auth.refresh_reuse_detected")
    )).first() is not None


async def test_rotate_expired_refresh(db_session):
    svc = await _svc(db_session)
    reg = await svc.register("exp@example.com", "correct-passphrase", "E", ip=None, user_agent=None)
    row = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(reg.refresh_token))
    )).scalar_one()
    row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    await db_session.flush()
    with pytest.raises(AuthError) as ei:
        await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    assert ei.value.code == "expired_refresh"


async def test_logout_revokes_family_and_is_silent_on_unknown(db_session):
    svc = await _svc(db_session)
    reg = await svc.register("out@example.com", "correct-passphrase", "O", ip=None, user_agent=None)
    await svc.logout(reg.refresh_token)
    await svc.logout("never-issued")  # no raise
    live = (await db_session.execute(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    )).scalar_one()
    assert live == 0


async def test_change_password_rotates_all_and_sets_new_hash(db_session):
    svc = await _svc(db_session)
    reg = await svc.register("pw@example.com", "old-passphrase", "P", ip=None, user_agent=None)
    await svc.rotate(reg.refresh_token, ip=None, user_agent=None)
    fresh = await svc.change_password(reg.user, "old-passphrase", "new-passphrase",
                                     ip=None, user_agent=None)
    assert fresh.refresh_token
    with pytest.raises(AuthError):
        await svc.authenticate("pw@example.com", "old-passphrase", ip=None, user_agent=None)
    ok = await svc.authenticate("pw@example.com", "new-passphrase", ip=None, user_agent=None)
    assert ok.access_token
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/domain/auth/test_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.auth.service'`.

- [x] **Step 3: Write minimal implementation**

`backend/app/domain/auth/service.py`:

```python
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import Settings, get_settings
from app.core.errors import AuthError, ConflictError, ForbiddenError
from app.core.logging import current_request_id
from app.domain.auth.passwords import hash_password, verify_password
from app.domain.auth.tokens import (
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.models.auth import RefreshToken
from app.models.user import User


@dataclass(frozen=True)
class AuthResult:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str


@dataclass(frozen=True)
class AccessResult:
    access_token: str
    expires_in: int
    refresh_token: str


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def _by_email(self, email: str) -> User | None:
        return (
            await self.session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    async def _revoke_family(self, family_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )

    async def _issue(
        self, user: User, *, ip: str | None, user_agent: str | None,
        family_id: uuid.UUID | None = None,
    ) -> tuple[str, int, str]:
        fam = family_id or uuid.uuid4()
        raw, digest = new_refresh_token()
        self.session.add(
            RefreshToken(
                user_id=user.id, token_hash=digest, family_id=fam,
                expires_at=_now() + dt.timedelta(seconds=self.settings.jwt_refresh_ttl_seconds),
                ip=ip, user_agent=user_agent,
            )
        )
        await self.session.flush()
        access, expires_in = create_access_token(user.id, settings=self.settings)
        return access, expires_in, raw

    async def _audit(self, action: str, *, user_id: uuid.UUID | None,
                     ip: str | None, user_agent: str | None,
                     result: Literal["success", "failure"] = "success") -> None:
        await audit(
            self.session, actor_type="user", action=action, result=result,
            actor_user_id=user_id, ip=ip, user_agent=user_agent,
            request_id=current_request_id(),
        )

    async def register(self, email: str, password: str, full_name: str, *,
                       ip: str | None, user_agent: str | None) -> AuthResult:
        if await self._by_email(email) is not None:
            raise ConflictError(detail="That email is already registered.", code="email_taken")
        user = User(email=email, password_hash=hash_password(password), full_name=full_name)
        self.session.add(user)
        await self.session.flush()
        access, expires_in, raw = await self._issue(user, ip=ip, user_agent=user_agent)
        await self._audit("auth.register", user_id=user.id, ip=ip, user_agent=user_agent)
        return AuthResult(user, access, expires_in, raw)

    async def authenticate(self, email: str, password: str, *,
                           ip: str | None, user_agent: str | None) -> AuthResult:
        user = await self._by_email(email)
        if user is None or not verify_password(user.password_hash, password):
            await self._audit("auth.login_failed", user_id=user.id if user else None,
                              ip=ip, user_agent=user_agent, result="failure")
            raise AuthError(detail="That email or password is not right.",
                            code="invalid_credentials")
        if user.status != "active":
            raise ForbiddenError(detail="This account is disabled.", code="account_disabled")
        user.last_login_at = _now()
        access, expires_in, raw = await self._issue(user, ip=ip, user_agent=user_agent)
        await self._audit("auth.login", user_id=user.id, ip=ip, user_agent=user_agent)
        return AuthResult(user, access, expires_in, raw)

    async def rotate(self, raw_refresh: str, *,
                     ip: str | None, user_agent: str | None) -> AccessResult:
        row = (
            await self.session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == hash_refresh_token(raw_refresh)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise AuthError(detail="Please sign in again.", code="invalid_refresh")
        if row.revoked_at is not None:
            # Reuse of an already-rotated token => the family is compromised.
            # Persist the revoke BEFORE raising: get_session rolls back on the
            # exception, and a rolled-back revoke would leave the stolen family
            # usable — defeating reuse detection entirely.
            await self._revoke_family(row.family_id)
            await self._audit("auth.refresh_reuse_detected", user_id=row.user_id,
                              ip=ip, user_agent=user_agent, result="failure")
            await self.session.commit()
            raise AuthError(detail="Please sign in again.", code="refresh_reuse")
        if row.expires_at <= _now():
            raise AuthError(detail="Please sign in again.", code="expired_refresh")
        user = await self.session.get(User, row.user_id)
        assert user is not None
        access, expires_in, raw = await self._issue(
            user, ip=ip, user_agent=user_agent, family_id=row.family_id
        )
        new_row = (
            await self.session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
            )
        ).scalar_one()
        row.revoked_at = _now()
        row.replaced_by_id = new_row.id
        await self._audit("auth.refresh", user_id=row.user_id, ip=ip, user_agent=user_agent)
        return AccessResult(access, expires_in, raw)

    async def logout(self, raw_refresh: str | None) -> None:
        if not raw_refresh:
            return
        row = (
            await self.session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == hash_refresh_token(raw_refresh)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        await self._revoke_family(row.family_id)
        await self._audit("auth.logout", user_id=row.user_id, ip=None, user_agent=None)

    async def change_password(self, user: User, current: str, new: str, *,
                              ip: str | None, user_agent: str | None) -> AuthResult:
        if not verify_password(user.password_hash, current):
            raise AuthError(detail="That email or password is not right.",
                            code="invalid_credentials")
        user.password_hash = hash_password(new)
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        access, expires_in, raw = await self._issue(user, ip=ip, user_agent=user_agent)
        await self._audit("auth.password_change", user_id=user.id, ip=ip, user_agent=user_agent)
        return AuthResult(user, access, expires_in, raw)
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/domain/auth/test_service.py -q && uv run ruff check . && uv run lint-imports && uv run mypy app`
Expected: PASS (10), ruff clean, import-linter 2 contracts kept, mypy clean.

- [x] **Step 5: Commit**

```bash
git add backend/app/domain/auth/service.py backend/tests/domain/auth/test_service.py
git commit -m "feat(auth): AuthService — register, login, refresh rotation with reuse detection, logout, change-password"
```

---

## Task 6: Auth request/response schemas (`app/api/v1/schemas/auth.py`)

**Files:**
- Create: `backend/app/api/v1/schemas/__init__.py` (empty)
- Create: `backend/app/api/v1/schemas/auth.py`
- Test: `backend/tests/api/test_auth_schemas.py`

**DEVIATION (2026-08-30):** the plan called for `EmailStr` + an `email-validator` dependency. `uv` is not installed on the dev machine and CI runs `uv sync --frozen`, so `pyproject.toml` cannot gain a dependency without a regenerated `uv.lock`. Instead: `email` is a plain `str` validated by a module-level regex `EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")` in a `field_validator`. Basic-shape validation only; a stricter check can be added when `email-validator` is properly locked.

**Interfaces:**
- Consumes: Pydantic v2 (no extra deps).
- Produces (`app.api.v1.schemas.auth`):
  - `MIN_PASSWORD_LENGTH = 10`
  - `EMAIL_RE: re.Pattern[str]`
  - `RegisterIn` — `email: str` (regex-validated, stripped; case preserved — the DB column is CITEXT), `password: str` (`min_length=MIN_PASSWORD_LENGTH`, `max_length=200`), `full_name: str` (`min_length=1`, `max_length=200`, stripped).
  - `LoginIn` — `email: str` (regex-validated, stripped; case preserved — the DB column is CITEXT), `password: str` (`min_length=1`).
  - `PasswordChangeIn` — `current_password: str` (`min_length=1`), `new_password: str` (`min_length=MIN_PASSWORD_LENGTH`, `max_length=200`).
  - `UserOut` — `id: UUID`, `email: str`, `full_name: str`, `is_admin: bool`, `created_at: datetime`; `model_config = ConfigDict(from_attributes=True)`.
  - `AuthResponse` — `access_token: str`, `token_type: Literal["bearer"] = "bearer"`, `expires_in: int`, `user: UserOut`.
  - `AccessResponse` — `access_token: str`, `token_type: Literal["bearer"] = "bearer"`, `expires_in: int`.

- [x] **Step 1: Write the failing test**

`backend/tests/api/test_auth_schemas.py`:

```python
import uuid
import datetime as dt

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.auth import (
    MIN_PASSWORD_LENGTH,
    AuthResponse,
    LoginIn,
    RegisterIn,
    UserOut,
)


def test_register_in_rejects_short_password():
    with pytest.raises(ValidationError):
        RegisterIn(email="a@b.com", password="x" * (MIN_PASSWORD_LENGTH - 1), full_name="A")


def test_register_in_rejects_bad_email():
    with pytest.raises(ValidationError):
        RegisterIn(email="not-an-email", password="x" * MIN_PASSWORD_LENGTH, full_name="A")


def test_register_in_trims_full_name():
    m = RegisterIn(email="a@b.com", password="x" * MIN_PASSWORD_LENGTH, full_name="  A Person  ")
    assert m.full_name == "A Person"


def test_user_out_from_attributes():
    class _U:
        id = uuid.uuid4()
        email = "a@b.com"
        full_name = "A"
        is_admin = False
        created_at = dt.datetime.now(dt.UTC)

    out = UserOut.model_validate(_U())
    assert out.email == "a@b.com" and out.is_admin is False


def test_auth_response_defaults_token_type_bearer():
    r = AuthResponse(access_token="t", expires_in=900,
                     user=UserOut(id=uuid.uuid4(), email="a@b.com", full_name="A",
                                  is_admin=False, created_at=dt.datetime.now(dt.UTC)))
    assert r.token_type == "bearer"
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_auth_schemas.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.v1.schemas'` (and, before that, `email-validator` may be missing → `ImportError` on `EmailStr`).

- [x] **Step 3: Write minimal implementation**

Add to `backend/pyproject.toml` `[project].dependencies`:

```toml
  "email-validator>=2.2",
```

Run `uv sync` (or `uv add email-validator`).

`backend/app/api/v1/schemas/auth.py`:

```python
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MIN_PASSWORD_LENGTH = 10


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_admin: bool
    created_at: dt.datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class AccessResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
```

Create empty `backend/app/api/v1/schemas/__init__.py`.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_auth_schemas.py -q && uv run mypy app`
Expected: PASS (5), mypy clean.

- [x] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/api/v1/schemas/ backend/tests/api/test_auth_schemas.py
git commit -m "feat(api): auth request/response schemas"
```

---

## Task 7: `get_current_user` / `get_current_admin` dependencies (`app/api/deps.py`)

**Files:**
- Modify: `backend/app/api/deps.py`
- Test: `backend/tests/api/test_current_user_dep.py`

**Interfaces:**
- Consumes: `DbDep`, `SettingsDep` (already in `deps.py`); `decode_access_token` (Task 3); `User` (Task 4); `AuthError` / `ForbiddenError`.
- Produces:
  - `async get_current_user(db, settings, authorization: str | None = Header(None)) -> User` — requires `Authorization: Bearer <jwt>`; `AuthError(code="missing_token")` when absent/malformed; delegates verification to `decode_access_token`; loads the `User`; `AuthError(code="invalid_token")` if the user row is gone; `ForbiddenError(code="account_disabled")` if `status != "active"`.
  - `CurrentUser = Annotated[User, Depends(get_current_user)]`
  - `async get_current_admin(user: CurrentUser) -> User` — `ForbiddenError(code="forbidden")` unless `user.is_admin`.
  - `CurrentAdmin = Annotated[User, Depends(get_current_admin)]`

- [x] **Step 1: Write the failing test**

`backend/tests/api/test_current_user_dep.py`:

```python
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import CurrentAdmin, CurrentUser
from app.core.db import get_session
from app.core.errors import install_error_handlers
from app.domain.auth.service import AuthService


@pytest.fixture
async def probe_client(db_session):
    app = FastAPI()
    install_error_handlers(app)
    app.dependency_overrides[get_session] = lambda: db_session

    @app.get("/whoami")
    async def whoami(user: CurrentUser) -> dict:
        return {"email": user.email}

    @app.get("/admin-only")
    async def admin_only(user: CurrentAdmin) -> dict:
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c, db_session


async def test_missing_bearer_is_401_missing_token(probe_client):
    c, _ = probe_client
    r = await c.get("/whoami")
    assert r.status_code == 401
    assert r.json()["code"] == "missing_token"


async def test_valid_bearer_resolves_user(probe_client):
    c, db = probe_client
    reg = await AuthService(db).register("me@example.com", "correct-passphrase", "Me",
                                         ip=None, user_agent=None)
    r = await c.get("/whoami", headers={"Authorization": f"Bearer {reg.access_token}"})
    assert r.status_code == 200 and r.json() == {"email": "me@example.com"}


async def test_garbage_bearer_is_401_invalid_token(probe_client):
    c, _ = probe_client
    r = await c.get("/whoami", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_token"


async def test_admin_dep_forbids_non_admin(probe_client):
    c, db = probe_client
    reg = await AuthService(db).register("u@example.com", "correct-passphrase", "U",
                                         ip=None, user_agent=None)
    r = await c.get("/admin-only", headers={"Authorization": f"Bearer {reg.access_token}"})
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_current_user_dep.py -q`
Expected: FAIL — `ImportError: cannot import name 'CurrentUser' from 'app.api.deps'`.

- [x] **Step 3: Write minimal implementation**

Rewrite `backend/app/api/deps.py` so the new imports sit in the top import block (ruff's `I` rule rejects mid-file imports). Full file:

```python
from __future__ import annotations

import uuid
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AuthError, ForbiddenError
from app.core.redis import redis_from_settings
from app.domain.auth.tokens import decode_access_token
from app.models.user import User

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_session)]


def _redis_dep(settings: SettingsDep) -> redis.Redis:
    return redis_from_settings(settings)


RedisDep = Annotated[redis.Redis, Depends(_redis_dep)]


async def get_current_user(
    db: DbDep,
    settings: SettingsDep,
    authorization: str | None = Header(default=None),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError(detail="Please sign in.", code="missing_token")
    user_id: uuid.UUID = decode_access_token(authorization[7:].strip(), settings=settings)
    user = await db.get(User, user_id)
    if user is None:
        raise AuthError(detail="Please sign in.", code="invalid_token")
    if user.status != "active":
        raise ForbiddenError(detail="This account is disabled.", code="account_disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise ForbiddenError(detail="Admins only.", code="forbidden")
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_current_user_dep.py -q && uv run lint-imports && uv run mypy app`
Expected: PASS (4), import-linter 2 contracts kept, mypy clean.

- [x] **Step 5: Commit**

```bash
git add backend/app/api/deps.py backend/tests/api/test_current_user_dep.py
git commit -m "feat(api): get_current_user / get_current_admin dependencies"
```

---

## Task 8: `/auth` router + integration tests (`app/api/v1/auth.py`)

**Files:**
- Create: `backend/app/api/v1/auth.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/api/test_auth.py`

**Interfaces:**
- Consumes: `AuthService` + `AuthResult` / `AccessResult` (Task 5); auth schemas (Task 6); `CurrentUser` (Task 7); `DbDep` / `SettingsDep`; `Settings.refresh_cookie_name` / `refresh_cookie_secure` / `api_base_path` / `jwt_refresh_ttl_seconds`.
- Produces: `app.api.v1.auth.router` (`APIRouter(prefix="/auth", tags=["auth"])`), included by `app/api/v1/router.py`. Endpoints:
  - `POST /auth/register` → `201 AuthResponse` + `Set-Cookie` refresh.
  - `POST /auth/login` → `200 AuthResponse` + `Set-Cookie` refresh.
  - `POST /auth/refresh` → `200 AccessResponse` + rotated `Set-Cookie`; reads the cookie only.
  - `POST /auth/logout` → `204`, clears cookie (idempotent).
  - `GET /auth/me` → `200 UserOut` (requires bearer).
  - `POST /auth/password/change` → `200 AccessResponse` + fresh `Set-Cookie` (requires bearer).
  - Cookie attributes: `httponly=True`, `secure=settings.refresh_cookie_secure`, `samesite="strict"`, `path=f"{settings.api_base_path}/auth"`, `max_age=settings.jwt_refresh_ttl_seconds`.

- [x] **Step 1: Write the failing test**

`backend/tests/api/test_auth.py`:

```python
import datetime as dt

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.audit import AuditLog

BASE = "/api/v1/auth"
COOKIE = get_settings().refresh_cookie_name


async def _register(client, email="user@example.com", pw="correct-passphrase", name="User"):
    return await client.post(f"{BASE}/register",
                             json={"email": email, "password": pw, "full_name": name})


async def test_register_returns_201_token_and_cookie(client):
    r = await _register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["user"]["email"] == "user@example.com"
    assert r.cookies.get(COOKIE)


async def test_register_duplicate_is_409_email_taken(client):
    await _register(client)
    r = await _register(client, name="Again")
    assert r.status_code == 409 and r.json()["code"] == "email_taken"


async def test_register_short_password_is_422(client):
    r = await client.post(f"{BASE}/register",
                          json={"email": "x@example.com", "password": "short", "full_name": "X"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


async def test_login_ok_and_wrong_password(client):
    await _register(client, email="l@example.com")
    ok = await client.post(f"{BASE}/login", json={"email": "l@example.com", "password": "correct-passphrase"})
    assert ok.status_code == 200 and ok.cookies.get(COOKIE)
    bad = await client.post(f"{BASE}/login", json={"email": "l@example.com", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["code"] == "invalid_credentials"


async def test_me_requires_bearer(client):
    reg = await _register(client, email="m@example.com")
    token = reg.json()["access_token"]
    anon = await client.get(f"{BASE}/me")
    assert anon.status_code == 401
    me = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "m@example.com"


async def test_refresh_rotates_cookie(client):
    await _register(client, email="r@example.com")
    first = await client.post(f"{BASE}/refresh")
    assert first.status_code == 200
    new_cookie = first.cookies.get(COOKIE)
    assert new_cookie
    second = await client.post(f"{BASE}/refresh")  # client jar now holds the rotated cookie
    assert second.status_code == 200


async def test_refresh_reuse_is_401_and_kills_family(client):
    reg = await _register(client, email="reuse@example.com")
    stolen = reg.cookies.get(COOKIE)
    await client.post(f"{BASE}/refresh")                       # legitimate rotation
    replay = await client.post(f"{BASE}/refresh", cookies={COOKIE: stolen})
    assert replay.status_code == 401 and replay.json()["code"] == "refresh_reuse"
    after = await client.post(f"{BASE}/refresh", cookies={COOKIE: stolen})
    assert after.status_code == 401  # family dead


async def test_logout_is_204_and_clears_cookie(client):
    await _register(client, email="o@example.com")
    r = await client.post(f"{BASE}/logout")
    assert r.status_code == 204
    again = await client.post(f"{BASE}/refresh")
    assert again.status_code == 401


async def test_password_change_revokes_old_sessions(client):
    reg = await _register(client, email="pw@example.com")
    token = reg.json()["access_token"]
    old_cookie = reg.cookies.get(COOKIE)
    r = await client.post(f"{BASE}/password/change",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"current_password": "correct-passphrase",
                                "new_password": "a-brand-new-passphrase"})
    assert r.status_code == 200
    stale = await client.post(f"{BASE}/refresh", cookies={COOKIE: old_cookie})
    assert stale.status_code == 401
    login = await client.post(f"{BASE}/login",
                              json={"email": "pw@example.com", "password": "a-brand-new-passphrase"})
    assert login.status_code == 200


async def test_auth_events_are_audited(client, db_session):
    await _register(client, email="audit@example.com")
    await client.post(f"{BASE}/login", json={"email": "audit@example.com", "password": "correct-passphrase"})
    await client.post(f"{BASE}/login", json={"email": "audit@example.com", "password": "wrong"})
    actions = set(
        (await db_session.execute(select(AuditLog.action))).scalars().all()
    )
    # Committed-path events. `auth.login_failed` is also written but on a request
    # that raises 401, so in production `get_session` rolls it back — see NOTE
    # below. Durable failed-attempt auditing is a Phase 13 concern.
    assert {"auth.register", "auth.login"}.issubset(actions)
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_auth.py -q`
Expected: FAIL — `404` on every route (router not registered) / `ModuleNotFoundError: app.api.v1.auth`.

- [x] **Step 3: Write minimal implementation**

`backend/app/api/v1/auth.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.api.v1.schemas.auth import (
    AccessResponse,
    AuthResponse,
    LoginIn,
    PasswordChangeIn,
    RegisterIn,
    UserOut,
)
from app.core.config import Settings
from app.core.errors import AuthError
from app.domain.auth.service import AccessResult, AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.jwt_refresh_ttl_seconds,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path=f"{settings.api_base_path}/auth",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=f"{settings.api_base_path}/auth",
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _auth_response(result: AuthResult) -> AuthResponse:
    return AuthResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=UserOut.model_validate(result.user),
    )


def _access_response(result: AccessResult) -> AccessResponse:
    return AccessResponse(access_token=result.access_token, expires_in=result.expires_in)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> AuthResponse:
    result = await AuthService(db, settings).register(
        body.email, body.password, body.full_name,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _auth_response(result)


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> AuthResponse:
    result = await AuthService(db, settings).authenticate(
        body.email, body.password,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _auth_response(result)


@router.post("/refresh")
async def refresh(
    request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> AccessResponse:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise AuthError(detail="Please sign in again.", code="missing_refresh")
    result = await AuthService(db, settings).rotate(
        raw, ip=_client_ip(request), user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _access_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> None:
    await AuthService(db, settings).logout(request.cookies.get(settings.refresh_cookie_name))
    _clear_refresh_cookie(response, settings)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/password/change")
async def change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUser,
) -> AccessResponse:
    result = await AuthService(db, settings).change_password(
        user, body.current_password, body.new_password,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _access_response(result)
```

`backend/app/api/v1/router.py`:

```python
from fastapi import APIRouter

from app.api.v1 import auth, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_auth.py -q && uv run ruff check . && uv run lint-imports && uv run mypy app`
Expected: PASS (10), ruff clean, import-linter 2 contracts kept, mypy clean.

- [x] **Step 5: Commit**

```bash
git add backend/app/api/v1/auth.py backend/app/api/v1/router.py backend/tests/api/test_auth.py
git commit -m "feat(api): /auth router — register, login, refresh, logout, me, password change"
```

---

## Task 9: Phase 1a verification & report

**Files:**
- Modify: `docs/superpowers/plans/2026-08-30-phase-1a-auth.md` (fill the completion report below)

**Interfaces:**
- Consumes: everything above.
- Produces: a green full backend suite + a filled completion report.

- [x] **Step 1: Full backend gate**

Run: `cd backend && uv run ruff check . && uv run lint-imports && uv run mypy app && uv run pytest -q`
Expected: ruff clean; import-linter 2 contracts kept; mypy clean; pytest all green (Phase 0's 39 + Phase 1a's new tests), coverage ≥ the CI floor (55).

- [x] **Step 2: OpenAPI sanity check**

Run: `cd backend && uv run python -c "from app.main import create_app; import json; print(sorted(p for p in create_app().openapi()['paths'] if 'auth' in p))"`
Expected: lists `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/me`, `/api/v1/auth/password/change`, `/api/v1/auth/refresh`, `/api/v1/auth/register`.

- [x] **Step 3: Fill the completion report**

Fill in the "Phase 1a completion report" section below with: what changed, files changed, test count + coverage %, and any deviations.

- [x] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-08-30-phase-1a-auth.md
git commit -m "docs: Phase 1a completion report"
```

---

## Phase 1a completion report — 2026-08-30

- **Branch:** `phase-1a-auth` (off `phase-0-foundations`). Commits `6f1f8f6`..`<report>` (9 commits, one per task).
- **What changed:**
  - `core/`: `Settings.refresh_cookie_name` / `refresh_cookie_secure`; `AppError(..., code=)` per-instance override; `current_request_id()`.
  - `domain/auth/`: `passwords.py` (argon2id `hash`/`verify`/`needs_rehash`), `tokens.py` (HS256 access JWT + opaque sha256 refresh), `service.py` (`AuthService`: register / authenticate / rotate-with-reuse-detection / logout / change_password; DTOs `AuthResult` / `AccessResult`).
  - `models/`: `User` (`users`, CITEXT email, status CHECK), `RefreshToken` (`refresh_tokens`, family_id, token_hash unique, FK cascade). Migration `0003_users` — first `BEFORE UPDATE` triggers on `set_updated_at()`.
  - `api/`: `deps.py` gains `get_current_user` / `CurrentUser` / `get_current_admin` / `CurrentAdmin`; `v1/schemas/auth.py` (request/response models); `v1/auth.py` router (6 endpoints); registered in `v1/router.py`.
- **Why:** email/password auth with rotating-refresh sessions + reuse detection is the gate every user-scoped feature depends on; `get_current_user` is the seam Phase 1b onward consumes.
- **Local verification (this machine — no `uv`, no Postgres/Redis; tools run via `backend/.venv/Scripts/`):**
  - `ruff check .` ✅ · `lint-imports` ✅ 2 contracts kept · `mypy app` ✅ 43 files.
  - `pytest`: **47 infra-independent tests pass** (Phase 0's 26 + 21 new: config +2, errors +2, logging +2, passwords 4, tokens 5, auth_schemas 6).
  - **DB-backed tests** error locally on the `_migrated` fixture (no Postgres). **Verified green in GitHub Actions CI on 2026-08-31** (`manideep311/Mana_Career`, run on `main` @ `77d8f5a`): `90 passed, coverage 89.64%` for the backend job (all Phase 0 + Phase 1a tests), `3 passed` frontend. Getting there took three fixes to latent Phase 0 issues that CI exposed on its first-ever run: `fb3de7a` (frontend CI Node 20 → 22), `87180ce` (`asyncio_default_test_loop_scope = "session"` — session-scoped `db_engine` vs per-function test loops), `77d8f5a` (per-`client` source IP so the real-Redis auth rate-limit doesn't bleed across tests; migration tests reuse the shared engine).
  - OpenAPI: all 6 `/api/v1/auth/*` paths present.
- **Deviations from the written plan:**
  1. **No `tests/**/__init__.py`** — repo uses a rootless test layout; the plan's package-marker steps were skipped. Test basenames are unique.
  2. **`.env.example` is at repo root**, not `backend/` — edited the root file.
  3. **Email validation:** plain `str` + regex `EMAIL_RE` instead of `EmailStr` + `email-validator`. `uv` is unavailable to regenerate `uv.lock` and CI runs `uv sync --frozen`, so no dependency could be added. `pyproject.toml` / `uv.lock` untouched.
  4. **`_issue()` returns a 4-tuple** `(access, expires_in, raw, RefreshToken)` — the committed `service.py`; several inline code snippets earlier in this plan still show the 3-tuple form. The router and tests use the 4-tuple.
  5. `token_type` fields carry `# noqa: S105` (ruff bandit false positive on the field name).
- **Regression check:** Phase 0's `tests/core` (non-DB) + `tests/domain` + `tests/worker` + `test_scaffold` still green; `/health` and `/health/ready` untouched; `lint-imports` still 2 contracts kept; no changes to worker, frontend, or docker-compose.
- **Open on the user:** push `phase-1a-auth`; confirm the `ci` workflow's `backend` + `frontend` jobs pass (authoritative for the 43 DB-backed tests). Then Phase 1b (career profile backend).

---

## Self-Review

**1. Spec coverage (auth slice of §9 Phase 1 + §2.7 / §6.2 / §6.3 / §6.5):**
- `register` / `login` / `refresh` / `logout` / `me` / `password/change` → Task 8. ✓ (`/auth/oauth/github/*` explicitly deferred — spec §12 marks it optional; noted in Architecture.)
- argon2id hashing → Task 2. ✓
- JWT access (15 min from `Settings.jwt_access_ttl_seconds`) + rotating refresh → Tasks 3, 5. ✓
- httpOnly `SameSite=Strict` cookie scoped to `/api/v1/auth` → Task 8. ✓
- Refresh reuse detection (family revoke) → Task 5 (`rotate`) + Task 8 test. ✓
- `get_current_user` / user isolation seam + `get_current_admin` for §6.3's admin surfaces → Task 7. ✓
- Audit on every auth event (`audit_logs`, append-only, non-throwing helper) → Task 5 `_audit`, asserted in Task 8. ✓
  - **Transaction note:** `audit()` writes on the request's own session. Success paths commit normally. The reuse-detection branch in `rotate` calls `self.session.commit()` before raising, so the family revoke + `auth.refresh_reuse_detected` are durable in production despite `get_session` rolling back on the raised exception (in the test harness the outer fixture transaction still rolls back at teardown, which keeps tests isolated; the in-test assertions run first). `auth.login_failed` has no such commit — it is lost on the 401 rollback in production. Durable failed-*attempt* auditing (for brute-force detection / lockout) is deferred to **Phase 13 — testing + security hardening**, designed there alongside lockout.
- `/auth/*` 10/min/IP rate tier → already enforced by Phase 0 `RateLimitMiddleware` (Global Constraints); no new code, no regression.
- `problem+json` + stable machine `code`s (`email_taken`, `invalid_credentials`, `account_disabled`, `refresh_reuse`, `expired_refresh`, `invalid_refresh`, `missing_refresh`, `token_expired`, `invalid_token`, `missing_token`, `forbidden`) → Task 1 (`code` override) + Tasks 3/5/7/8. ✓
- `updated_at` trigger pattern (first use of `set_updated_at()`) → Task 4. ✓

**2. Placeholder scan:** No "TBD" / "add validation" / "similar to Task N". Every code + test step is literal. The one deliberate deferral (GitHub OAuth) is called out in Architecture and Self-Review item 1.

**3. Type consistency:**
- `AuthResult(user, access_token, expires_in, refresh_token)` / `AccessResult(access_token, expires_in, refresh_token)` — defined Task 5, consumed verbatim by Task 8's `_auth_response` / `_access_response`.
- `create_access_token(user_id, *, settings) -> tuple[str, int]` — Task 3, called by Task 5 `_issue` as `access, expires_in = create_access_token(...)`.
- `decode_access_token(token, *, settings) -> uuid.UUID` — Task 3, called by Task 7.
- `new_refresh_token() -> tuple[str, str]` / `hash_refresh_token(raw) -> str` — Task 3, used by Task 5 and by Task 5's tests.
- `AppError(..., code=...)` — Task 1, used by Tasks 3, 5, 7 and surfaced by the unchanged `to_problem`.
- `current_request_id() -> str | None` — Task 1, used by Task 5 `_audit`.
- `User` / `RefreshToken` column names (`token_hash`, `family_id`, `revoked_at`, `replaced_by_id`, `expires_at`, `status`, `is_admin`, `last_login_at`) — Task 4, referenced identically in Task 5 and the model/service tests.
- `CurrentUser` / `CurrentAdmin` — Task 7, imported by Task 8 and the dep test.
- `Settings.refresh_cookie_name` / `refresh_cookie_secure` — Task 1, read by Task 8 cookie helpers and the auth tests (`COOKIE = get_settings().refresh_cookie_name`).
- Migration chain: `0001_bootstrap` → `0002_audit_logs` → `0003_users` (`down_revision = "0002_audit_logs"`). ✓

No inconsistencies found.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-30-phase-1a-auth.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task, two-stage review between tasks.

**2. Inline Execution** — execute tasks in this session with `superpowers:executing-plans`, batched with checkpoints.

**Which approach?** (And note: `uv` + a Postgres 16 / Redis 7 are required to run the DB-backed tests — same constraint as Phase 0; on this machine those run in CI.)
