# Account Data (Export + Deletion) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Data export as a ZIP and irreversible account deletion that leaves nothing behind.

**Architecture:** `app/domain/account/` with `export.py` (collect + serialize + zip) and `deletion.py` (collect refs → checkpoints → audit scrub → cascade delete → files). Router `app/api/v1/account.py`. Profile page gains "Your data" and "Danger zone".

**Tech Stack:** FastAPI, SQLAlchemy async, stdlib `zipfile`/`json`, LangGraph checkpointer, Next.js, TanStack Query, vitest.

**Spec:** `docs/superpowers/specs/2026-09-30-account-data-design.md`

## Global Constraints

- No commits or pushes until the user says so.
- Every query scoped by `user_id`; never export or delete another user's rows.
- Deny-listed fields never exported: `password_hash`, `token_hash`, `embedding`, `search_tsv`, `payload_hash`, `generation_meta`.
- Deletion requires the current password and the literal confirmation `DELETE`.
- Files are deleted only after the DB transaction commits.

---

### Task 1: Export
- `app/domain/account/export.py`: `serialize(row) -> dict` (mapper columns minus deny list; uuid/datetime/Decimal → str), `collect(session, user_id) -> dict`, `build_zip(data, files) -> bytes`, `AccountExporter.export(user) -> (filename, bytes)`.
- Pure tests: serializer drops deny-listed columns and stringifies types; zip contains JSON + PDFs.
- DB tests: export includes profile/résumé text/application letter/own job; excludes other user and secrets.

### Task 2: Deletion
- `app/domain/account/deletion.py`: `AccountDeleter.delete(user, password, *, ip, user_agent) -> list[str]` (file refs to remove after commit); `remove_files(store, refs)`.
- DB tests: rows gone across tables, other user intact, audit scrubbed, checkpoints deleted, wrong password → nothing.

### Task 3: API
- `GET /account/export` (zip, `Content-Disposition`, `Cache-Control: no-store`), `DELETE /account` (schema `password`, `confirm == "DELETE"`), clears refresh cookie; rate-limit: export → upload bucket, delete → auth bucket.
- API tests incl. 401/422 and tenant isolation.

### Task 4: Frontend
- `api.account.export()` (blob) + `api.account.remove(body)`; `AccountDataCard` + `DeleteAccountDialog` on Profile page; tests.

### Task 5: Docs + verification
- Runbook note; backend + frontend gates. No commit.
