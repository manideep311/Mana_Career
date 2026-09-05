# Phase 8b — Résumé tailoring (frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user kick off a "tailor my résumé for this job" agent run from a Job Detail page, watch it stream live, and land on a field-level diff of what changed — plus browse past tailored versions and download any version in md/html/pdf/docx.

**Architecture:** New API types + `api.resumes.*` endpoints + query keys for `ResumeVersion`/`ResumeDiff`; a `useTailorRunEvents` hook that watches an already-started agent run over SSE (single-attempt, no reconnect — see rationale in Task 3); a `ResumeSuggestionBlockView` registered into the existing block registry; a `<TailorButton>` on Job Detail; a "Tailored versions" section on `/resume`; a new `/resume/versions/[id]` diff page.

**Tech Stack:** Next.js 15, React 19, TanStack Query v5, TypeScript, Vitest + Testing Library, pnpm.

**Spec:** `docs/superpowers/specs/2026-09-04-phase-8b-resume-tailoring-frontend.md` (full addendum — read this first, it documents two backend fixes already on `main` and two scope cuts from the original design) + `docs/superpowers/specs/2026-09-04-phase-8-resume-tailoring.md` §9 (superseded by the addendum) + master `2026-08-30-mana-career-design.md` §4.3/§5.3.

## Global Constraints

- Backend is done and on `main` (`8430ae9` + hotfixes `55fe27c`, `da13755`). This plan touches **`frontend/` only**.
- `pnpm exec eslint` is broken repo-wide (ESLint 9 vs a legacy `.eslintrc.json`) — the real lint gate is `pnpm lint` (= `next lint`). Local gates for every task: `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm vitest run <the task's test files>`.
- Semantic color tokens only — `text-positive`/`bg-positive-soft`, `text-warning`/`bg-warning-soft`, `text-danger`/`bg-danger-soft`, `text-accent`/`bg-accent-soft`, `bg-surface-sunk`/`text-text-muted`/`text-text-subtle` (see `app/globals.css` `@theme inline`, mirrored in `components/jobs/MatchBadge.tsx`). No raw hex, no Tailwind color-literal classes (`bg-green-500` etc.).
- SSE hooks in this codebase each carry their own copy of a `parseFrame` helper and the `/\r\n\r\n|\n\n/` frame-split regex — this is the established repo convention (see `hooks/useAgentStream.ts`, `hooks/useJobEvents.ts`, `hooks/useResumeEvents.ts`), not something to extract into a shared module.
- `authedStream(path, init)` (from `useAuth()`) is for any request whose response isn't parsed as JSON by `apiFetch` — raw SSE bodies (existing) and now raw render bodies (blob/text) too. `api.resumes.renderUrl(...)` returns a path string, not a fetch call — callers pass it straight into `authedStream`.
- Every new/edited `ResponseBlock`-shaped type change goes through `lib/api/types.ts`'s existing discriminated union (`TextBlock | JobCardBlock | InsufficientInfoBlock | StubBlock` → gains `ResumeSuggestionBlock`), dispatched by `components/ai/blocks/block-registry.tsx`'s `switch (block.kind)`. Follow `JobCardBlockView`'s "the view owns its own fetch" pattern exactly for `ResumeSuggestionBlockView`.
- Test conventions: `renderWithProviders(ui, { api: {...partial overrides...} })` and `AuthContext`/`makeAuthValue` from `@/test/utils` (see `tests/ai/block-registry.test.tsx`, `tests/ai/use-agent-stream.test.ts`, `tests/resume/use-resume-events.test.ts` for the exact shapes to mirror).
- `ResumeVersionOut.claim_validation` is `{}` (no `checked`/`unsupported`/`supported_ratio`/`passed` keys) for `base_snapshot`/`manual_edit` versions — only `ai_tailored` versions carry all four. Type it as `Partial<ClaimValidation>` and guard on `"passed" in claim_validation` (or `claim_validation.checked != null`) before rendering the banner — never assume the fields exist.
- `FieldDelta.path` format (from the backend, not repeated by the frontend): a bare field name for a top-level scalar or the top-level `skills` list (`"summary"`, `"skills"`); `"{section}[{i}]"` for a whole added/removed entry; `"{section}[{i}].{field}"` for a changed sub-field (including `highlights`/`tech` list sub-fields). Group the UI by the text before the first `[` or `.`.

---

## Task 1: Types + endpoints + query keys

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/api/endpoints.ts`
- Modify: `frontend/lib/query.ts`
- Modify: `frontend/tests/api/endpoints.test.ts`

**Interfaces:**
- Produces: `RunRef { run_id, session_id }`; `ClaimValidation`; `ResumeVersion`; `ResumeVersionDetail`; `FieldDelta`; `ResumeDiff`; `ResumeSuggestionBlock`; `api.resumes.tailor(id, {job_id}) -> Promise<RunRef>`; `api.resumes.versions(id) -> Promise<{items: ResumeVersion[]}>`; `api.resumes.version(versionId) -> Promise<ResumeVersionDetail>`; `api.resumes.diff(versionId, against?) -> Promise<ResumeDiff>`; `api.resumes.renderUrl(versionId, fmt) -> string`; `qk.resumeVersions(resumeId)`, `qk.resumeVersion(id)`, `qk.resumeDiff(id, against?)`.
- Consumes: nothing new (extends the existing `RunRef`/`StubBlock` shapes and `makeApi(f)`/`Fetcher` pattern).

- [ ] **Step 1: `lib/api/types.ts` — extend `RunRef`, add the version/diff types, carve out `ResumeSuggestionBlock`**

Replace the existing `RunRef` interface:
```typescript
export interface RunRef {
  run_id: string;
  session_id: string;
}
```

Add after `ResumeExtraction` (after the closing brace at the line that currently reads `}` following `certifications?: ExtractedCertification[];`):
```typescript
export interface ClaimValidation {
  checked: number;
  unsupported: string[];
  supported_ratio: number;
  passed: boolean;
}

export type ResumeVersionKind = "base_snapshot" | "manual_edit" | "ai_tailored";

export interface ResumeVersion {
  id: string;
  kind: ResumeVersionKind;
  label: string | null;
  job_id: string | null;
  parent_version_id: string | null;
  created_by: "user" | "mana_ai";
  created_at: string;
  claim_validation: Partial<ClaimValidation>;
}

export interface ResumeVersionDetail extends ResumeVersion {
  content: ResumeExtraction;
}

export type FieldDeltaOp = "added" | "removed" | "changed" | "reordered";

export interface FieldDelta {
  path: string;
  op: FieldDeltaOp;
  before: unknown;
  after: unknown;
}

export interface ResumeDiff {
  deltas: FieldDelta[];
}
```

In the `StubBlock` kind union, remove `"resume_suggestion"`:
```typescript
/** Declared-but-unrendered block kinds (Phases 9–12) — the registry shows a muted fallback. */
export interface StubBlock {
  kind:
    | "match_score"
    | "skill_gap"
    | "career_recommendation"
    | "learning_recommendation"
    | "application_draft"
    | "approval_action";
  [field: string]: unknown;
}
export interface ResumeSuggestionBlock {
  kind: "resume_suggestion";
  suggestion_id: string;
}
export type ResponseBlock =
  | TextBlock
  | JobCardBlock
  | InsufficientInfoBlock
  | ResumeSuggestionBlock
  | StubBlock;
```

- [ ] **Step 2: `lib/api/endpoints.ts` — add the five `resumes` methods**

Add `ClaimValidation` is not imported (unused directly); import the new types actually referenced:
```typescript
  ResumeDiff,
  ResumeExtraction,
  ResumeOut,
  ResumeVersion,
  ResumeVersionDetail,
  RunRef,
```
(insert `ResumeDiff` before `ResumeExtraction`, and `ResumeVersion`, `ResumeVersionDetail` after `ResumeOut`, keeping the existing alphabetical-ish list — `RunRef` already exists in the import list, just keep it.)

Inside the `resumes: { ... }` block, after `confirmProfile`, add:
```typescript
      async tailor(id: string, body: { job_id: string }) {
        return f<RunRef>(`/api/v1/resumes/${id}/tailor`, json("POST", body));
      },
      async versions(id: string) {
        return f<{ items: ResumeVersion[] }>(`/api/v1/resumes/${id}/versions`);
      },
      async version(versionId: string) {
        return f<ResumeVersionDetail>(`/api/v1/resumes/versions/${versionId}`);
      },
      async diff(versionId: string, against?: string) {
        const qs = against ? `?against=${encodeURIComponent(against)}` : "";
        return f<ResumeDiff>(`/api/v1/resumes/versions/${versionId}/diff${qs}`);
      },
      renderUrl(versionId: string, fmt: "md" | "html" | "pdf" | "docx") {
        return `/api/v1/resumes/versions/${versionId}/render?fmt=${fmt}`;
      },
```

- [ ] **Step 3: `lib/query.ts` — add the three query keys**

After `resumeExtraction`:
```typescript
  resumeVersions: (resumeId: string) => ["resume", resumeId, "versions"] as const,
  resumeVersion: (id: string) => ["resume-version", id] as const,
  resumeDiff: (id: string, against?: string) =>
    ["resume-version", id, "diff", against ?? null] as const,
```

- [ ] **Step 4: extend `tests/api/endpoints.test.ts`**

Add a new `describe` block at the end of the file:
```typescript
describe("resume tailoring", () => {
  it("tailor POSTs { job_id } to /resumes/{id}/tailor", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.tailor("r1", { job_id: "j1" });
    expect(calls[0].path).toBe("/api/v1/resumes/r1/tailor");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ job_id: "j1" });
  });

  it("versions GETs /resumes/{id}/versions", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.versions("r1");
    expect(calls[0].path).toBe("/api/v1/resumes/r1/versions");
  });

  it("version GETs /resumes/versions/{id}", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.version("v1");
    expect(calls[0].path).toBe("/api/v1/resumes/versions/v1");
  });

  it("diff GETs /resumes/versions/{id}/diff with no query by default", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.diff("v1");
    expect(calls[0].path).toBe("/api/v1/resumes/versions/v1/diff");
  });

  it("diff GETs /resumes/versions/{id}/diff?against=... when given", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.diff("v1", "base");
    expect(calls[0].path).toBe("/api/v1/resumes/versions/v1/diff?against=base");
  });

  it("renderUrl builds a fmt-qualified path with no fetch call", () => {
    const { f } = recordingFetcher();
    const url = makeApi(f).resumes.renderUrl("v1", "pdf");
    expect(url).toBe("/api/v1/resumes/versions/v1/render?fmt=pdf");
    expect(f).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 5: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/api/endpoints.test.ts`
Expected: all PASS (lint clean, no type errors, new tests green).

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/lib/query.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(resume-fe): résumé version/diff/tailor types + endpoints + query keys"
```

---

## Task 2: `ResumeSuggestionBlockView` + block-registry wiring

**Files:**
- Create: `frontend/components/ai/blocks/ResumeSuggestionBlockView.tsx`
- Modify: `frontend/components/ai/blocks/block-registry.tsx`
- Modify: `frontend/tests/ai/block-registry.test.tsx`

**Interfaces:**
- Consumes: `ResumeSuggestionBlock` (Task 1), `api.resumes.version(id) -> ResumeVersionDetail` (Task 1), `qk.resumeVersion(id)` (Task 1).
- Produces: `<ResumeSuggestionBlockView block={ResumeSuggestionBlock} />`, registered for `kind === "resume_suggestion"`.

- [ ] **Step 1: `components/ai/blocks/ResumeSuggestionBlockView.tsx`**

```tsx
"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { Spinner } from "@/components/ui/spinner";
import type { ResumeSuggestionBlock } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * `block.suggestion_id` is a `ResumeVersion` id (Phase 8a reused the
 * `resume_suggestion` stub kind to mean "a tailored version is ready" — see
 * the Phase 8b spec addendum §2). This view fetches that version and offers
 * a link to its diff page; there is no accept/edit/dismiss action to wire up
 * (no `resume_suggestions` API exists — the version is already-persisted
 * history, not a proposal needing disposal).
 */
export function ResumeSuggestionBlockView({ block }: { block: ResumeSuggestionBlock }) {
  const { api } = useAuth();

  const versionQuery = useQuery({
    queryKey: qk.resumeVersion(block.suggestion_id),
    queryFn: () => api.resumes.version(block.suggestion_id),
  });

  if (versionQuery.isPending) {
    return (
      <div className="flex justify-center rounded-[var(--radius)] border border-border bg-surface p-4 text-text-muted">
        <Spinner size="sm" />
      </div>
    );
  }
  if (versionQuery.isError) {
    return (
      <p className="rounded-[var(--radius)] border border-border bg-surface p-3 text-sm text-text-muted">
        Couldn’t load that résumé version.
      </p>
    );
  }

  const v = versionQuery.data;
  const cv = v.claim_validation;
  const groundedLine =
    cv.checked != null
      ? `${cv.checked - (cv.unsupported?.length ?? 0)} of ${cv.checked} claims grounded in your résumé`
      : null;

  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius)] border border-border bg-surface p-3">
      <p className="text-sm font-medium text-text">Your résumé was tailored for this role</p>
      {groundedLine ? <p className="text-xs text-text-muted">{groundedLine}</p> : null}
      <Link
        href={`/resume/versions/${v.id}`}
        className="text-sm font-medium text-accent underline-offset-4 hover:underline"
      >
        View changes
      </Link>
    </div>
  );
}
```

- [ ] **Step 2: wire it into `components/ai/blocks/block-registry.tsx`**

```tsx
import { InsufficientInfoBlockView } from "@/components/ai/blocks/InsufficientInfoBlockView";
import { JobCardBlockView } from "@/components/ai/blocks/JobCardBlockView";
import { ResumeSuggestionBlockView } from "@/components/ai/blocks/ResumeSuggestionBlockView";
import { TextBlockView } from "@/components/ai/blocks/TextBlockView";
import type { ResponseBlock } from "@/lib/api/types";

/** Dispatches a `ResponseBlock` to its view; unknown/not-yet-built kinds get a muted line. */
export function BlockView({ block }: { block: ResponseBlock }) {
  switch (block.kind) {
    case "text":
      return <TextBlockView block={block} />;
    case "job_card":
      return <JobCardBlockView block={block} />;
    case "insufficient_info":
      return <InsufficientInfoBlockView block={block} />;
    case "resume_suggestion":
      return <ResumeSuggestionBlockView block={block} />;
    default:
      return (
        <p className="rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-xs text-text-subtle">
          {`This kind of result ("${block.kind}") is not available yet.`}
        </p>
      );
  }
}
```

- [ ] **Step 3: extend `tests/ai/block-registry.test.tsx`**

Add inside the existing `describe("BlockView", ...)` block, and change the `"unknown"` test's block kind (`"approval_action"` still works — leave it) — just add a new `it`:
```tsx
  it("renders resume_suggestion by fetching the version", async () => {
    renderWithProviders(
      <BlockView block={{ kind: "resume_suggestion", suggestion_id: "v1" }} />,
      {
        api: {
          resumes: {
            version: vi.fn(async () => ({
              id: "v1",
              kind: "ai_tailored",
              label: null,
              job_id: "j1",
              parent_version_id: null,
              created_by: "mana_ai",
              created_at: "2026-09-04T00:00:00Z",
              claim_validation: { checked: 5, unsupported: [], supported_ratio: 1, passed: true },
              content: {},
            })),
          },
        },
      },
    );
    expect(await screen.findByText("Your résumé was tailored for this role")).toBeInTheDocument();
    expect(screen.getByText("5 of 5 claims grounded in your résumé")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View changes" })).toHaveAttribute(
      "href",
      "/resume/versions/v1",
    );
  });
```

- [ ] **Step 4: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/ai/block-registry.test.tsx`
Expected: all PASS.

```bash
git add frontend/components/ai/blocks/ResumeSuggestionBlockView.tsx frontend/components/ai/blocks/block-registry.tsx frontend/tests/ai/block-registry.test.tsx
git commit -m "feat(resume-fe): ResumeSuggestionBlockView — view-only, links to the version diff"
```

---

## Task 3: `useTailorRunEvents` hook

**Files:**
- Create: `frontend/hooks/useTailorRunEvents.ts`
- Create: `frontend/tests/resume/use-tailor-run-events.test.ts`

**Interfaces:**
- Consumes: `AgentStep` (already exported from `hooks/useAgentStream.ts`), `ResponseBlock` (Task 1's extended union), `authedStream` from `useAuth()`.
- Produces: `useTailorRunEvents(sessionId: string | null, runId: string | null) -> { blocks, steps, status, error }`, used by Task 5's `<TailorButton>`.

**Design note (put this reasoning in the file's docstring, not just here):** unlike `useJobEvents`/`useResumeEvents`, this hook does **not** reconnect after a dropped stream. Those hooks reconnect because the backend re-reads DB status on every fresh `open` frame. The AI run relay (`_relay` in `app/api/v1/ai.py`) has no such re-read — it only forwards live Redis pub/sub messages for the run's channel, which has no replay buffer. A reconnect after a drop would subscribe to a channel that already finished emitting and just sit until the relay's own 300s cap synthesizes a timeout `done`. A single-attempt design (matching `useAgentStream`, which already accepts this for the chat flow) that surfaces a drop as an immediate, honest error is strictly better UX here.

- [ ] **Step 1: `hooks/useTailorRunEvents.ts`**

```typescript
"use client";

import { useEffect, useState } from "react";

import type { AgentStep } from "@/hooks/useAgentStream";
import type { ResponseBlock } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export interface TailorRunState {
  blocks: ResponseBlock[];
  steps: AgentStep[];
  status: "idle" | "streaming" | "done" | "error";
  error: string | null;
}

const INITIAL: TailorRunState = { blocks: [], steps: [], status: "idle", error: null };

interface Frame {
  event: string;
  data: Record<string, unknown>;
}

function parseFrame(raw: string): Frame | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue;
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

/**
 * Watches an already-started agent run: `GET /ai/sessions/{sessionId}/events
 * ?run_id={runId}`. Deliberately single-attempt, no reconnect — see the
 * design note in this plan's Task 3 (the relay only forwards live pub/sub
 * messages; there is nothing to resume into after a drop). A dropped stream
 * surfaces as a terminal `"error"` pointing at "Tailored versions", where
 * the result will already be sitting if the run actually finished.
 */
export function useTailorRunEvents(
  sessionId: string | null,
  runId: string | null,
): TailorRunState {
  const { authedStream } = useAuth();
  const [state, setState] = useState<TailorRunState>(INITIAL);

  useEffect(() => {
    if (!sessionId || !runId) {
      setState(INITIAL);
      return;
    }
    setState({ ...INITIAL, status: "streaming" });
    let cancelled = false;

    void (async () => {
      try {
        const res = await authedStream(
          `/api/v1/ai/sessions/${sessionId}/events?run_id=${encodeURIComponent(runId)}`,
          { headers: { Accept: "text/event-stream" } },
        );
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let m: RegExpExecArray | null;
          while ((m = /\r\n\r\n|\n\n/.exec(buf)) !== null) {
            const frame = parseFrame(buf.slice(0, m.index));
            buf = buf.slice(m.index + m[0].length);
            if (!frame || cancelled) continue;
            if (frame.event === "step") {
              setState((s) => ({
                ...s,
                steps: [
                  ...s.steps,
                  {
                    node: String(frame.data.node ?? ""),
                    status: String(frame.data.status ?? ""),
                    summary: String(frame.data.summary ?? ""),
                  },
                ],
              }));
            } else if (frame.event === "block") {
              const block = frame.data.block as ResponseBlock | undefined;
              if (block) setState((s) => ({ ...s, blocks: [...s.blocks, block] }));
            } else if (frame.event === "error") {
              setState((s) => ({
                ...s,
                status: "error",
                error: String(frame.data.message ?? "The run failed."),
              }));
            } else if (frame.event === "done") {
              setState((s) => (s.status === "error" ? s : { ...s, status: "done" }));
            }
          }
        }
        if (!cancelled) {
          setState((s) =>
            s.status === "streaming"
              ? {
                  ...s,
                  status: "error",
                  error: "Lost the connection. Check Tailored versions shortly.",
                }
              : s,
          );
        }
      } catch {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            status: "error",
            error: "Lost the connection. Check Tailored versions shortly.",
          }));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId, runId, authedStream]);

  return state;
}
```

- [ ] **Step 2: `tests/resume/use-tailor-run-events.test.ts`**

```typescript
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { useTailorRunEvents } from "@/hooks/useTailorRunEvents";

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
  return ({ children }: { children: ReactNode }) =>
    createElement(AuthContext.Provider, { value }, children);
}

describe("useTailorRunEvents", () => {
  it("accumulates step and block frames then marks done", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: open\ndata: {"event":"open","run_id":"r1"}\n\n`,
        `event: step\ndata: {"event":"step","node":"resume_tailoring","status":"ok","summary":"Tailored résumé draft ready"}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"text","markdown":"Done."}}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"resume_suggestion","suggestion_id":"v1"}}\n\n`,
        `event: done\ndata: {"event":"done","status":"completed","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useTailorRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(authedStream).toHaveBeenCalledWith(
      "/api/v1/ai/sessions/s1/events?run_id=r1",
      expect.objectContaining({ headers: { Accept: "text/event-stream" } }),
    );
    expect(result.current.steps).toHaveLength(1);
    expect(result.current.blocks.map((b) => b.kind)).toEqual(["text", "resume_suggestion"]);
    expect(result.current.error).toBeNull();
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"event":"error","message":"The run failed."}\n\n`]),
    );
    const { result } = renderHook(() => useTailorRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("The run failed.");
  });

  it("does not reconnect after a stream closes with no done frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: step\ndata: {"event":"step","node":"x","status":"ok","summary":"s"}\n\n`]),
    );
    const { result } = renderHook(() => useTailorRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("Lost the connection. Check Tailored versions shortly.");
    expect(authedStream).toHaveBeenCalledTimes(1);
  });

  it("is inert with a null sessionId or runId", () => {
    const authedStream = vi.fn();
    const { result } = renderHook(() => useTailorRunEvents(null, null), {
      wrapper: wrap(authedStream),
    });
    expect(authedStream).not.toHaveBeenCalled();
    expect(result.current).toEqual({ blocks: [], steps: [], status: "idle", error: null });
  });
});
```

- [ ] **Step 3: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/resume/use-tailor-run-events.test.ts`
Expected: all PASS.

```bash
git add frontend/hooks/useTailorRunEvents.ts frontend/tests/resume/use-tailor-run-events.test.ts
git commit -m "feat(resume-fe): useTailorRunEvents — single-attempt SSE watch for an agent run"
```

---

## Task 4: `VersionDiff` component

**Files:**
- Create: `frontend/components/resume/VersionDiff.tsx`
- Create: `frontend/tests/resume/version-diff.test.tsx`

**Interfaces:**
- Consumes: `ResumeDiff`, `FieldDelta`, `ClaimValidation` (Task 1).
- Produces: `<VersionDiff diff={ResumeDiff} claimValidation={Partial<ClaimValidation>} />`, used by Task 6's diff page.

- [ ] **Step 1: `components/resume/VersionDiff.tsx`**

```tsx
import type { ClaimValidation, FieldDelta, ResumeDiff } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const OP_LABEL: Record<FieldDelta["op"], string> = {
  added: "Added",
  removed: "Removed",
  changed: "Changed",
  reordered: "Reordered",
};

const OP_CLASS: Record<FieldDelta["op"], string> = {
  added: "bg-positive-soft text-positive",
  removed: "bg-danger-soft text-danger",
  changed: "bg-accent-soft text-accent",
  reordered: "bg-surface-sunk text-text-muted",
};

/** The text before the first `[` or `.` in a delta path — the section it groups under. */
function sectionOf(path: string): string {
  const m = /^[^[.]+/.exec(path);
  return m ? m[0] : path;
}

const SECTION_TITLE: Record<string, string> = {
  summary: "Summary",
  full_name: "Name",
  email: "Email",
  location: "Location",
  github_url: "GitHub",
  linkedin_url: "LinkedIn",
  portfolio_url: "Portfolio",
  skills: "Skills",
  experiences: "Experience",
  projects: "Projects",
  education: "Education",
  certifications: "Certifications",
};

function displayValue(v: unknown): string {
  if (v == null) return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function DeltaRow({ delta }: { delta: FieldDelta }) {
  return (
    <div className="flex flex-col gap-1 border-t border-border py-2 first:border-t-0 first:pt-0">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold",
            OP_CLASS[delta.op],
          )}
        >
          {OP_LABEL[delta.op]}
        </span>
        <span className="text-xs text-text-muted">{delta.path}</span>
      </div>
      {delta.op === "changed" ? (
        <div className="flex flex-col gap-1 text-sm">
          <p className="text-text-muted line-through decoration-danger/50">
            {displayValue(delta.before)}
          </p>
          <p className="text-text">{displayValue(delta.after)}</p>
        </div>
      ) : (
        <p className="text-sm text-text">
          {displayValue(delta.op === "removed" ? delta.before : delta.after)}
        </p>
      )}
    </div>
  );
}

/**
 * Renders a `ResumeDiff` grouped by top-level section (the text before the
 * first `[` or `.` in each delta's `path`), plus a claim-validation banner
 * when `claimValidation` actually carries fields (it's `{}` for
 * `base_snapshot`/`manual_edit` versions — only `ai_tailored` ones validate
 * claims).
 */
export function VersionDiff({
  diff,
  claimValidation,
}: {
  diff: ResumeDiff;
  claimValidation: Partial<ClaimValidation>;
}) {
  const groups = new Map<string, FieldDelta[]>();
  for (const d of diff.deltas) {
    const key = sectionOf(d.path);
    const list = groups.get(key) ?? [];
    list.push(d);
    groups.set(key, list);
  }

  return (
    <div className="flex flex-col gap-4">
      {claimValidation.checked != null ? (
        <div
          className={cn(
            "rounded-[var(--radius)] border border-border p-3 text-sm",
            claimValidation.passed ? "bg-positive-soft text-positive" : "bg-warning-soft text-warning",
          )}
        >
          {claimValidation.passed
            ? `All ${claimValidation.checked} claims are grounded in your résumé.`
            : `${claimValidation.unsupported?.length ?? 0} of ${claimValidation.checked} claims couldn’t be grounded in your résumé:`}
          {!claimValidation.passed && claimValidation.unsupported?.length ? (
            <ul className="mt-1 list-disc pl-5">
              {claimValidation.unsupported.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {diff.deltas.length === 0 ? (
        <p className="text-sm text-text-muted">No changes from the base résumé.</p>
      ) : (
        [...groups.entries()].map(([section, deltas]) => (
          <div key={section} className="rounded-[var(--radius)] border border-border bg-surface p-3">
            <h3 className="text-sm font-semibold text-text">
              {SECTION_TITLE[section] ?? section}
            </h3>
            <div>
              {deltas.map((d, i) => (
                <DeltaRow key={`${d.path}-${i}`} delta={d} />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
```

- [ ] **Step 2: `tests/resume/version-diff.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VersionDiff } from "@/components/resume/VersionDiff";
import type { ResumeDiff } from "@/lib/api/types";

describe("VersionDiff", () => {
  it("shows a no-changes message for an empty diff", () => {
    render(<VersionDiff diff={{ deltas: [] }} claimValidation={{}} />);
    expect(screen.getByText("No changes from the base résumé.")).toBeInTheDocument();
  });

  it("groups deltas by section and labels the op", () => {
    const diff: ResumeDiff = {
      deltas: [
        { path: "summary", op: "changed", before: "Old summary.", after: "New summary." },
        {
          path: "experiences[0].highlights",
          op: "added",
          before: null,
          after: ["Shipped the tailoring feature"],
        },
      ],
    };
    render(<VersionDiff diff={diff} claimValidation={{}} />);
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Experience")).toBeInTheDocument();
    expect(screen.getByText("Changed")).toBeInTheDocument();
    expect(screen.getByText("Added")).toBeInTheDocument();
    expect(screen.getByText("Old summary.")).toBeInTheDocument();
    expect(screen.getByText("New summary.")).toBeInTheDocument();
    expect(screen.getByText("Shipped the tailoring feature")).toBeInTheDocument();
  });

  it("shows a passed claim-validation banner", () => {
    render(
      <VersionDiff
        diff={{ deltas: [] }}
        claimValidation={{ checked: 4, unsupported: [], supported_ratio: 1, passed: true }}
      />,
    );
    expect(screen.getByText("All 4 claims are grounded in your résumé.")).toBeInTheDocument();
  });

  it("lists unsupported claims when validation failed", () => {
    render(
      <VersionDiff
        diff={{ deltas: [] }}
        claimValidation={{
          checked: 4,
          unsupported: ["Led a team of 12 engineers"],
          supported_ratio: 0.75,
          passed: false,
        }}
      />,
    );
    expect(screen.getByText(/1 of 4 claims couldn.t be grounded/)).toBeInTheDocument();
    expect(screen.getByText("Led a team of 12 engineers")).toBeInTheDocument();
  });

  it("renders nothing claim-related when claim_validation is empty", () => {
    render(<VersionDiff diff={{ deltas: [] }} claimValidation={{}} />);
    expect(screen.queryByText(/claims/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/resume/version-diff.test.tsx`
Expected: all PASS.

```bash
git add frontend/components/resume/VersionDiff.tsx frontend/tests/resume/version-diff.test.tsx
git commit -m "feat(resume-fe): VersionDiff — grouped field-level diff + claim-validation banner"
```

---

## Task 5: `TailorButton` + Job Detail wiring

**Files:**
- Create: `frontend/components/resume/TailorButton.tsx`
- Modify: `frontend/app/(app)/jobs/[id]/page.tsx`
- Create: `frontend/tests/resume/tailor-button.test.tsx`

**Interfaces:**
- Consumes: `api.resumes.list()` (existing), `api.resumes.tailor(id, {job_id})` (Task 1), `useTailorRunEvents(sessionId, runId)` (Task 3), `<BlockView>` (Task 2's registry entry renders the `resume_suggestion` block it receives).
- Produces: `<TailorButton jobId={string} />`.

- [ ] **Step 1: `components/resume/TailorButton.tsx`**

```tsx
"use client";

import { useState } from "react";

import Link from "next/link";

import { useMutation, useQuery } from "@tanstack/react-query";

import { BlockView } from "@/components/ai/blocks/block-registry";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import { useTailorRunEvents } from "@/hooks/useTailorRunEvents";
import type { ResumeOut } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** Primary confirmed résumé, else the first confirmed one, else none. */
function pickConfirmed(resumes: ResumeOut[] | undefined): ResumeOut | null {
  if (!resumes) return null;
  const confirmed = resumes.filter((r) => r.confirmed_at != null);
  return confirmed.find((r) => r.is_primary) ?? confirmed[0] ?? null;
}

/**
 * "Tailor résumé for this job" on a Job Detail page. Resolves the user's
 * confirmed résumé itself (mirroring the backend's own primary-or-first-
 * confirmed pick, but sent explicitly — see the Phase 8b spec addendum §1
 * for why the explicit id matters), starts the run, and watches it inline
 * via `useTailorRunEvents` until a `resume_suggestion` block arrives.
 */
export function TailorButton({ jobId }: { jobId: string }) {
  const { api } = useAuth();
  const { toast } = useToast();
  const [run, setRun] = useState<{ sessionId: string; runId: string } | null>(null);

  const resumesQuery = useQuery({ queryKey: qk.resumes, queryFn: () => api.resumes.list() });
  const resume = pickConfirmed(resumesQuery.data);

  const tailorMut = useMutation({
    mutationFn: () => api.resumes.tailor((resume as ResumeOut).id, { job_id: jobId }),
    onSuccess: (ref) => setRun({ sessionId: ref.session_id, runId: ref.run_id }),
    onError: () => toast({ title: "Couldn't start tailoring.", variant: "danger" }),
  });

  const ev = useTailorRunEvents(run?.sessionId ?? null, run?.runId ?? null);

  if (resumesQuery.isPending) {
    return (
      <Button disabled>
        <Spinner size="sm" />
        Tailor résumé for this job
      </Button>
    );
  }

  if (!resume) {
    return (
      <Button disabled title="Confirm a résumé first">
        Tailor résumé for this job
      </Button>
    );
  }

  if (run) {
    if (ev.status === "error") {
      return (
        <Card>
          <CardBody className="flex flex-col items-start gap-2">
            <p className="text-sm text-text">{ev.error}</p>
            <div className="flex items-center gap-3">
              <Button variant="outline" size="sm" onClick={() => setRun(null)}>
                Try again
              </Button>
              <Link
                href="/resume"
                className="text-sm font-medium text-accent underline-offset-4 hover:underline"
              >
                Go to Tailored versions
              </Link>
            </div>
          </CardBody>
        </Card>
      );
    }

    const suggestion = ev.blocks.find((b) => b.kind === "resume_suggestion");
    if (suggestion) {
      return <BlockView block={suggestion} />;
    }

    return (
      <Card>
        <CardBody className="flex items-center gap-2">
          <Spinner size="sm" />
          <p className="text-sm text-text-muted">
            {ev.steps.at(-1)?.summary ?? "Tailoring your résumé for this role…"}
          </p>
        </CardBody>
      </Card>
    );
  }

  return (
    <Button loading={tailorMut.isPending} onClick={() => tailorMut.mutate()}>
      Tailor résumé for this job
    </Button>
  );
}
```

- [ ] **Step 2: wire it into `app/(app)/jobs/[id]/page.tsx`**

Replace the import block's absence of `TailorButton` and the placeholder button. Add the import alongside the other `@/components/...` imports:
```typescript
import { TailorButton } from "@/components/resume/TailorButton";
```

Replace:
```tsx
      {/* Phase 8: Prepare Application */}
      <Button disabled title="Coming in a later release">
        Prepare application
      </Button>
```
with:
```tsx
      <TailorButton jobId={id} />
```

If `Button` becomes unused elsewhere in the file after this change, leave the import — it is still used by the "Remove" button earlier in the same file (confirm with a search; do not remove the import if `<Button` appears anywhere else in the file).

- [ ] **Step 3: `tests/resume/tailor-button.test.tsx`**

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TailorButton } from "@/components/resume/TailorButton";
import { renderWithProviders } from "@/test/utils";

const confirmedPrimary = {
  id: "r-primary", title: null, original_filename: "cv.pdf", content_type: "application/pdf",
  size_bytes: 100, page_count: 1, status: "extracted" as const, parse_error: null,
  is_primary: true, confirmed_at: "2026-09-01T00:00:00Z", created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};
const confirmedOther = { ...confirmedPrimary, id: "r-other", is_primary: false };
const unconfirmed = { ...confirmedPrimary, id: "r-draft", is_primary: false, confirmed_at: null };

describe("TailorButton", () => {
  it("is disabled with no confirmed résumé", async () => {
    renderWithProviders(<TailorButton jobId="j1" />, {
      api: { resumes: { list: vi.fn(async () => [unconfirmed]) } },
    });
    expect(await screen.findByRole("button", { name: /tailor résumé for this job/i })).toBeDisabled();
  });

  it("tailors the primary confirmed résumé, not a non-primary one", async () => {
    const tailor = vi.fn(async () => ({ run_id: "run1", session_id: "sess1" }));
    renderWithProviders(<TailorButton jobId="j1" />, {
      api: {
        resumes: { list: vi.fn(async () => [confirmedOther, confirmedPrimary]), tailor },
      },
    });
    const btn = await screen.findByRole("button", { name: /tailor résumé for this job/i });
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    await waitFor(() => expect(tailor).toHaveBeenCalledWith("r-primary", { job_id: "j1" }));
  });

  it("shows the resume_suggestion block once the run streams it", async () => {
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
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: block\ndata: {"event":"block","block":{"kind":"resume_suggestion","suggestion_id":"v1"}}\n\n`,
        `event: done\ndata: {"event":"done"}\n\n`,
      ]),
    );
    renderWithProviders(<TailorButton jobId="j1" />, {
      api: {
        resumes: {
          list: vi.fn(async () => [confirmedPrimary]),
          tailor: vi.fn(async () => ({ run_id: "run1", session_id: "sess1" })),
          version: vi.fn(async () => ({
            id: "v1", kind: "ai_tailored", label: null, job_id: "j1", parent_version_id: null,
            created_by: "mana_ai", created_at: "2026-09-04T00:00:00Z",
            claim_validation: { checked: 2, unsupported: [], supported_ratio: 1, passed: true },
            content: {},
          })),
        },
      },
      authValue: { authedStream },
    });
    const btn = await screen.findByRole("button", { name: /tailor résumé for this job/i });
    await userEvent.click(btn);
    expect(await screen.findByText("Your résumé was tailored for this role")).toBeInTheDocument();
  });
});
```

If `renderWithProviders`'s options type does not already accept an `authValue` override alongside `api`, check `frontend/test/utils.tsx` for the exact override shape before writing this step — mirror whatever `tests/ai/use-agent-stream.test.ts` and `tests/ai/block-registry.test.tsx` each do for combining an `api` override with a custom `authedStream`; adjust the test to that real shape rather than guessing further.

- [ ] **Step 4: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/resume/tailor-button.test.tsx`
Expected: all PASS.

```bash
git add frontend/components/resume/TailorButton.tsx "frontend/app/(app)/jobs/[id]/page.tsx" frontend/tests/resume/tailor-button.test.tsx
git commit -m "feat(resume-fe): TailorButton on Job Detail — start + watch a tailor run inline"
```

---

## Task 6: "Tailored versions" section on `/resume` + the version diff page

**Files:**
- Modify: `frontend/app/(app)/resume/page.tsx`
- Create: `frontend/components/resume/ResumeVersionsList.tsx`
- Create: `frontend/app/(app)/resume/versions/[id]/page.tsx`
- Create: `frontend/tests/resume/resume-versions-list.test.tsx`
- Create: `frontend/tests/resume/version-page.test.tsx`

**Interfaces:**
- Consumes: `api.resumes.versions`, `api.resumes.version`, `api.resumes.diff`, `api.resumes.renderUrl` (Task 1); `<VersionDiff>` (Task 4).
- Produces: a "Tailored versions" section visible in the `/resume` page's `"list"` phase; `/resume/versions/[id]`.

- [ ] **Step 1: `components/resume/ResumeVersionsList.tsx`**

```tsx
"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "@/components/ui/skeleton";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** Newest-first list of a résumé's `ai_tailored` versions, each linking to its diff page. */
export function ResumeVersionsList({ resumeId }: { resumeId: string }) {
  const { api } = useAuth();
  const versionsQuery = useQuery({
    queryKey: qk.resumeVersions(resumeId),
    queryFn: () => api.resumes.versions(resumeId),
  });

  if (versionsQuery.isPending) {
    return <Skeleton className="h-16 w-full" />;
  }
  if (versionsQuery.isError) return null;

  const tailored = versionsQuery.data.items.filter((v) => v.kind === "ai_tailored");
  if (tailored.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-text">Tailored versions</h2>
      <ul className="flex flex-col gap-2">
        {tailored.map((v) => (
          <li key={v.id}>
            <Link
              href={`/resume/versions/${v.id}`}
              className="flex items-center justify-between rounded-[var(--radius)] border border-border bg-surface p-3 text-sm hover:bg-surface-sunk"
            >
              <span className="text-text">
                {v.label ?? `Tailored ${new Date(v.created_at).toLocaleDateString()}`}
              </span>
              <span className="text-accent">View changes</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: wire it into `app/(app)/resume/page.tsx`**

Add the import:
```typescript
import { ResumeVersionsList } from "@/components/resume/ResumeVersionsList";
```

In the `phase === "list"` branch's returned JSX, insert the versions list for whichever résumé is primary-confirmed (else first confirmed), right after the `<ResumeList ... />` element and before the closing of that flex column (i.e., as a sibling between `<ResumeList>` and the `<div ref={uploadAnotherRef} ...>` block):
```tsx
          <ResumeList
            resumes={resumes}
            onSetPrimary={(id) => setPrimaryMut.mutate(id)}
            onReview={(id) => setActiveId(id)}
            onRetry={(id) => retryMut.mutate(id)}
            onDelete={(id) => deleteMut.mutate(id)}
            onUploadAnother={() => {
              setActiveId(null);
              uploadAnotherRef.current?.scrollIntoView({ block: "center" });
            }}
            busyId={busyId}
          />
          {(() => {
            const confirmed = resumes.filter((r) => r.confirmed_at != null);
            const target = confirmed.find((r) => r.is_primary) ?? confirmed[0];
            return target ? <ResumeVersionsList resumeId={target.id} /> : null;
          })()}
          <div ref={uploadAnotherRef} className="flex flex-col gap-2">
```

- [ ] **Step 3: `app/(app)/resume/versions/[id]/page.tsx`**

```tsx
"use client";

import { useState } from "react";

import { useParams } from "next/navigation";

import { useQuery } from "@tanstack/react-query";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { ErrorState } from "@/components/common/ErrorState";
import { VersionDiff } from "@/components/resume/VersionDiff";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import { ProblemError } from "@/lib/api/fetcher";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const FORMATS = [
  { fmt: "md" as const, label: "Markdown" },
  { fmt: "html" as const, label: "HTML" },
  { fmt: "pdf" as const, label: "PDF" },
  { fmt: "docx" as const, label: "DOCX" },
];

/** `/resume/versions/[id]` — the field-level diff for one tailored résumé version. */
export default function ResumeVersionPage() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";
  const { api, authedStream } = useAuth();
  const { toast } = useToast();
  const [rendering, setRendering] = useState<string | null>(null);

  const versionQuery = useQuery({
    queryKey: qk.resumeVersion(id),
    queryFn: () => api.resumes.version(id),
  });
  const diffQuery = useQuery({
    queryKey: qk.resumeDiff(id),
    queryFn: () => api.resumes.diff(id),
    enabled: versionQuery.isSuccess,
  });

  async function onRender(fmt: "md" | "html" | "pdf" | "docx") {
    setRendering(fmt);
    try {
      const res = await authedStream(api.resumes.renderUrl(id, fmt));
      if (res.status === 409) {
        toast({ title: "That format isn't available right now — try Markdown or HTML." });
        return;
      }
      if (!res.ok) throw new Error(`render ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (fmt === "docx") {
        const a = document.createElement("a");
        a.href = url;
        a.download = `resume.${fmt}`;
        a.click();
      } else {
        window.open(url, "_blank");
      }
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch {
      toast({ title: "Couldn't render that format.", variant: "danger" });
    } finally {
      setRendering(null);
    }
  }

  if (versionQuery.isPending) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (versionQuery.isError) {
    const notFound =
      versionQuery.error instanceof ProblemError && versionQuery.error.status === 404;
    return notFound ? (
      <p className="mx-auto w-full max-w-3xl text-sm text-text-muted">
        That résumé version wasn’t found.
      </p>
    ) : (
      <ErrorState onRetry={() => void versionQuery.refetch()} />
    );
  }

  return (
    <RequireAuth>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-text">
            {versionQuery.data.label ?? "Tailored résumé"}
          </h1>
          <p className="text-sm text-text-muted">
            Changes from your base résumé, {new Date(versionQuery.data.created_at).toLocaleString()}.
          </p>
        </header>

        <div className="flex flex-wrap gap-2">
          {FORMATS.map(({ fmt, label }) => (
            <Button
              key={fmt}
              variant="outline"
              size="sm"
              loading={rendering === fmt}
              onClick={() => void onRender(fmt)}
            >
              {label}
            </Button>
          ))}
        </div>

        {diffQuery.isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : diffQuery.isError ? (
          <ErrorState onRetry={() => void diffQuery.refetch()} />
        ) : (
          <VersionDiff diff={diffQuery.data} claimValidation={versionQuery.data.claim_validation} />
        )}
      </div>
    </RequireAuth>
  );
}
```

- [ ] **Step 4: `tests/resume/resume-versions-list.test.tsx`**

```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResumeVersionsList } from "@/components/resume/ResumeVersionsList";
import { renderWithProviders } from "@/test/utils";

describe("ResumeVersionsList", () => {
  it("renders nothing when there are no ai_tailored versions", async () => {
    const { container } = renderWithProviders(<ResumeVersionsList resumeId="r1" />, {
      api: {
        resumes: {
          versions: vi.fn(async () => ({
            items: [
              {
                id: "v0", kind: "base_snapshot", label: null, job_id: null,
                parent_version_id: null, created_by: "user", created_at: "2026-09-01T00:00:00Z",
                claim_validation: {},
              },
            ],
          })),
        },
      },
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
  });

  it("lists tailored versions newest first, linking to the diff page", async () => {
    renderWithProviders(<ResumeVersionsList resumeId="r1" />, {
      api: {
        resumes: {
          versions: vi.fn(async () => ({
            items: [
              {
                id: "v1", kind: "ai_tailored", label: "Tailored for Acme", job_id: "j1",
                parent_version_id: "v0", created_by: "mana_ai", created_at: "2026-09-04T00:00:00Z",
                claim_validation: { checked: 3, unsupported: [], supported_ratio: 1, passed: true },
              },
            ],
          })),
        },
      },
    });
    expect(await screen.findByText("Tailored versions")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Tailored for Acme/ })).toHaveAttribute(
      "href",
      "/resume/versions/v1",
    );
  });
});
```

- [ ] **Step 5: `tests/resume/version-page.test.tsx`**

```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ResumeVersionPage from "@/app/(app)/resume/versions/[id]/page";
import { renderWithProviders } from "@/test/utils";

/**
 * Per the established RULING R11 (`tests/jobs/job-detail-page.test.tsx`):
 * never touch `useParams` — `test/utils` already mocks it to `() => ({})`,
 * so `id === ""` for the page under test. The mocked `api` methods below
 * ignore their argument and drive the render regardless, exactly like that
 * file's `get`/`remove` mocks do.
 */
const version = {
  id: "v1", kind: "ai_tailored" as const, label: "Tailored for Acme", job_id: "j1",
  parent_version_id: null, created_by: "mana_ai" as const, created_at: "2026-09-04T00:00:00Z",
  claim_validation: { checked: 2, unsupported: [], supported_ratio: 1, passed: true },
  content: {},
};

describe("ResumeVersionPage", () => {
  it("renders the header and the diff once both queries settle", async () => {
    renderWithProviders(<ResumeVersionPage />, {
      api: {
        resumes: {
          version: vi.fn(async () => version),
          diff: vi.fn(async () => ({
            deltas: [{ path: "summary", op: "changed", before: "Old.", after: "New." }],
          })),
        },
      },
    });
    expect(await screen.findByText("Tailored for Acme")).toBeInTheDocument();
    expect(await screen.findByText("New.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Markdown" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeInTheDocument();
  });
});
```

`params.id` will be `""` under test (per R11 above) — `ResumeVersionPage`'s `const id = params.id ?? "";` already handles that the same way `JobDetailPage` does, so no page-code change is needed to accommodate the test.

- [ ] **Step 6: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/resume/resume-versions-list.test.tsx tests/resume/version-page.test.tsx tests/resume/resume-page.test.tsx`
Expected: all PASS (including the pre-existing `resume-page.test.tsx`, to confirm the new section didn't break the existing flow).

```bash
git add "frontend/app/(app)/resume/page.tsx" frontend/components/resume/ResumeVersionsList.tsx "frontend/app/(app)/resume/versions/[id]/page.tsx" frontend/tests/resume/resume-versions-list.test.tsx frontend/tests/resume/version-page.test.tsx
git commit -m "feat(resume-fe): Tailored versions list on /resume + the version diff page"
```

---

## Final gate (whole branch)

Run, from `frontend/`: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run`
Expected: all PASS, no new failures in any pre-existing suite.

Then: whole-branch review (inline, per the lean review policy — all-frontend task), squash to `main`, push, watch CI, `finishing-a-development-branch`.

---

## Completion report

**Status: shipped.** All 6 tasks executed via subagent-driven-development (fresh Sonnet implementer per task, inline controller review per task — lean policy for all-frontend work), on branch `phase-8b-resume-tailoring-frontend` off `main@76a0ad6`.

**What changed:** `RunRef` gained `session_id`; new types `ClaimValidation`/`ResumeVersion`/`ResumeVersionDetail`/`FieldDelta`/`ResumeDiff`; `ResumeSuggestionBlock` carved out of `StubBlock` into the `ResponseBlock` union; `api.resumes.tailor/versions/version/diff/renderUrl` + 3 new `qk` keys; `useTailorRunEvents` (single-attempt SSE watch — see design note below); `ResumeSuggestionBlockView` registered in the block registry; `<VersionDiff>` (grouped field-level diff + claim-validation banner); `<TailorButton>` replacing the disabled "Prepare application" placeholder on Job Detail; a "Tailored versions" section on `/resume`; the `/resume/versions/[id]` diff page with a format switcher (md/html/pdf/docx via `authedStream` + blob open/download). 19 files changed, +1093/-6, 6 commits (`e8b70aa`..`63db806`), all landed via fast-forward (the task commits were already clean — no reconstruction squash needed, unlike Phases 7a/7b/8a).

**Two backend fixes made during pre-flight, before any frontend task was dispatched** (both on `main` ahead of this branch, both CI-green independently):
- `RunRefOut` gained `session_id` (commit `55fe27c`) — `POST /resumes/{id}/tailor` creates its own session per run and returned only `{run_id}`, leaving no way to build the `/ai/sessions/{id}/events` watch URL.
- `resume_tailoring` node now honors `inputs.resume_id` instead of always picking the primary-or-first-confirmed résumé (commit `da13755`, with a DB regression test) — a real correctness bug that this phase's `TailorButton` depends on being fixed, since it always sends an explicit résumé id.

**Design ruling — why `useTailorRunEvents` doesn't reconnect:** unlike `useJobEvents`/`useResumeEvents`, which reconnect on a dropped stream because the backend re-reads DB status on every fresh `open` frame, the AI run relay (`_relay` in `ai.py`) only forwards live Redis pub/sub with no replay buffer — reconnecting after a drop would hang until the relay's own 300s cap. The hook is deliberately single-attempt (matching `useAgentStream`'s existing precedent), surfacing a drop as an immediate error pointing the user at "Tailored versions".

**Scope cut from the master spec's original §9 sketch** (both decided during spec-addendum authoring, before any task was planned): no `resume_suggestions` accept/edit/dismiss API — 8a never wrote rows to that table, so `ResumeSuggestionBlockView` is view-only, linking to the diff; no "Résumé Workspace 3-pane shell" — a "Tailored versions" section was added to the existing single-column `/resume` page instead. Both are recorded in the spec addendum §2 and left for a later phase if ever needed.

**Process notes:** two implementer dispatch attempts for Task 2 failed immediately on a session rate limit before writing any files (discarded cleanly, re-dispatched fresh once the limit reset); Task 5 and Task 6 implementers each found and fixed a real test-infra defect in this plan's own test snippets — a `findByRole` race against a still-disabled button's first paint (Task 5, fixed with a `waitFor(...).toBeEnabled()` poll) and a `container.toBeEmptyDOMElement()` assertion that can never pass because `<Toaster>` always mounts a Radix notifications region (Task 6, fixed by asserting on the component's own output instead). Both fixes were test-only, verified correct by inline review, no production code affected.

**Regression check:** full frontend suite green throughout — 135 → 140 → 145 → 148 → 151 tests across the six tasks, 47 files, zero pre-existing test broken. `pnpm lint` and `tsc --noEmit` clean at every step and on final `main`.

**CI:** [run 33940595292](https://github.com/manideep311/Mana_Career/actions/runs/33940595292) — frontend/backend/eval all green.

**Not verified here (flagged, not addressed):** the render endpoint's actual `pdf`/`docx` output was never exercised end-to-end against a real `xhtml2pdf`/`python-docx` render (backend renders are DB/CI-gated and this phase is frontend-only) — only the frontend's handling of a successful blob response and a 409 was tested with mocks. Persisting rendered files to `FileStore`, `resume_chunks` retrieval, and the accept/edit/dismiss workflow all remain out of scope per the spec addendum.
