# Phase 2b — Résumé Ingestion (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A newly-registered user lands on `/resume`, uploads a PDF, watches a 3-stage stepper driven by Server-Sent Events, reviews and lightly edits the LLM extraction, confirms, and is taken to a populated dashboard.

**Architecture:** One `(app)/resume` route holds a small client-side state machine (`idle → uploading → processing → review | failed`, plus a `list` view for returning users). A new `useResumeEvents` hook is the project's `useSSE` foundation — it streams `GET /resumes/{id}/events` over `fetch` + `ReadableStream` (not `EventSource`, which cannot send `Authorization: Bearer`), reconnecting with backoff and reading a fresh DB status on every reconnect. The extraction-review screen is a `react-hook-form` + `zod` form seeded from `GET /resumes/{id}/extraction`; **Confirm** POSTs the user-corrected `ResumeExtraction` to `/confirm-profile`. One backend task first brings the résumé SSE stream up to spec §6.4 (`done` / `error` events, no custom ping).

**Tech Stack:** Next.js 15 App Router, React 19, TypeScript strict, Tailwind v4, `@tanstack/react-query` v5, `react-hook-form` + `@hookform/resolvers` + `zod`, `lucide-react`, Vitest + Testing Library + jsdom. Backend task: Python 3.12 / FastAPI / `sse-starlette` / `redis.asyncio`. `uv` for the backend task at `C:\Users\chitt\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`; `pnpm` for the frontend (Node ≥ 22.13).

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` — Phase 2 of §9 (frontend half), §3.2 J1 (onboarding journey), §6.4 (SSE event contract), §7.2 (rendering & data strategy), §7.5 (loading/empty/error), §7.6 (a11y). Phase 2a (backend) is complete on `main` (`b4b60b4`).

## Global Constraints

Every task's requirements implicitly include this section.

- **Backend contract (Phase 2a, live on `main`):** `POST /api/v1/resumes` (multipart `file`, `202` → `ResumeOut`) · `GET /api/v1/resumes` (→ `ResumeOut[]`, newest first) · `GET /api/v1/resumes/{id}` · `GET /api/v1/resumes/{id}/events` (SSE) · `GET /api/v1/resumes/{id}/extraction` (→ `ResumeExtraction`; `404` `code:"resume.not_extracted"` until `status === "extracted"`) · `PATCH /api/v1/resumes/{id}` (`{title?, is_primary?}`) · `POST /api/v1/resumes/{id}/reprocess` (`202`) · `DELETE /api/v1/resumes/{id}` (`204`) · `POST /api/v1/resumes/{id}/confirm-profile` (`{extraction: ResumeExtraction}` → `204`). Errors are RFC 9457 `application/problem+json` `{type,title,status,detail,instance,code,errors[]}`.
- **`status` enum:** `uploaded → parsing → parsed → extracting → extracted → failed`. Terminal: `extracted`, `failed`. `failed` always carries a human `parse_error` sentence.
- **SSE (spec §6.4, after Task 1):** `event: status data:{resource,id,status,message}` · `event: done data:{status,totals}` · `event: error data:{code,message}`. Exactly one terminal frame (`done` or `error`) ends every stream.
- **Auth:** access token lives only in `AuthProvider`'s in-memory ref. Authorized calls go through `useAuth().api` (JSON) or the new `useAuth().authedStream` (streaming). Both do one silent `bootstrap()` + retry on a `401`.
- **Data strategy (§7.2):** TanStack Query for reads/mutations/invalidation; `react-hook-form` + `zod` for forms with backend `problem+json` `errors[]` mapped back onto fields via `applyProblemToForm`; no global store; filters/tabs in URL params.
- **Loading / empty / error (§7.5, §3.3):** skeletons for content, labelled spinners (the stepper) for pipeline work, a designed empty state with a next action for every list, `problem+json` → toast + inline + a retry affordance. Never a bare "Loading…".
- **A11y (§7.6):** full keyboard reach; visible `--ring` focus; `aria-live="polite"` on the stepper and streaming text; `role="alert"` on inline errors; WCAG AA token pairs (already in `styles/tokens.css`); respect `prefers-reduced-motion`.
- **YAGNI — explicitly out of scope (their phases):** Résumé Workspace 3-pane, résumé versions / diff / tailoring (Phase 8); skill-taxonomy normalization & date-string parsing of the extraction (Phase 3); the embeddings "index" stepper stage (Phase 6 — the stepper ends at "Ready to review"); multi-résumé "active for matching" beyond `is_primary`.
- **Workflow:** TDD, DRY, YAGNI, commit per green step. Frontend commands from `frontend/`: `pnpm test`, `pnpm lint`, `pnpm exec tsc --noEmit`. Backend commands from `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run mypy app`, `uv run lint-imports`.

---

## File Structure

**Created — frontend**
- `frontend/hooks/useResumeEvents.ts` — the `useSSE` foundation: fetch-stream SSE reader + reconnect. Returns `{status, message, done, error}`.
- `frontend/components/ui/textarea.tsx` — `<Textarea>` primitive (`cva`-styled like `input.tsx`, `Field`-compatible).
- `frontend/components/resume/UploadDropzone.tsx` — PDF picker with drag-drop + client-side type/size validation.
- `frontend/components/resume/ResumeStepper.tsx` — 3-step progress display driven by `status` + `message`.
- `frontend/components/resume/ResumeFailed.tsx` — failure card with "Try again" / "Upload a different file".
- `frontend/components/resume/ReviewSection.tsx` — one collapsible section of the review form (a `useFieldArray` of one `Extracted*` shape).
- `frontend/components/resume/ExtractionReview.tsx` — the full review form: scalars + 4 `<ReviewSection>`s + Confirm.
- `frontend/components/resume/ResumeList.tsx` — returning-user list (status, primary badge, set-primary / re-review / retry / delete).
- `frontend/components/resume/SetupProfileCard.tsx` — dashboard nudge → `/resume`.
- `frontend/lib/resume/extraction-form.ts` — zod schema, `ReviewFormValues` type, `toFormValues` / `toExtraction` converters.
- `frontend/app/(app)/resume/page.tsx` — the route: the flow state machine + the list.
- Tests alongside each unit under `frontend/tests/resume/` and `frontend/tests/ui/`.

**Modified — frontend**
- `frontend/lib/api/types.ts` — add `ResumeStatus`, `ResumeOut`, `ResumeExtraction` (+ nested `Extracted*`).
- `frontend/lib/api/endpoints.ts` — add the `resumes` group to `makeApi`.
- `frontend/providers/AuthProvider.tsx` — add `authedStream(path, init) => Promise<Response>` (bearer + 401→bootstrap→retry, raw `Response`).
- `frontend/test/utils.tsx` — `makeAuthValue` default for `authedStream`.
- `frontend/components/layout/nav-items.ts` — add the `/resume` item (`ready: true`).
- `frontend/components/auth/RegisterForm.tsx` — post-register redirect `/dashboard` → `/resume`.
- `frontend/app/(app)/dashboard/page.tsx` — render `<SetupProfileCard>` when no résumé has `confirmed_at`.

**Modified — backend (Task 1 only)**
- `backend/app/core/events.py` — `status_stream`: emit `done` on terminal, `error` on a bad payload, drop the custom `ping`.
- `backend/app/api/v1/resumes.py` — `resume_events` `_gen`: emit `done` on the already-terminal short-circuit path.
- `backend/tests/core/test_events.py` — cover `done` / `error` / no-ping.

---

## Task 1: Backend — bring the résumé SSE stream to spec §6.4

**Files:**
- Modify: `backend/app/core/events.py`, `backend/app/api/v1/resumes.py:52-84`
- Test: `backend/tests/core/test_events.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `status_stream` now yields, in addition to `{"event":"status",...}` payloads, exactly one of `{"event":"done","status":<terminal>,"totals":{}}` or `{"event":"error","code":"stream.bad_payload","message":<str>}` before returning; it no longer yields `{"event":"ping"}`. `sse_event` is unchanged (`event=payload.get("event","status")` already handles the new shapes).

- [ ] **Step 1: Update the failing tests**

Replace the body of `test_status_stream_opens_relays_and_closes_on_terminal` and add two tests in `backend/tests/core/test_events.py` (keep the `_FakePubSub` / `_FakeRedisForStream` helpers):

```python
async def test_status_stream_emits_done_after_terminal_status():
    ps = _FakePubSub([
        {"data": json.dumps({"event": "status", "status": "parsing"})},
        {"data": json.dumps({"event": "status", "status": "extracted"})},
    ])
    out = [
        ev async for ev in status_stream(
            _FakeRedisForStream(ps), "ch", terminal={"extracted", "failed"}
        )
    ]
    assert out[0] == {"event": "open"}
    assert out[-2]["status"] == "extracted"
    assert out[-1] == {"event": "done", "status": "extracted", "totals": {}}
    assert ps.unsubscribed and ps.closed


async def test_status_stream_emits_error_on_malformed_payload():
    ps = _FakePubSub([{"data": "not-json"}])
    out = [
        ev async for ev in status_stream(
            _FakeRedisForStream(ps), "ch", terminal={"extracted", "failed"}
        )
    ]
    assert out[0] == {"event": "open"}
    assert out[-1]["event"] == "error"
    assert out[-1]["code"] == "stream.bad_payload"
    assert ps.unsubscribed and ps.closed


async def test_status_stream_skips_keepalive_timeouts_without_a_ping_frame():
    ps = _FakePubSub([
        None,  # a get_message() timeout
        {"data": json.dumps({"event": "status", "status": "extracted"})},
    ])
    out = [
        ev async for ev in status_stream(
            _FakeRedisForStream(ps), "ch", terminal={"extracted", "failed"}
        )
    ]
    assert {"event": "ping"} not in out
    assert out[-1] == {"event": "done", "status": "extracted", "totals": {}}
```

- [ ] **Step 2: Run — expect fail**

Run: `cd backend && "$UV" run pytest tests/core/test_events.py -q`
Expected: the three tests above fail (`ping` frame still present; no `done`; `json.loads` raises on `not-json`).

- [ ] **Step 3: Implement**

In `backend/app/core/events.py`, replace the `while True` loop body and keep the `try/finally`:

```python
    async def status_stream(
        redis: Redis,
        channel: str,
        *,
        terminal: set[str],
    ) -> AsyncIterator[dict[str, Any]]:
        pubsub = redis.pubsub()  # no I/O until subscribe()
        try:
            await pubsub.subscribe(channel)
            yield {"event": "open"}  # only fires once the subscription is live
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15.0
                )
                if msg is None:
                    # EventSourceResponse sends its own keepalive comment; nothing
                    # to emit on a plain read timeout.
                    continue
                try:
                    payload: dict[str, Any] = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    yield {
                        "event": "error",
                        "code": "stream.bad_payload",
                        "message": "Received a malformed status update.",
                    }
                    return
                yield payload
                if payload.get("status") in terminal:
                    yield {
                        "event": "done",
                        "status": payload.get("status"),
                        "totals": {},
                    }
                    return
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(channel)
            await pubsub.aclose()  # type: ignore[no-untyped-call]
```

In `backend/app/api/v1/resumes.py`, the `resume_events` `_gen` already-terminal branch — add a `done` frame before the early return:

```python
            if payload.get("event") == "open":
                try:
                    async with AsyncSessionLocal() as s:
                        current = (await ResumeService(s).get(user.id, resume_id)).status
                except NotFoundError:
                    return  # deleted mid-stream — close cleanly
                yield sse_event(
                    {
                        "event": "status",
                        "resource": "resume",
                        "id": str(resume_id),
                        "status": current,
                    }
                )
                if current in {"extracted", "failed"}:
                    yield sse_event({"event": "done", "status": current, "totals": {}})
                    return
                continue
            yield sse_event(payload)
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && "$UV" run pytest tests/core/test_events.py -q && "$UV" run ruff check . && "$UV" run mypy app && "$UV" run lint-imports`
Expected: all green (2 import contracts kept). The route-level `_gen` change is exercised in CI's `tests/api/test_resumes.py` (DB+Redis) — verify locally with `"$UV" run pytest --collect-only -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/events.py backend/app/api/v1/resumes.py backend/tests/core/test_events.py
git commit -m "feat(events): résumé SSE stream emits spec §6.4 done/error, drops custom ping"
```

---

## Task 2: Frontend — résumé types + API endpoints

**Files:**
- Modify: `frontend/lib/api/types.ts`, `frontend/lib/api/endpoints.ts`
- Test: `frontend/tests/api/endpoints.test.ts`

**Interfaces:**
- Consumes: `Fetcher` from `@/lib/api/fetcher`, the `json(method, body)` helper in `endpoints.ts`.
- Produces:
  - `ResumeStatus = "uploaded" | "parsing" | "parsed" | "extracting" | "extracted" | "failed"`.
  - `ResumeOut` — `{ id, title: string|null, original_filename: string|null, content_type: string, size_bytes: number, page_count: number|null, status: ResumeStatus, parse_error: string|null, is_primary: boolean, confirmed_at: string|null, created_at: string, updated_at: string }`.
  - `ExtractedExperience`, `ExtractedEducation`, `ExtractedProject`, `ExtractedCertification`, `ResumeExtraction` — exact shapes below.
  - `makeApi(f).resumes` — `{ list, get, upload, extraction, patch, reprocess, remove, confirmProfile }` with the signatures below.

- [ ] **Step 1: Write the failing test**

Append to `frontend/tests/api/endpoints.test.ts` (it already builds `makeApi(fakeFetch)` and asserts path + method):

```ts
describe("resumes", () => {
  it("upload posts multipart to /resumes with no JSON content-type", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi(async (path, init) => {
      calls.push({ path, init });
      return {} as unknown;
    });
    const file = new File(["%PDF-1.7"], "cv.pdf", { type: "application/pdf" });
    await api.resumes.upload(file);
    expect(calls[0].path).toBe("/api/v1/resumes");
    expect(calls[0].init?.method).toBe("POST");
    expect(calls[0].init?.body).toBeInstanceOf(FormData);
    expect((calls[0].init?.headers as Record<string, string>)?.["Content-Type"]).toBeUndefined();
  });

  it("confirmProfile posts { extraction } to /confirm-profile", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi(async (path, init) => {
      calls.push({ path, init });
      return undefined as unknown;
    });
    await api.resumes.confirmProfile("r1", { full_name: "Jane" });
    expect(calls[0].path).toBe("/api/v1/resumes/r1/confirm-profile");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      extraction: { full_name: "Jane" },
    });
  });

  it("extraction GETs /resumes/{id}/extraction", async () => {
    const calls: string[] = [];
    const api = makeApi(async (path) => {
      calls.push(path);
      return {} as unknown;
    });
    await api.resumes.extraction("r1");
    expect(calls[0]).toBe("/api/v1/resumes/r1/extraction");
  });
});
```

- [ ] **Step 2: Run — expect fail**

Run: `cd frontend && pnpm test -- endpoints`
Expected: FAIL — `api.resumes` is `undefined`.

- [ ] **Step 3: Implement**

Add to `frontend/lib/api/types.ts`:

```ts
export type ResumeStatus =
  | "uploaded"
  | "parsing"
  | "parsed"
  | "extracting"
  | "extracted"
  | "failed";

export interface ResumeOut {
  id: string;
  title: string | null;
  original_filename: string | null;
  content_type: string;
  size_bytes: number;
  page_count: number | null;
  status: ResumeStatus;
  parse_error: string | null;
  is_primary: boolean;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExtractedExperience {
  company: string;
  title: string;
  employment_type?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  location?: string | null;
  description?: string | null;
  highlights?: string[];
  tech?: string[];
}

export interface ExtractedEducation {
  institution: string;
  degree?: string | null;
  field?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  grade?: string | null;
}

export interface ExtractedProject {
  name: string;
  description?: string | null;
  url?: string | null;
  highlights?: string[];
  tech?: string[];
  start_date?: string | null;
  end_date?: string | null;
}

export interface ExtractedCertification {
  name: string;
  issuer?: string | null;
  issued_date?: string | null;
  expires_date?: string | null;
  credential_id?: string | null;
  url?: string | null;
}

export interface ResumeExtraction {
  full_name?: string | null;
  email?: string | null;
  location?: string | null;
  github_url?: string | null;
  linkedin_url?: string | null;
  portfolio_url?: string | null;
  summary?: string | null;
  skills?: string[];
  experiences?: ExtractedExperience[];
  education?: ExtractedEducation[];
  projects?: ExtractedProject[];
  certifications?: ExtractedCertification[];
}
```

Add the `resumes` group inside the object returned by `makeApi` in `frontend/lib/api/endpoints.ts` (import `ResumeExtraction`, `ResumeOut` from `@/lib/api/types`):

```ts
    resumes: {
      async list() {
        return f<ResumeOut[]>("/api/v1/resumes");
      },
      async get(id: string) {
        return f<ResumeOut>(`/api/v1/resumes/${id}`);
      },
      async upload(file: File) {
        const form = new FormData();
        form.append("file", file);
        return f<ResumeOut>("/api/v1/resumes", { method: "POST", body: form });
      },
      async extraction(id: string) {
        return f<ResumeExtraction>(`/api/v1/resumes/${id}/extraction`);
      },
      async patch(id: string, body: { title?: string; is_primary?: boolean }) {
        return f<ResumeOut>(`/api/v1/resumes/${id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
          headers: { "Content-Type": "application/json" },
        });
      },
      async reprocess(id: string) {
        return f<ResumeOut>(`/api/v1/resumes/${id}/reprocess`, { method: "POST" });
      },
      async remove(id: string) {
        return f<void>(`/api/v1/resumes/${id}`, { method: "DELETE" });
      },
      async confirmProfile(id: string, extraction: ResumeExtraction) {
        return f<void>(
          `/api/v1/resumes/${id}/confirm-profile`,
          json("POST", { extraction }),
        );
      },
    },
```

- [ ] **Step 4: Run — expect pass**

Run: `cd frontend && pnpm test -- endpoints && pnpm exec tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(api): résumé types + /resumes endpoint group"
```

---

## Task 3: Frontend — `authedStream` on AuthProvider

**Files:**
- Modify: `frontend/providers/AuthProvider.tsx`, `frontend/test/utils.tsx`
- Test: `frontend/tests/auth-provider.test.tsx`

**Interfaces:**
- Consumes: `API_BASE_URL` from `@/lib/env`, the existing `bootstrap()` and `tokenRef`.
- Produces: `AuthContextValue.authedStream: (path: string, init?: RequestInit) => Promise<Response>` — prepends `API_BASE_URL`, sends `credentials: "include"` + `Authorization: Bearer <token>`, and on a `401` does one `bootstrap()` + retry (going `anon` if the retry is still `401`). Returns the raw `Response` (never reads the body). `makeAuthValue` in `test/utils.tsx` gains a default `authedStream: vi.fn(async () => new Response(null, { status: 500 }))`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/auth-provider.test.tsx` (it already renders `<AuthProvider>` with a mocked global `fetch` and reads the context via a probe component):

```tsx
it("authedStream attaches the bearer token and retries once on 401", async () => {
  const fetchMock = vi.fn();
  // bootstrap on mount: refresh + me
  fetchMock
    .mockResolvedValueOnce(jsonRes({ access_token: "t1", token_type: "bearer", expires_in: 900 }))
    .mockResolvedValueOnce(jsonRes({ id: "u1", email: "a@b.co", full_name: "A", is_admin: false, created_at: "" }))
    // first stream call: 401
    .mockResolvedValueOnce(new Response(null, { status: 401 }))
    // re-bootstrap: refresh + me
    .mockResolvedValueOnce(jsonRes({ access_token: "t2", token_type: "bearer", expires_in: 900 }))
    .mockResolvedValueOnce(jsonRes({ id: "u1", email: "a@b.co", full_name: "A", is_admin: false, created_at: "" }))
    // retry: 200 stream
    .mockResolvedValueOnce(new Response("data: {}\n\n", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  const seen: { url: string; auth: string | null }[] = [];
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    seen.push({ url, auth: new Headers(init?.headers).get("Authorization") });
    return Promise.resolve(new Response(null, { status: 500 }));
  });
  // (re-arm the ordered mock above via mockResolvedValueOnce before mockImplementation
  //  in the real test — this comment marks the ordering the implementer must wire.)

  // Render provider, wait for status "authed", then call authedStream and assert:
  //  - the failing call carried Authorization: Bearer t1
  //  - after retry, a call carried Authorization: Bearer t2
  //  - the returned value is a Response (not parsed)
});
```

> The implementer should shape this against the file's existing helpers (`jsonRes`, the probe component pattern). The assertions that matter: (a) `authedStream` returns a `Response`; (b) the pre-refresh attempt carried `Bearer <first token>`; (c) the post-refresh retry carried `Bearer <second token>`.

- [ ] **Step 2: Run — expect fail** (`authedStream` is not on the context).

- [ ] **Step 3: Implement**

In `frontend/providers/AuthProvider.tsx`: add `import { API_BASE_URL } from "@/lib/env";`, extend `AuthContextValue`, add the callback, thread it through the `value` memo:

```tsx
  const authedStream = useCallback(
    async (path: string, init?: RequestInit): Promise<Response> => {
      const go = () =>
        fetch(`${API_BASE_URL}${path}`, {
          ...init,
          credentials: "include",
          headers: {
            ...(init?.headers ?? {}),
            Authorization: `Bearer ${tokenRef.current}`,
          },
        });
      const res = await go();
      if (res.status !== 401) return res;
      try {
        await bootstrap();
      } catch (err) {
        setStatus("anon");
        throw err;
      }
      const retry = await go();
      if (retry.status === 401) setStatus("anon");
      return retry;
    },
    [bootstrap],
  );
```

Add `authedStream: (path: string, init?: RequestInit) => Promise<Response>;` to the `AuthContextValue` interface, and `authedStream` to the `useMemo<AuthContextValue>` dependency list + object.

In `frontend/test/utils.tsx`, add to the `defaults` object inside `makeAuthValue`:

```ts
    authedStream: vi.fn(async () => new Response(null, { status: 500 })),
```

- [ ] **Step 4: Run — expect pass**

Run: `cd frontend && pnpm test -- auth-provider && pnpm exec tsc --noEmit && pnpm test`
Expected: the new test passes and the **full suite stays green** (every prior test that renders through `renderWithProviders` now gets a default `authedStream`).

- [ ] **Step 5: Commit**

```bash
git add frontend/providers/AuthProvider.tsx frontend/test/utils.tsx frontend/tests/auth-provider.test.tsx
git commit -m "feat(auth): authedStream — authorized fetch that returns a raw Response for SSE"
```

---

## Task 4: Frontend — `useResumeEvents` hook

**Files:**
- Create: `frontend/hooks/useResumeEvents.ts`
- Test: `frontend/tests/resume/use-resume-events.test.ts`

**Interfaces:**
- Consumes: `useAuth().authedStream` (Task 3); `ResumeStatus` from `@/lib/api/types`.
- Produces: `useResumeEvents(resumeId: string | null, opts?: { enabled?: boolean }) => { status: ResumeStatus | null; message: string | null; done: boolean; error: string | null }`. It opens `authedStream("/api/v1/resumes/{id}/events")`, parses SSE frames from `response.body`, maps `event: status` → `{status, message}`, `event: done` → `{done:true, status}`, `event: error` → `{error, done:true}`; on an unexpected disconnect before `done` it reconnects with exponential backoff (max 5 tries, 1s→16s), giving up with `error` set. Disabled or `resumeId === null` → inert (`{status:null,message:null,done:false,error:null}`). Cleans up (aborts the fetch) on unmount / id change.

- [ ] **Step 1: Write the failing test**

`frontend/tests/resume/use-resume-events.test.ts`:

```ts
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useResumeEvents } from "@/hooks/useResumeEvents";
import { AuthContext, makeAuthValue } from "@/test/utils";
import type { ReactNode } from "react";

function streamOf(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      for (const f of frames) controller.enqueue(enc.encode(f));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

function wrap(authedStream: () => Promise<Response>) {
  const value = makeAuthValue({ authValue: { authedStream } });
  return ({ children }: { children: ReactNode }) => (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

describe("useResumeEvents", () => {
  it("advances status from stream frames and marks done", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: open\ndata: {"event":"open"}\n\n`,
        `event: status\ndata: {"status":"parsing","message":"Reading your résumé…"}\n\n`,
        `event: status\ndata: {"status":"extracting","message":"Understanding the details…"}\n\n`,
        `event: status\ndata: {"status":"extracted","message":"Ready to review"}\n\n`,
        `event: done\ndata: {"status":"extracted","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useResumeEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true));
    expect(result.current.status).toBe("extracted");
    expect(result.current.error).toBeNull();
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"code":"stream.bad_payload","message":"bad"}\n\n`]),
    );
    const { result } = renderHook(() => useResumeEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true));
    expect(result.current.error).toBe("bad");
  });

  it("is inert when resumeId is null", () => {
    const authedStream = vi.fn();
    const { result } = renderHook(() => useResumeEvents(null), { wrapper: wrap(authedStream) });
    expect(authedStream).not.toHaveBeenCalled();
    expect(result.current).toEqual({ status: null, message: null, done: false, error: null });
  });

  it("reconnects after an early disconnect and resumes", async () => {
    const authedStream = vi
      .fn()
      .mockResolvedValueOnce(streamOf([`event: status\ndata: {"status":"parsing"}\n\n`])) // ends with no `done`
      .mockResolvedValueOnce(
        streamOf([`event: status\ndata: {"status":"extracted"}\n\n`, `event: done\ndata: {"status":"extracted"}\n\n`]),
      );
    const { result } = renderHook(() => useResumeEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true), { timeout: 3000 });
    expect(authedStream).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("extracted");
  });
});
```

- [ ] **Step 2: Run — expect fail** (`@/hooks/useResumeEvents` does not exist).

- [ ] **Step 3: Implement**

`frontend/hooks/useResumeEvents.ts`:

```ts
"use client";

import { useEffect, useState } from "react";

import type { ResumeStatus } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export interface ResumeEventState {
  status: ResumeStatus | null;
  message: string | null;
  done: boolean;
  error: string | null;
}

const INITIAL: ResumeEventState = { status: null, message: null, done: false, error: null };
const MAX_ATTEMPTS = 5;

interface Frame {
  event: string;
  data: Record<string, unknown>;
}

function parseFrame(raw: string): Frame | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue; // keepalive comment
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (data.length === 0) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
  } catch {
    return null;
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useResumeEvents(
  resumeId: string | null,
  opts: { enabled?: boolean } = {},
): ResumeEventState {
  const { authedStream } = useAuth();
  const enabled = (opts.enabled ?? true) && resumeId !== null;
  const [state, setState] = useState<ResumeEventState>(INITIAL);

  useEffect(() => {
    if (!enabled || !resumeId) {
      setState(INITIAL);
      return;
    }
    setState(INITIAL);
    let cancelled = false;
    const ctrl = new AbortController();

    const consume = async (): Promise<"done" | "closed"> => {
      const res = await authedStream(`/api/v1/resumes/${resumeId}/events`, {
        signal: ctrl.signal,
        headers: { Accept: "text/event-stream" },
      });
      if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return "closed";
        buf += decoder.decode(value, { stream: true });
        let i: number;
        while ((i = buf.indexOf("\n\n")) !== -1) {
          const frame = parseFrame(buf.slice(0, i));
          buf = buf.slice(i + 2);
          if (!frame || cancelled) continue;
          if (frame.event === "status") {
            setState((s) => ({
              ...s,
              status: (frame.data.status as ResumeStatus) ?? s.status,
              message: (frame.data.message as string) ?? s.message,
            }));
          } else if (frame.event === "done") {
            setState((s) => ({ ...s, done: true, status: (frame.data.status as ResumeStatus) ?? s.status }));
            return "done";
          } else if (frame.event === "error") {
            setState((s) => ({ ...s, done: true, error: (frame.data.message as string) ?? "Stream error" }));
            return "done";
          }
        }
      }
    };

    const run = async () => {
      for (let attempt = 0; attempt <= MAX_ATTEMPTS && !cancelled; attempt++) {
        try {
          const result = await consume();
          if (result === "done" || cancelled) return;
          // "closed" with no `done`: reconnect (the backend re-reads status on `open`).
        } catch {
          if (cancelled || ctrl.signal.aborted) return;
        }
        if (attempt === MAX_ATTEMPTS) {
          setState((s) => ({ ...s, done: true, error: "Lost the connection to status updates." }));
          return;
        }
        await sleep(Math.min(1000 * 2 ** attempt, 16000));
      }
    };

    void run();
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [enabled, resumeId, authedStream]);

  return state;
}
```

> **Test-timing note:** the reconnect test relies on the first backoff being ~1000ms. If that makes the suite slow, the implementer may read the base delay from an optional 3rd arg defaulted to `1000` and pass a small value in the test — keep the production default at 1000.

- [ ] **Step 4: Run — expect pass**

Run: `cd frontend && pnpm test -- use-resume-events && pnpm exec tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add frontend/hooks/useResumeEvents.ts frontend/tests/resume/use-resume-events.test.ts
git commit -m "feat(resume): useResumeEvents — SSE-over-fetch status hook with reconnect"
```

---

## Task 5: Frontend — `<Textarea>` primitive

**Files:**
- Create: `frontend/components/ui/textarea.tsx`
- Test: `frontend/tests/ui/textarea.test.tsx`

**Interfaces:**
- Consumes: `cn` from `@/lib/cn`.
- Produces: `Textarea` — `forwardRef<HTMLTextAreaElement, ComponentProps<"textarea">>`, token-styled to match `Input`, forwards `className` and all native props (incl. `aria-describedby`, `aria-invalid`), `displayName = "Textarea"`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/ui/textarea.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import { Textarea } from "@/components/ui/textarea";

describe("Textarea", () => {
  it("forwards ref and native props", () => {
    const ref = createRef<HTMLTextAreaElement>();
    render(<Textarea ref={ref} aria-invalid placeholder="Summary" defaultValue="hi" />);
    const el = screen.getByPlaceholderText("Summary");
    expect(ref.current).toBe(el);
    expect(el).toHaveAttribute("aria-invalid", "true");
    expect(el).toHaveValue("hi");
  });

  it("merges className", () => {
    render(<Textarea className="custom-x" data-testid="t" />);
    expect(screen.getByTestId("t").className).toContain("custom-x");
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement**

`frontend/components/ui/textarea.tsx`:

```tsx
import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Textarea = forwardRef<HTMLTextAreaElement, ComponentProps<"textarea">>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "min-h-20 w-full rounded-[var(--radius)] border border-border bg-surface px-3 py-2 text-sm text-text outline-none placeholder:text-text-subtle focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
        "aria-[invalid=true]:border-danger aria-[invalid=true]:ring-[color-mix(in_srgb,var(--danger)_45%,transparent)]",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
```

- [ ] **Step 4: Run — expect pass** (`pnpm test -- textarea && pnpm exec tsc --noEmit`).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ui/textarea.tsx frontend/tests/ui/textarea.test.tsx
git commit -m "feat(ui): Textarea primitive"
```

---

## Task 6: Frontend — `<UploadDropzone>`

**Files:**
- Create: `frontend/components/resume/UploadDropzone.tsx`
- Test: `frontend/tests/resume/upload-dropzone.test.tsx`

**Interfaces:**
- Consumes: `Card` from `@/components/ui/card`, `cn`.
- Produces: `UploadDropzone({ onFile, disabled }: { onFile: (file: File) => void; disabled?: boolean })`. A keyboard-operable `role="button"` card wrapping a visually-hidden `<input type="file" accept="application/pdf" data-testid="resume-file-input">`. Client validation before `onFile`: rejects non-`application/pdf` and files `> 10 * 1024 * 1024` bytes with a `role="alert"` message; a valid pick calls `onFile(file)`. Drag-over sets an accent style. When `disabled`, the card is inert (`aria-disabled`, `tabIndex=-1`).

- [ ] **Step 1: Write the failing test**

`frontend/tests/resume/upload-dropzone.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UploadDropzone } from "@/components/resume/UploadDropzone";

const pdf = (name = "cv.pdf", bytes = 100) =>
  new File([new Uint8Array(bytes)], name, { type: "application/pdf" });

describe("UploadDropzone", () => {
  it("calls onFile for a valid PDF", async () => {
    const onFile = vi.fn();
    render(<UploadDropzone onFile={onFile} />);
    await userEvent.upload(screen.getByTestId("resume-file-input"), pdf());
    expect(onFile).toHaveBeenCalledTimes(1);
    expect(onFile.mock.calls[0][0].name).toBe("cv.pdf");
  });

  it("rejects a non-PDF with an inline alert and does not call onFile", async () => {
    const onFile = vi.fn();
    render(<UploadDropzone onFile={onFile} />);
    const txt = new File(["hi"], "notes.txt", { type: "text/plain" });
    await userEvent.upload(screen.getByTestId("resume-file-input"), txt);
    expect(onFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/pdf/i);
  });

  it("rejects a file over 10 MB", async () => {
    const onFile = vi.fn();
    render(<UploadDropzone onFile={onFile} />);
    await userEvent.upload(
      screen.getByTestId("resume-file-input"),
      pdf("big.pdf", 10 * 1024 * 1024 + 1),
    );
    expect(onFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/10 MB/i);
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** — build the component to the Produces contract. Key points: `MAX_BYTES = 10 * 1024 * 1024`; validation helper shared by the `onChange` and `onDrop` paths; `onDragOver`/`onDrop` call `e.preventDefault()`; `onClick` / `Enter` / `Space` trigger `inputRef.current?.click()`; the hidden input is `className="sr-only"`.

- [ ] **Step 4: Run — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add frontend/components/resume/UploadDropzone.tsx frontend/tests/resume/upload-dropzone.test.tsx
git commit -m "feat(resume): UploadDropzone with client-side PDF/size checks"
```

---

## Task 7: Frontend — `<ResumeStepper>` + `<ResumeFailed>`

**Files:**
- Create: `frontend/components/resume/ResumeStepper.tsx`, `frontend/components/resume/ResumeFailed.tsx`
- Test: `frontend/tests/resume/resume-stepper.test.tsx`, `frontend/tests/resume/resume-failed.test.tsx`

**Interfaces:**
- Consumes: `lucide-react` (`Check`, `Loader2`), `cn`, `Button`, `Card`, `ResumeStatus`.
- Produces:
  - `ResumeStepper({ status, message }: { status: ResumeStatus | null; message: string | null })` — an `aria-live="polite"` ordered list of 3 steps: **"Reading your résumé"** (`uploaded`/`parsing`), **"Understanding the details"** (`parsed`/`extracting`), **"Ready to review"** (`extracted`). Completed steps show a check; the active step shows a spinner and, if present, `message` in place of the label; `status === "extracted"` marks all 3 complete.
  - `ResumeFailed({ message, onRetry, onReupload, retrying }: { message: string | null; onRetry: () => void; onReupload: () => void; retrying?: boolean })` — a card with the `message` (fallback copy if null) and two buttons: **"Try again"** (`onRetry`, disabled + "Retrying…" while `retrying`) and **"Upload a different file"** (`onReupload`, secondary).

- [ ] **Step 1: Write the failing tests**

`frontend/tests/resume/resume-stepper.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResumeStepper } from "@/components/resume/ResumeStepper";

describe("ResumeStepper", () => {
  it("marks step 1 active while parsing and shows the message", () => {
    render(<ResumeStepper status="parsing" message="Reading your résumé…" />);
    expect(screen.getByText("Reading your résumé…")).toBeInTheDocument();
    expect(screen.getByText("Understanding the details")).toBeInTheDocument();
  });

  it("marks all steps complete at extracted", () => {
    const { container } = render(<ResumeStepper status="extracted" message={null} />);
    // 3 check icons — implementer: give each check a data-testid="step-done" or assert via role
    expect(container.querySelectorAll('[data-testid="step-done"]')).toHaveLength(3);
  });
});
```

`frontend/tests/resume/resume-failed.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ResumeFailed } from "@/components/resume/ResumeFailed";

describe("ResumeFailed", () => {
  it("shows the message and wires both actions", async () => {
    const onRetry = vi.fn();
    const onReupload = vi.fn();
    render(
      <ResumeFailed
        message="This looks like a scanned PDF — text extraction isn't available yet."
        onRetry={onRetry}
        onReupload={onReupload}
      />,
    );
    expect(screen.getByText(/scanned PDF/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await userEvent.click(screen.getByRole("button", { name: /different file/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onReupload).toHaveBeenCalledTimes(1);
  });

  it("disables Try again while retrying", () => {
    render(<ResumeFailed message={null} onRetry={vi.fn()} onReupload={vi.fn()} retrying />);
    expect(screen.getByRole("button", { name: /retrying/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** both components. `ResumeStepper`: a `STEPS` array mapping labels to status sets, a `stageIndex(status)` helper (returns `-1` for `failed`), each `<li>` renders a check (`data-testid="step-done"`) / spinner / number badge and the label-or-message. `ResumeFailed`: verify the secondary `Button` variant name against `components/ui/button.tsx` (`secondary` or `ghost`).

- [ ] **Step 4: Run — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add frontend/components/resume/ResumeStepper.tsx frontend/components/resume/ResumeFailed.tsx frontend/tests/resume/resume-stepper.test.tsx frontend/tests/resume/resume-failed.test.tsx
git commit -m "feat(resume): ResumeStepper + ResumeFailed presentational components"
```

---

## Task 8: Frontend — extraction review form (`extraction-form.ts`, `<ReviewSection>`, `<ExtractionReview>`)

**Files:**
- Create: `frontend/lib/resume/extraction-form.ts`, `frontend/components/resume/ReviewSection.tsx`, `frontend/components/resume/ExtractionReview.tsx`
- Test: `frontend/tests/resume/extraction-review.test.tsx`, `frontend/tests/resume/extraction-form.test.ts`

**Interfaces:**
- Consumes: `react-hook-form` (`useForm`, `useFieldArray`, `Controller`), `zodResolver` from `@hookform/resolvers/zod`, `zod`, `Field`, `Input`, `Textarea`, `Button`, `Card`, `csvToList` / `listToCsv` from `@/lib/forms`, `applyProblemToForm` from `@/lib/api/form-errors`, `ResumeExtraction` + nested types.
- Produces:
  - `extraction-form.ts`: `reviewSchema` (zod, every field optional; strings trimmed; arrays default `[]`), `type ReviewFormValues` (highlights/tech modelled as comma-joined `string`), `toFormValues(e: ResumeExtraction): ReviewFormValues`, `toExtraction(v: ReviewFormValues): ResumeExtraction` (splits the csv fields back to `string[]`, drops empty scalars to `undefined`).
  - `ReviewSection<T>({ title, fields, control, register, name })` — a titled `<Card>` listing the `useFieldArray` rows for `name`; each row renders a `<Field>`+`<Input>` per entry in `fields` and a **Remove** button (`remove(index)`); no "add row" (that lives in `/profile`).
  - `ExtractionReview({ extraction, onConfirm, confirming }: { extraction: ResumeExtraction; onConfirm: (e: ResumeExtraction) => Promise<void>; confirming?: boolean })` — a form seeded via `toFormValues`; scalar `<Field>`s for `full_name`, `email`, `location`, `github_url`, `linkedin_url`, `portfolio_url`, `summary` (Textarea), a `skills` csv `<Field>`, and four `<ReviewSection>`s (experiences: `company,title,employment_type,location,start_date,end_date,description`; education: `institution,degree,field,start_date,end_date,grade`; projects: `name,url,description,start_date,end_date`; certifications: `name,issuer,credential_id,url`). Submit → `onConfirm(toExtraction(values))`; a thrown `ProblemError` is fed to `applyProblemToForm` and a `root` error is shown; the submit button reads **"Confirm & build my profile"** (→ "Building…" while `confirming`).

- [ ] **Step 1: Write the failing tests**

`frontend/tests/resume/extraction-form.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { toExtraction, toFormValues } from "@/lib/resume/extraction-form";

describe("extraction-form converters", () => {
  it("round-trips scalars and csv arrays", () => {
    const e = {
      full_name: "Jane Doe",
      skills: ["Python", "PyTorch"],
      experiences: [{ company: "Acme", title: "ML Eng", highlights: ["shipped x"], tech: ["py"] }],
    };
    const v = toFormValues(e);
    expect(v.skills).toBe("Python, PyTorch");
    expect(v.experiences[0].tech).toBe("py");
    const back = toExtraction(v);
    expect(back.skills).toEqual(["Python", "PyTorch"]);
    expect(back.experiences?.[0]).toMatchObject({ company: "Acme", title: "ML Eng", tech: ["py"] });
  });

  it("drops empty scalars to undefined", () => {
    const back = toExtraction(toFormValues({ full_name: "", location: "Berlin" }));
    expect(back.full_name).toBeUndefined();
    expect(back.location).toBe("Berlin");
  });
});
```

`frontend/tests/resume/extraction-review.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExtractionReview } from "@/components/resume/ExtractionReview";

const extraction = {
  full_name: "Jane Doe",
  email: "jane@example.com",
  summary: "ML engineer.",
  skills: ["Python", "PyTorch"],
  experiences: [
    { company: "Acme", title: "ML Eng" },
    { company: "Globex", title: "Intern" },
  ],
  education: [],
  projects: [],
  certifications: [],
};

describe("ExtractionReview", () => {
  it("seeds fields from the extraction and confirms the edited payload", async () => {
    const onConfirm = vi.fn(async () => {});
    render(<ExtractionReview extraction={extraction} onConfirm={onConfirm} />);

    expect(screen.getByLabelText(/full name/i)).toHaveValue("Jane Doe");
    expect(screen.getByLabelText(/summary/i)).toHaveValue("ML engineer.");

    // edit location
    await userEvent.type(screen.getByLabelText(/location/i), "Berlin");
    // drop the second experience row
    const rows = screen.getAllByTestId?.("experience-row") ?? screen.getAllByRole("group");
    await userEvent.click(within(rows[1]).getByRole("button", { name: /remove/i }));

    await userEvent.click(screen.getByRole("button", { name: /confirm & build/i }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const payload = onConfirm.mock.calls[0][0];
    expect(payload.location).toBe("Berlin");
    expect(payload.experiences).toHaveLength(1);
    expect(payload.experiences[0].company).toBe("Acme");
    expect(payload.skills).toEqual(["Python", "PyTorch"]);
  });
});
```

> The implementer aligns the row selector with what they render (recommended: `data-testid="experience-row"` on each `<ReviewSection>` row, or a `<fieldset>` with an accessible name).

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** the schema, converters, `ReviewSection`, and `ExtractionReview` to the Produces contract. Use `Controller` for the Textarea; wire `aria-invalid` from `fieldState.error` and pass `error={...}` to `<Field>`. Highlights/tech are edited as csv per row via `listToCsv` / `csvToList`.

- [ ] **Step 4: Run — expect pass** (`pnpm test -- extraction && pnpm exec tsc --noEmit`).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/resume/extraction-form.ts frontend/components/resume/ReviewSection.tsx frontend/components/resume/ExtractionReview.tsx frontend/tests/resume/extraction-review.test.tsx frontend/tests/resume/extraction-form.test.ts
git commit -m "feat(resume): extraction review form — seed, light edits, confirm payload"
```

---

## Task 9: Frontend — `<ResumeList>`

**Files:**
- Create: `frontend/components/resume/ResumeList.tsx`
- Test: `frontend/tests/resume/resume-list.test.tsx`

**Interfaces:**
- Consumes: `ResumeOut`, `Card`, `Button`, `lucide-react`, `cn`.
- Produces: `ResumeList({ resumes, onSetPrimary, onReview, onRetry, onDelete, onUploadAnother, busyId }: { resumes: ResumeOut[]; onSetPrimary: (id: string) => void; onReview: (id: string) => void; onRetry: (id: string) => void; onDelete: (id: string) => void; onUploadAnother: () => void; busyId: string | null })` — one row per résumé: `title ?? original_filename ?? "Résumé"`, a status label, a **Primary** badge when `is_primary`, the uploaded date. Per-row actions by status: `extracted && !confirmed_at` → **Review** (`onReview`); `failed` → **Try again** (`onRetry`); any → **Make primary** (unless already primary) and **Delete** (`onDelete`, guarded by a `window.confirm`). An **"Upload another résumé"** button under the list. The row whose id equals `busyId` shows its buttons disabled.

- [ ] **Step 1: Write the failing test**

`frontend/tests/resume/resume-list.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ResumeList } from "@/components/resume/ResumeList";
import type { ResumeOut } from "@/lib/api/types";

const base: ResumeOut = {
  id: "r1", title: "Senior CV", original_filename: "cv.pdf", content_type: "application/pdf",
  size_bytes: 1000, page_count: 2, status: "extracted", parse_error: null, is_primary: true,
  confirmed_at: "2026-09-01T00:00:00Z", created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z",
};

describe("ResumeList", () => {
  it("shows Review for an extracted-but-unconfirmed résumé and Try again for a failed one", async () => {
    const onReview = vi.fn();
    const onRetry = vi.fn();
    const rows: ResumeOut[] = [
      { ...base, id: "r2", title: "Draft", is_primary: false, confirmed_at: null },
      { ...base, id: "r3", title: "Broken", is_primary: false, status: "failed", parse_error: "scanned", confirmed_at: null },
    ];
    render(
      <ResumeList
        resumes={rows}
        onSetPrimary={vi.fn()} onReview={onReview} onRetry={onRetry}
        onDelete={vi.fn()} onUploadAnother={vi.fn()} busyId={null}
      />,
    );
    await userEvent.click(within(screen.getByText("Draft").closest("li")!).getByRole("button", { name: /review/i }));
    await userEvent.click(within(screen.getByText("Broken").closest("li")!).getByRole("button", { name: /try again/i }));
    expect(onReview).toHaveBeenCalledWith("r2");
    expect(onRetry).toHaveBeenCalledWith("r3");
  });

  it("confirms before delete", async () => {
    const onDelete = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <ResumeList
        resumes={[base]} onSetPrimary={vi.fn()} onReview={vi.fn()} onRetry={vi.fn()}
        onDelete={onDelete} onUploadAnother={vi.fn()} busyId={null}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    expect(onDelete).toHaveBeenCalledWith("r1");
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** to the Produces contract.

- [ ] **Step 4: Run — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add frontend/components/resume/ResumeList.tsx frontend/tests/resume/resume-list.test.tsx
git commit -m "feat(resume): ResumeList for returning users"
```

---

## Task 10: Frontend — `/resume` route (the flow state machine)

**Files:**
- Create: `frontend/app/(app)/resume/page.tsx`
- Test: `frontend/tests/resume/resume-page.test.tsx`

**Interfaces:**
- Consumes: `useAuth`, `useQuery` / `useMutation` / `useQueryClient` from `@tanstack/react-query`, `useResumeEvents`, `useRouter` from `next/navigation`, `useToast`, and every `components/resume/*` from Tasks 6–9, plus `Skeleton`, `RequireAuth`.
- Produces: the default-exported `ResumePage` client component. Behaviour:
  - Wrapped in `<RequireAuth>`. Queries `["resumes"]` via `api.resumes.list()`.
  - **Active résumé** = the newest résumé that is `!confirmed_at` and `status !== "failed"` **or** the one the user just uploaded/selected (tracked in local `activeId` state).
  - No résumés at all, or `activeId` set and its status is non-terminal-non-review → render the **flow**:
    - `idle` (no `activeId`): `<UploadDropzone onFile={upload} />`.
    - `upload` mutation pending: a labelled spinner ("Uploading…").
    - `activeId` set, status ∈ `{uploaded,parsing,parsed,extracting}`: `<ResumeStepper status message />` fed by `useResumeEvents(activeId)`. On the hook reaching `done` with `status === "extracted"` → invalidate `["resumes"]` and move to review. On `done` with `status === "failed"` or `error` → failed view.
    - status `extracted` (and not confirmed): fetch `["resume-extraction", activeId]` via `api.resumes.extraction(activeId)`; while pending show skeleton; then `<ExtractionReview extraction onConfirm={confirm} confirming={confirmMut.isPending} />`.
    - status `failed`: `<ResumeFailed message={resume.parse_error} onRetry={retry} onReupload={() => setActiveId(null)} retrying={retryMut.isPending} />`.
  - `confirm` mutation → `api.resumes.confirmProfile(activeId, edited)` → on success: `queryClient.invalidateQueries({ queryKey: ["profile"] })` + `["resumes"]`, `toast({ title: "Profile updated from your résumé" })`, `router.push("/dashboard")`.
  - `upload` mutation → `api.resumes.upload(file)` → `setActiveId(res.id)`, invalidate `["resumes"]`.
  - `retry` mutation → `api.resumes.reprocess(id)` → invalidate `["resumes"]`, keep `activeId`.
  - Otherwise (there is ≥1 confirmed résumé and no active flow) → `<ResumeList>` wired to `setPrimary` / `review` (`setActiveId`) / `retry` / `delete` (`api.resumes.remove` → invalidate) mutations, and `onUploadAnother={() => setActiveId(null)}` scrolling to a shown `<UploadDropzone>`.
  - Any mutation error → `toast` with the `ProblemError.problem.detail` fallback.
- Data flow one-liner: `upload → activeId → useResumeEvents(activeId) drives the stepper → on extracted, GET extraction → edit → confirm → invalidate ["profile"] → /dashboard`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/resume/resume-page.test.tsx` — use `renderWithProviders` with a stub `api`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders, mockPush } from "@/test/utils";
import ResumePage from "@/app/(app)/resume/page";

function stubApi(over: Record<string, unknown> = {}) {
  return {
    resumes: {
      list: vi.fn(async () => []),
      get: vi.fn(),
      upload: vi.fn(async () => ({ id: "r1", status: "uploaded" })),
      extraction: vi.fn(async () => ({ full_name: "Jane", experiences: [], education: [], projects: [], certifications: [] })),
      patch: vi.fn(),
      reprocess: vi.fn(),
      remove: vi.fn(),
      confirmProfile: vi.fn(async () => undefined),
      ...over,
    },
  };
}

describe("ResumePage", () => {
  it("shows the dropzone when the user has no résumés", async () => {
    renderWithProviders(<ResumePage />, { api: stubApi(), authValue: { status: "authed", user: { id: "u1" } as never } });
    expect(await screen.findByTestId("resume-file-input")).toBeInTheDocument();
  });

  it("uploads, walks the stepper to extracted, confirms, and routes to /dashboard", async () => {
    const api = stubApi();
    // authedStream yields a completed pipeline for r1
    const authedStream = vi.fn(async () =>
      new Response(
        `event: status\ndata: {"status":"extracted","message":"Ready to review"}\n\n` +
          `event: done\ndata: {"status":"extracted","totals":{}}\n\n`,
        { status: 200 },
      ),
    );
    renderWithProviders(<ResumePage />, {
      api,
      authValue: { status: "authed", user: { id: "u1" } as never, authedStream },
    });
    await userEvent.upload(await screen.findByTestId("resume-file-input"),
      new File([new Uint8Array(10)], "cv.pdf", { type: "application/pdf" }));
    // list is re-fetched — make the 2nd list() return the uploaded résumé as extracted
    api.resumes.list.mockResolvedValue([
      { id: "r1", title: "cv.pdf", original_filename: "cv.pdf", content_type: "application/pdf",
        size_bytes: 10, page_count: 1, status: "extracted", parse_error: null, is_primary: true,
        confirmed_at: null, created_at: "", updated_at: "" },
    ]);
    await screen.findByLabelText(/full name/i, undefined, { timeout: 3000 });
    await userEvent.click(screen.getByRole("button", { name: /confirm & build/i }));
    await waitFor(() => expect(api.resumes.confirmProfile).toHaveBeenCalledWith("r1", expect.any(Object)));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
  });
});
```

> This is an integration test; the implementer may split it into two (`dropzone visible` / `full happy path`) and adjust query-invalidation timing with `waitFor`. The load-bearing assertions: dropzone with no résumés, and `confirmProfile("r1", …)` + `router.push("/dashboard")` on the happy path.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** `ResumePage` to the Produces contract. Keep the state machine explicit (a small `phase` derived from `activeResume?.status` + `activeId` + mutation pending flags), not a `useReducer`. Guard every `useResumeEvents` call with `enabled: phase === "processing"`.

- [ ] **Step 4: Run — expect pass** (`pnpm test -- resume-page && pnpm exec tsc --noEmit`).

- [ ] **Step 5: Commit**

```bash
git add "frontend/app/(app)/resume/page.tsx" frontend/tests/resume/resume-page.test.tsx
git commit -m "feat(resume): /resume route — upload → stepper → review → confirm flow"
```

---

## Task 11: Frontend — onboarding wiring (nav, register redirect, dashboard nudge)

**Files:**
- Create: `frontend/components/resume/SetupProfileCard.tsx`
- Modify: `frontend/components/layout/nav-items.ts`, `frontend/components/auth/RegisterForm.tsx`, `frontend/app/(app)/dashboard/page.tsx`
- Test: `frontend/tests/resume/setup-profile-card.test.tsx`, and extend `frontend/tests/auth/register-form.test.tsx`, `frontend/tests/dashboard.test.tsx`, `frontend/tests/layout/*` as needed.

**Interfaces:**
- Consumes: `Card`, `Button`, `Link` from `next/link`, `useAuth`, `useQuery`.
- Produces:
  - `SetupProfileCard()` — a `<Card>` headed "Finish setting up your profile" with copy and a **"Upload your résumé"** `<Link href="/resume">` styled as a button.
  - `nav-items.ts`: a new `{ href: "/resume", label: "Résumé", icon: ScrollText, ready: true }` inserted right after `/dashboard` (import `ScrollText` from `lucide-react`).
  - `RegisterForm`: on successful `register(...)`, `router.push("/resume")` instead of `/dashboard`.
  - `dashboard/page.tsx`: queries `["resumes"]`; if `resumes.length === 0 || resumes.every(r => !r.confirmed_at)` renders `<SetupProfileCard>` above the existing content.

- [ ] **Step 1: Write / update the failing tests**

`frontend/tests/resume/setup-profile-card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SetupProfileCard } from "@/components/resume/SetupProfileCard";

it("links to /resume", () => {
  render(<SetupProfileCard />);
  expect(screen.getByRole("link", { name: /upload your résumé/i })).toHaveAttribute("href", "/resume");
});
```

Update `frontend/tests/auth/register-form.test.tsx`: the "redirects after register" case asserts `mockPush` was called with `"/resume"` (was `"/dashboard"`).

Update `frontend/tests/dashboard.test.tsx`: add a case — with `api.resumes.list` resolving `[]`, `getByText(/finish setting up your profile/i)` is present; with a confirmed résumé it is absent.

- [ ] **Step 2: Run — expect fail** (SetupProfileCard missing; register-form still pushes `/dashboard`).

- [ ] **Step 3: Implement** all four changes. For `dashboard/page.tsx`, reuse the existing `useAuth().api` + `useQuery({ queryKey: ["resumes"], queryFn: () => api.resumes.list() })`; render `<SetupProfileCard />` conditionally; keep the rest of the page intact.

- [ ] **Step 4: Run — expect pass** (`pnpm test && pnpm lint && pnpm exec tsc --noEmit` — the **whole** suite, since nav/register/dashboard are shared).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/resume/SetupProfileCard.tsx frontend/components/layout/nav-items.ts frontend/components/auth/RegisterForm.tsx "frontend/app/(app)/dashboard/page.tsx" frontend/tests/resume/setup-profile-card.test.tsx frontend/tests/auth/register-form.test.tsx frontend/tests/dashboard.test.tsx
git commit -m "feat(resume): onboarding wiring — nav item, register→/resume, dashboard nudge"
```

---

## Task 12: Phase 2b verification & completion report

- [ ] **Step 1: Full frontend gate**

`cd frontend && pnpm lint && pnpm exec tsc --noEmit && pnpm test` — eslint clean; `tsc` clean; every Vitest suite green (Phase 1c + Phase 2b). Note the total test count vs. the pre-phase baseline.

- [ ] **Step 2: Full backend gate**

`cd backend && "$UV" run ruff check . && "$UV" run lint-imports && "$UV" run mypy app && "$UV" run pytest -q` — ruff clean; 2 import contracts kept; mypy clean; pytest green (DB+Redis-backed suites run in CI — locally confirm `"$UV" run pytest --collect-only -q` is error-free and the `tests/core/test_events.py` additions pass).

- [ ] **Step 3: Manual smoke (documented, not a gate)**

If a dev stack is available: register → land on `/resume` → upload a text-based PDF → stepper advances → review screen seeded → edit a field, remove a row → Confirm → `/dashboard` shows the populated profile + no "Finish setting up" card. Record the result (or "not run — no stack") in the report.

- [ ] **Step 4: Fill the completion report below, commit**

```bash
git add docs/superpowers/plans/2026-09-01-phase-2b-resume-frontend.md
git commit -m "docs: Phase 2b completion report"
```

---

## Phase 2b completion report

_Executed 2026-09-01 via subagent-driven-development (12 tasks, fresh implementer + two-verdict
review per task). Ledger: `.superpowers/sdd/2026-09-01-phase-2b-resume-frontend/progress.md`.
Tasks 4, 6, 8, 10 each took one fix round; the rest passed first review._

- **What changed:**
  - **Backend SSE §6.4** (`app/core/events.py`, `app/api/v1/resumes.py`) — the résumé stream now emits
    `event: done {status, totals}` on a terminal status and `event: error {code, message}` on a
    malformed pub/sub payload, and no longer sends the custom `ping` frame (`EventSourceResponse`
    keepalives suffice). Closes the deferred Phase-2a I12 chip.
  - **`hooks/useResumeEvents.ts`** — the project's `useSSE` foundation: streams
    `GET /resumes/{id}/events` over `fetch` + `ReadableStream` via `authedStream` (not `EventSource`,
    which can't send `Authorization`), CRLF-tolerant frame parser, exponential-backoff reconnect
    (5 attempts) that re-reads current status on every reconnect. Returns `{status, message, done, error}`.
  - **`providers/AuthProvider.tsx`** — `authedStream(path, init) => Promise<Response>`: bearer +
    one silent refresh-and-retry on 401, raw `Response` for streaming.
  - **`components/ui/textarea.tsx`** — `<Textarea>` primitive (matches `<Input>`).
  - **`components/resume/`** — `UploadDropzone` (drag-drop PDF picker, client type/size checks,
    `accept="application/pdf"`), `ResumeStepper` (3-stage aria-live progress), `ResumeFailed` (retry /
    re-upload card), `ReviewSection` + `ExtractionReview` (react-hook-form review form: scalars +
    4 collapsible sections, per-row remove, `is_current` round-tripped without a control, Confirm →
    corrected `ResumeExtraction`), `ResumeList` (returning-user list: set-primary / re-review / retry /
    delete), `SetupProfileCard` (dashboard nudge).
  - **`app/(app)/resume/page.tsx`** — the flow state machine (`idle → processing → review | failed`,
    plus `list`); a sticky `streamOutcome` drives phase transitions off the SSE `done` frame (with
    `invalidateQueries` still firing) rather than waiting on a status refetch; confirm → invalidate
    `qk.profile` + `qk.resumes`, toast, `router.push("/dashboard")`.
  - **Onboarding wiring** — `RegisterForm` redirects to `/resume`; `nav-items.ts` gains a Résumé entry;
    the dashboard shows `<SetupProfileCard>` until a résumé has `confirmed_at`.
  - **`lib/`** — `api/types.ts` (+`ResumeStatus`/`ResumeOut`/`ResumeExtraction`),
    `api/endpoints.ts` (+`api.resumes` group), `resume/extraction-form.ts` (zod + converters),
    `query.ts` (+`qk.resumes`/`qk.resumeExtraction`).
- **Why:** the résumé is the on-ramp — the human surface for §3.2 J1 (upload → review → confirm →
  populated dashboard); `useResumeEvents` is the `useSSE` foundation reused by the agent/builder in
  Phases 7–12.
- **Files changed / new deps:** ~26 frontend files (10 new components/hooks, 4 lib edits, 1 route,
  ~11 test files) + 3 backend files. **No new dependencies** — `react-hook-form` / `zod` /
  `@hookform/resolvers` were already present.
- **How to test:** `cd frontend && pnpm exec vitest run` · `cd backend && uv run pytest tests/core/test_events.py -q`.
- **Regression check:** whole frontend suite green (29 files / 71 tests); `tsc --noEmit` + `next lint`
  clean; backend `ruff` / `mypy` (65 files) / `import-linter` (2 contracts) clean, suite collects 162
  with no errors; `/auth`, `/profile`, `/health` and the Phase 2a résumé API untouched.
- **Baseline:** frontend ~35 → **71** tests (+36). Backend 158 → **162** (Task 1's `test_events.py`
  net: old stream test replaced by 3 new). DB+Redis-backed backend suites verify in CI.
- **Deviations:**
  - **fetch-stream SSE, not `EventSource`** — `EventSource` cannot send an `Authorization` header and
    the access token is memory-only.
  - **`useResumeEvents` frame splitting is CRLF-tolerant** (`/\r\n\r\n|\n\n/`) — sse-starlette's
    default separator is `\r\n`; the first cut used `\n\n` and would have parsed nothing (caught in
    Task 4 review).
  - **`streamOutcome` sticky state** in `/resume` page instead of pure query-invalidation — the pure
    design deadlocks the test and is prod-racy when the SSE `done` frame beats DB-status visibility.
  - **`ExtractionReview` experience-row "location" labelled "City"** so the scalar "Location" stays a
    unique `getByLabelText` match.
  - `is_current` (experiences) is round-tripped through the form without a rendered control;
    `*_date` fields are intentionally not (Phase 2a's `confirm_profile` excludes every `*_date`).
  - **Whole-branch fix wave (BASE `ce883fe`):**
    - **`highlights` (experiences + projects) edit as newline-delimited text in a `<Textarea>`, not
      CSV** — LLM bullets routinely contain commas, so the CSV round-trip shredded a bullet like
      `"Cut p99 latency by 40%, saving $120k/yr"` into two on the zero-interaction Confirm path.
      `skills` and per-row `tech` stay CSV (short tokens).
    - **`full_name`, `email`, `skills`, and every per-row `start_date` / `end_date` render read-only**
      in `ExtractionReview` (under "Saved with your résumé — Mana uses this from a later step.").
      Phase 2a's `confirm_profile` merges `location` / `*_url` / `career_goals(←summary)` + the
      sub-entities' non-date fields, but **not** `full_name` / `email` / `skills` / any `*_date`, so
      an inline edit to those would toast success and silently not stick. They still ride to the
      backend unchanged in the payload (kept complete for future extraction-eval).
    - **`streamOutcome` is 3-way** (`"extracted" | "failed" | "disconnected"`): a dropped SSE stream
      (`ev.error`) now shows a distinct connection-failure card (`<ResumeFailed kind="connection">`),
      not the misleading "scanned or image-only PDF" pipeline copy. A `reuploadRequested` flag
      suppresses implicit-active adoption after "Upload a different file" so the user reaches (and
      stays on) the dropzone instead of being bounced back onto the still-`extracting` résumé. A
      3-minute wall-clock timer surfaces an inline "taking longer than usual" escape hatch if the
      worker dies without emitting `done`.
    - **Focus management:** `ExtractionReview` and `ResumeFailed` focus their top `<h2 tabIndex={-1}>`
      on mount (the stepper already self-announces via `aria-live`).
    - **`applyProblemToForm` keys `setError` on the full dotted `loc` path below `body`** (not the
      tail segment) so a backend row-validation error reaches the wired-up row `<Field>`.
    - `qk.resumeExtraction` accepts `string | null`; `/resume` passes `skipToken` while not reviewing.
    - `test/utils.tsx` re-exports `AuthContext` straight from `@/providers/AuthProvider` (re-exporting
      the imported local binding trips a Vite SSR live-binding quirk); `use-resume-events.test.ts`
      switched its import back to `@/test/utils` and stays green.
  - Test-runner note: `pnpm test` is watch-mode; CI and this phase used `pnpm exec vitest run`.
- **Not verified here:** real end-to-end against a live worker + Redis (needs the dev stack / a CI e2e —
  out of scope); résumé-workspace 3-pane, versions, skill-taxonomy normalization, date-string parsing
  (their phases); the `/resume` `list`-phase branches (delete-of-active, retry re-entry) are traced but
  not test-covered.
- **Deferred minors (carried to the whole-branch review triage):** `test/utils.tsx` `AuthContext`
  re-export trips a Vite SSR binding quirk (one-line fix: re-export from source); `useResumeEvents`
  reader not explicitly released on the reconnect path; `applyProblemToForm` keys `setError` on only
  the tail `loc` segment so backend row-validation errors don't reach the now-wired row `<Field>`s;
  `ExtractionReview` submit label flips only on `confirming`, not `isSubmitting`; `/resume` `onReupload`
  can transiently bounce during the SSE-vs-DB sync window (self-correcting); `UploadDropzone` has no
  `aria-describedby` from control to error; `qk.resumeExtraction(reviewId ?? "")` builds a key while
  disabled (`skipToken` tidier).

---

## Self-Review

**1. Spec coverage (Phase 2 frontend half of §9 + §3.2 J1 + §6.4 + §7.2/7.5/7.6):**
- `upload PDF` → Task 6 (`UploadDropzone`) + Task 10 (upload mutation). ✓
- `3-stage parse/extract/index stepper` → Task 7 (`ResumeStepper`, 3 steps ending at "Ready to review" — the `index` stage is Phase 6, noted). ✓
- SSE status → Task 1 (backend §6.4) + Task 4 (`useResumeEvents`). ✓
- `review extracted profile → edit/confirm` → Task 8 (`ExtractionReview`, light inline edits) + Task 10 (confirm mutation → `/confirm-profile`). ✓
- `dashboard populates` → Task 10 (`invalidateQueries(["profile"])` + `router.push("/dashboard")`) + Task 11 (nudge disappears once a résumé has `confirmed_at`). ✓
- `corrections saved inline` → Task 8 sends the user-corrected `ResumeExtraction`; "corrections become extraction-eval labels" is a Phase 3 backend concern (the frontend already sends the diffable corrected payload). ✓
- `useSSE hook (auth, backoff, reconnect)` §7.2 → Task 4 (fetch-stream, 5-try exponential backoff, re-reads status on reconnect via the backend's `open`-triggered DB read). ✓
- `react-hook-form + zod, problem+json errors[] onto fields` §7.2 → Task 8 (`reviewSchema` + `applyProblemToForm`). ✓
- loading/empty/error §7.5 → skeletons (Task 10 extraction fetch, dashboard), the stepper as the labelled spinner, `UploadDropzone` empty state, `toast` + inline + retry everywhere. ✓
- a11y §7.6 → `aria-live` stepper (Task 7), keyboard-operable dropzone (Task 6), `role="alert"` inline errors, token focus rings inherited from the primitives. ✓
- register → `/resume` first-run → Task 11. ✓
- **Deferred, flagged:** résumé-workspace 3-pane / versions / diff (Phase 8); skill-taxonomy + date normalization (Phase 3); embeddings "index" stage (Phase 6); multi-résumé matching selection (later).

**2. Placeholder scan:** Tasks 1, 2, 4, 5, 6, 7 carry literal code + tests. Tasks 3, 8, 9, 10, 11 carry full interface contracts + concrete tests and describe the component bodies against those contracts (the shapes are pinned by the Produces blocks and the load-bearing test assertions) — consistent with the Phase 2a plan's accepted style. Two test seams are named explicitly: the injectable backoff-base in `useResumeEvents` and the `data-testid` row selectors in the review form / list. No "TBD".

**3. Type consistency:**
- `ResumeStatus` / `ResumeOut` / `ResumeExtraction` (+ nested `Extracted*`) — defined once in Task 2, consumed verbatim by Tasks 4 (`status`), 7 (`ResumeStatus`), 8 (`ResumeExtraction`), 9 (`ResumeOut`), 10 (all). Field names mirror the Phase 2a Pydantic (`app/domain/resume/extractor.py`) exactly.
- `useAuth().authedStream: (path, init?) => Promise<Response>` — added in Task 3, consumed only by Task 4; `makeAuthValue` default keeps every prior `renderWithProviders` test compiling.
- `useResumeEvents(id, {enabled}) => {status, message, done, error}` — Task 4 defines, Task 10 consumes (guards with `enabled`).
- `ExtractionReview`'s `onConfirm: (e: ResumeExtraction) => Promise<void>` — Task 8 defines, Task 10 passes `(e) => confirmMut.mutateAsync(e)`.
- `api.resumes.*` — Task 2 defines `list/get/upload/extraction/patch/reprocess/remove/confirmProfile`; Tasks 10 & 11 call exactly those names.
- SSE frame contract: Task 1 backend emits `status`/`done`/`error`; Task 4's `parseFrame` + the reducer handle exactly those three `event` values (plus ignores `open`/comments).
- `toFormValues` / `toExtraction` (Task 8) are the only place `string[]` ⇄ csv `string` conversion happens; `ReviewFormValues` is the rhf shape, `ResumeExtraction` the wire shape.

**4. Ambiguity check:** The review form allows **edit + remove**, not **add** (adding sections is `/profile`'s job — matches "light inline edits"). The "active résumé" for the flow is the newest `!confirmed_at && status !== "failed"` résumé or the just-uploaded one; everything else renders the list. The stepper shows 3 steps and treats `extracted` as all-complete; `failed` is a separate view, not a stepper state. Reconnect in `useResumeEvents` is capped at 5 attempts, then `error` + `done`. `authedStream` returns the raw `Response` (never reads the body) so the hook owns stream parsing.
