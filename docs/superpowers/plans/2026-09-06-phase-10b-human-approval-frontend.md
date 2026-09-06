# Phase 10b — Human approval workflow (frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Prepare application" flow — from Job Detail, kick off the `prepare_application` agent run, stream it to the `human_approval` pause, show the exact cover letter + email, and on the user's explicit approval resume the run to send. Then a success state.

**Architecture:** New `applications`/`approvals` API types + endpoints + query keys. A dedicated `usePrepareRunEvents` SSE hook (`useTailorRunEvents` + one `approval`-event branch). An `<ApprovalCard>` (pure) and a `<PrepareApplicationBuilder>` orchestrator on a new `applications/new/[jobId]` route, linked from Job Detail. Post-approval progress is polled via `GET /applications/{id}`, not a re-watched SSE (see spec R2).

**Tech Stack:** Next.js 15, React 19, TanStack Query v5, TypeScript, Vitest + Testing Library, pnpm.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-10b-human-approval-frontend.md` — read first (7 rulings R1-R7 resolve every ambiguity below).

## Global Constraints

- Backend is done and CI-green on `main` (`0e03726`). This plan touches `frontend/` only.
- `pnpm exec eslint` is broken repo-wide — the real lint gate is `pnpm lint` (= `next lint`). Local gates per task: `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm vitest run <the task's test files>`.
- Semantic color tokens only (`text-accent`, `bg-surface`, `bg-surface-sunk`, `text-text`/`text-text-muted`/`text-text-subtle`, `text-positive`/`bg-positive-soft`, `text-danger`/`bg-danger-soft`, `border-border`) — no hex, no `bg-*-500` literals.
- SSE hooks each carry their own `parseFrame` copy + the `/\r\n\r\n|\n\n/` split — repo convention (`hooks/useTailorRunEvents.ts` is the direct template).
- `authedStream(path, init)` from `useAuth()` for the raw SSE body. `Link`-as-button: `<Link href={...} className={buttonVariants({ variant })}>` (see `components/resume/SetupProfileCard.tsx`).
- Test conventions: `renderWithProviders(ui, { api, authValue })` + `AuthContext`/`makeAuthValue` from `@/test/utils`; `renderHook` + `makeAuthValue({ authValue: { authedStream } })` for hooks (see `tests/resume/use-tailor-run-events.test.ts`). Page-under-test never touches `useParams` — `test/utils` mocks it to `() => ({})` (RULING R11 from `tests/jobs/job-detail-page.test.tsx`); mock `api` methods ignore their argument.

---

## Task 1: Types + endpoints + query keys

**Files:** Modify `frontend/lib/api/types.ts`, `frontend/lib/api/endpoints.ts`, `frontend/lib/query.ts`, `frontend/tests/api/endpoints.test.ts`.

**Interfaces:**
- Produces: `Application`, `ApprovalPayloadSnapshot`, `ApprovalRequest`, `ApprovalRequestList`, `ApprovalDecision`; `api.applications.create/get`; `api.approvals.list/get/decide`; `qk.application/approval/approvals`.

- [ ] **Step 1: `lib/api/types.ts`** — add near the other `Resume*`/`RunRef` types:
```typescript
export interface Application {
  id: string;
  job_id: string;
  resume_version_id: string | null;
  cover_letter_id: string | null;
  application_email_id: string | null;
  status: string;
  match_score: string | null;
  source: string;
  applied_at: string | null;
  last_status_change_at: string;
  created_at: string;
  updated_at: string;
}

export interface ApprovalPayloadSnapshot {
  job: { title: string; company: string };
  resume_version_id: string | null;
  cover_letter: { id: string; content: string };
  email: {
    id: string;
    to_email: string | null;
    to_name: string | null;
    subject: string;
    body: string;
  };
}

export interface ApprovalRequest {
  id: string;
  application_id: string;
  action_type: string;
  payload_snapshot: ApprovalPayloadSnapshot;
  status: string;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
}

export interface ApprovalRequestList {
  items: ApprovalRequest[];
}

export interface ApprovalDecision {
  decision: "approve" | "reject";
  note?: string;
}
```
(`match_score` is `string | null` because the backend serialises the `Decimal` column as a JSON string; nothing in this phase reads it, but type it honestly.)

- [ ] **Step 2: `lib/api/endpoints.ts`** — import the new types (`Application`, `ApprovalDecision`, `ApprovalRequest`, `ApprovalRequestList`) alongside the existing list; `RunRef` is already imported. Add two new sections after `resumes: { … },` (or anywhere among the domain sections — match the file's ordering style):
```typescript
    applications: {
      async create(body: { job_id: string }) {
        return f<RunRef>("/api/v1/applications", json("POST", body));
      },
      async get(id: string) {
        return f<Application>(`/api/v1/applications/${id}`);
      },
    },
    approvals: {
      async list(status?: string) {
        const qs = status ? `?status=${encodeURIComponent(status)}` : "";
        return f<ApprovalRequestList>(`/api/v1/approvals${qs}`);
      },
      async get(id: string) {
        return f<ApprovalRequest>(`/api/v1/approvals/${id}`);
      },
      async decide(id: string, body: ApprovalDecision) {
        return f<void>(`/api/v1/approvals/${id}`, json("POST", body));
      },
    },
```

- [ ] **Step 3: `lib/query.ts`** — add after `resumeDiff`:
```typescript
  application: (id: string) => ["application", id] as const,
  approval: (id: string) => ["approval", id] as const,
  approvals: (status?: string) => ["approvals", status ?? null] as const,
```

- [ ] **Step 4: `tests/api/endpoints.test.ts`** — add a `describe` block at the end:
```typescript
describe("applications + approvals", () => {
  it("applications.create POSTs { job_id } to /applications", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.create({ job_id: "j1" });
    expect(calls[0].path).toBe("/api/v1/applications");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ job_id: "j1" });
  });

  it("applications.get GETs /applications/{id}", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.get("a1");
    expect(calls[0].path).toBe("/api/v1/applications/a1");
  });

  it("approvals.list GETs /approvals with no query by default", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).approvals.list();
    expect(calls[0].path).toBe("/api/v1/approvals");
  });

  it("approvals.list GETs /approvals?status=pending when given", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).approvals.list("pending");
    expect(calls[0].path).toBe("/api/v1/approvals?status=pending");
  });

  it("approvals.get GETs /approvals/{id}", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).approvals.get("ap1");
    expect(calls[0].path).toBe("/api/v1/approvals/ap1");
  });

  it("approvals.decide POSTs the decision to /approvals/{id}", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).approvals.decide("ap1", { decision: "approve" });
    expect(calls[0].path).toBe("/api/v1/approvals/ap1");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ decision: "approve" });
  });
});
```
(`recordingFetcher()` — returning `{ f, calls }` where `calls[i]` is `{ path, init }` — is an existing top-of-file helper in `endpoints.test.ts`, used by the Phase 8b `describe("resume tailoring", …)` block; the code above uses it exactly the same way.)

- [ ] **Step 5: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/api/endpoints.test.ts`
Expected: all PASS.

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/lib/query.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(applications-fe): Application/Approval types + endpoints + query keys"
```

---

## Task 2: `usePrepareRunEvents` hook

**Files:** Create `frontend/hooks/usePrepareRunEvents.ts`, `frontend/tests/applications/use-prepare-run-events.test.ts`.

**Interfaces:**
- Consumes: `AgentStep` (from `@/hooks/useAgentStream`), `authedStream` from `useAuth()`.
- Produces: `usePrepareRunEvents(sessionId: string | null, runId: string | null) -> { steps: AgentStep[]; status: "idle"|"streaming"|"awaiting_approval"|"done"|"error"; approvalId: string | null; error: string | null }`.

- [ ] **Step 1: `hooks/usePrepareRunEvents.ts`** — this is `hooks/useTailorRunEvents.ts` with: no `blocks` (not needed — spec R4), an `approvalId` field, and an `approval`-event branch. Read `useTailorRunEvents.ts` and adapt:
```typescript
"use client";

import { useEffect, useState } from "react";

import type { AgentStep } from "@/hooks/useAgentStream";
import { useAuth } from "@/providers/AuthProvider";

export interface PrepareRunState {
  steps: AgentStep[];
  status: "idle" | "streaming" | "awaiting_approval" | "done" | "error";
  approvalId: string | null;
  error: string | null;
}

const INITIAL: PrepareRunState = {
  steps: [], status: "idle", approvalId: null, error: null,
};

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
 * Watches an in-flight `prepare_application` run
 * (`GET /ai/sessions/{sessionId}/events?run_id=...`). Single-attempt, no
 * reconnect — same rationale as `useTailorRunEvents` (the AI relay forwards
 * live Redis pub/sub with no replay). On the `approval` frame it stops
 * advancing and surfaces `status: "awaiting_approval"` + `approvalId`; the
 * caller then drives the approval + the post-approval poll (spec R2/R3).
 */
export function usePrepareRunEvents(
  sessionId: string | null,
  runId: string | null,
): PrepareRunState {
  const { authedStream } = useAuth();
  const [state, setState] = useState<PrepareRunState>(INITIAL);

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
            } else if (frame.event === "approval") {
              const id = frame.data.approval_id;
              setState((s) => ({
                ...s,
                status: "awaiting_approval",
                approvalId: typeof id === "string" ? id : null,
              }));
            } else if (frame.event === "error") {
              setState((s) => ({
                ...s,
                status: "error",
                error: String(frame.data.message ?? "The run failed."),
              }));
            } else if (frame.event === "done") {
              setState((s) =>
                s.status === "error" || s.status === "awaiting_approval"
                  ? s
                  : { ...s, status: "done" },
              );
            }
          }
        }
        if (!cancelled) {
          setState((s) =>
            s.status === "streaming"
              ? { ...s, status: "error", error: "Lost the connection to this run." }
              : s,
          );
        }
      } catch {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            status: "error",
            error: "Lost the connection to this run.",
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
Note the `done` handler: a `prepare_application` run's pause emits `approval` **then** `done` (`status: "awaiting_approval"` in the `done` frame — Phase 10a `_drive`), so `done` must NOT overwrite an already-set `awaiting_approval` back to `done`; the guard `s.status === "awaiting_approval" ? s : …` handles that.

- [ ] **Step 2: `tests/applications/use-prepare-run-events.test.ts`** — mirror `tests/resume/use-tailor-run-events.test.ts`'s `streamOf`/`wrap` helpers exactly:
```typescript
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { usePrepareRunEvents } from "@/hooks/usePrepareRunEvents";

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

describe("usePrepareRunEvents", () => {
  it("accumulates steps then surfaces awaiting_approval with the approval id", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: step\ndata: {"event":"step","node":"cover_letter","status":"ok","summary":"Wrote a cover letter"}\n\n`,
        `event: step\ndata: {"event":"step","node":"application_prep","status":"ok","summary":"Ready for review"}\n\n`,
        `event: approval\ndata: {"event":"approval","approval_id":"ap-1"}\n\n`,
        `event: done\ndata: {"event":"done","status":"awaiting_approval","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => usePrepareRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("awaiting_approval"));
    expect(result.current.approvalId).toBe("ap-1");
    expect(result.current.steps.map((s) => s.node)).toEqual([
      "cover_letter", "application_prep",
    ]);
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"event":"error","message":"The run failed."}\n\n`]),
    );
    const { result } = renderHook(() => usePrepareRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("The run failed.");
  });

  it("reaches done for a run that completes without a pause", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: step\ndata: {"event":"step","node":"respond","status":"ok","summary":"done"}\n\n`,
        `event: done\ndata: {"event":"done","status":"completed","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => usePrepareRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("done"));
  });

  it("is inert with a null sessionId or runId", () => {
    const authedStream = vi.fn();
    const { result } = renderHook(() => usePrepareRunEvents(null, null), {
      wrapper: wrap(authedStream),
    });
    expect(authedStream).not.toHaveBeenCalled();
    expect(result.current).toEqual({
      steps: [], status: "idle", approvalId: null, error: null,
    });
  });
});
```

- [ ] **Step 3: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/use-prepare-run-events.test.ts`
Expected: all PASS.

```bash
git add frontend/hooks/usePrepareRunEvents.ts frontend/tests/applications/use-prepare-run-events.test.ts
git commit -m "feat(applications-fe): usePrepareRunEvents -- SSE watch through the approval pause"
```

---

## Task 3: `<ApprovalCard>`

**Files:** Create `frontend/components/applications/ApprovalCard.tsx`, `frontend/tests/applications/approval-card.test.tsx`.

**Interfaces:**
- Consumes: `ApprovalPayloadSnapshot` (Task 1).
- Produces: `<ApprovalCard snapshot={ApprovalPayloadSnapshot} submitting={boolean} onApprove={() => void} onReject={() => void} />`.

- [ ] **Step 1: `components/applications/ApprovalCard.tsx`**
```tsx
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import type { ApprovalPayloadSnapshot } from "@/lib/api/types";

export function ApprovalCard({
  snapshot,
  submitting,
  onApprove,
  onReject,
}: {
  snapshot: ApprovalPayloadSnapshot;
  submitting: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const { job, cover_letter, email } = snapshot;
  return (
    <Card>
      <CardBody className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold text-text">
            Review your application for {job.title}
          </h2>
          {job.company ? (
            <p className="text-sm text-text-muted">{job.company}</p>
          ) : null}
        </div>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Cover letter</h3>
          <p className="whitespace-pre-line rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-sm text-text">
            {cover_letter.content || "—"}
          </p>
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Email</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-text-muted">To</dt>
            <dd className="text-text">{email.to_email || "—"}</dd>
            <dt className="text-text-muted">Subject</dt>
            <dd className="text-text">{email.subject || "—"}</dd>
          </dl>
          <p className="whitespace-pre-line rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-sm text-text">
            {email.body || "—"}
          </p>
        </section>

        <p className="text-sm font-medium text-text-muted">
          Nothing will be sent until you approve it.
        </p>

        <div className="flex items-center gap-3">
          <Button loading={submitting} onClick={onApprove}>
            Approve &amp; send
          </Button>
          <Button variant="outline" disabled={submitting} onClick={onReject}>
            Don&apos;t send
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
```

- [ ] **Step 2: `tests/applications/approval-card.test.tsx`**
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApprovalCard } from "@/components/applications/ApprovalCard";
import type { ApprovalPayloadSnapshot } from "@/lib/api/types";

const snapshot: ApprovalPayloadSnapshot = {
  job: { title: "Staff Engineer", company: "Acme" },
  resume_version_id: "v1",
  cover_letter: { id: "cl1", content: "Dear Hiring Team,\n\nI'm excited to apply." },
  email: {
    id: "em1", to_email: "jobs@acme.com", to_name: null,
    subject: "Application: Staff Engineer", body: "Please find my materials attached.",
  },
};

describe("ApprovalCard", () => {
  it("renders the job, cover letter, email, and the safety line", () => {
    render(
      <ApprovalCard snapshot={snapshot} submitting={false} onApprove={vi.fn()} onReject={vi.fn()} />,
    );
    expect(screen.getByText("Review your application for Staff Engineer")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText(/I'm excited to apply/)).toBeInTheDocument();
    expect(screen.getByText("jobs@acme.com")).toBeInTheDocument();
    expect(screen.getByText("Application: Staff Engineer")).toBeInTheDocument();
    expect(
      screen.getByText("Nothing will be sent until you approve it."),
    ).toBeInTheDocument();
  });

  it("fires the callbacks and disables while submitting", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const { rerender } = render(
      <ApprovalCard snapshot={snapshot} submitting={false} onApprove={onApprove} onReject={onReject} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /approve & send/i }));
    expect(onApprove).toHaveBeenCalledOnce();

    rerender(
      <ApprovalCard snapshot={snapshot} submitting onApprove={onApprove} onReject={onReject} />,
    );
    expect(screen.getByRole("button", { name: /don't send/i })).toBeDisabled();
  });
});
```

- [ ] **Step 3: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/approval-card.test.tsx`
Expected: all PASS.

```bash
git add frontend/components/applications/ApprovalCard.tsx frontend/tests/applications/approval-card.test.tsx
git commit -m "feat(applications-fe): ApprovalCard -- the exact preview + approve/reject"
```

---

## Task 4: `<PrepareApplicationBuilder>`

**Files:** Create `frontend/components/applications/PrepareApplicationBuilder.tsx`, `frontend/tests/applications/prepare-builder.test.tsx`.

**Interfaces:**
- Consumes: `api.applications.create/get`, `api.approvals.get/decide` (Task 1), `usePrepareRunEvents` (Task 2), `<ApprovalCard>` (Task 3), `qk.approval`/`qk.application` (Task 1).
- Produces: `<PrepareApplicationBuilder jobId={string} />`.

- [ ] **Step 1: `components/applications/PrepareApplicationBuilder.tsx`**
```tsx
"use client";

import { useState } from "react";

import Link from "next/link";

import { useMutation, useQuery } from "@tanstack/react-query";

import { ApprovalCard } from "@/components/applications/ApprovalCard";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import { usePrepareRunEvents } from "@/hooks/usePrepareRunEvents";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const STEP_LABEL: Record<string, string> = {
  resume_tailoring: "Tailoring your résumé",
  claim_validator: "Checking every claim is grounded",
  cover_letter: "Writing your cover letter",
  letter_claim_validator: "Checking the cover letter",
  email_draft: "Drafting your email",
  application_prep: "Getting it ready for your review",
};

export function PrepareApplicationBuilder({ jobId }: { jobId: string }) {
  const { api } = useAuth();
  const { toast } = useToast();
  const [attempt, setAttempt] = useState(0);
  const [run, setRun] = useState<{ sessionId: string; runId: string } | null>(null);
  const [decided, setDecided] = useState<"approve" | "reject" | null>(null);

  const startMut = useMutation({
    mutationFn: () => api.applications.create({ job_id: jobId }),
    onSuccess: (ref) => setRun({ sessionId: ref.session_id, runId: ref.run_id }),
    onError: () => toast({ title: "Couldn't start preparing this application.", variant: "danger" }),
  });

  const ev = usePrepareRunEvents(run?.sessionId ?? null, run?.runId ?? null);

  const approvalQuery = useQuery({
    queryKey: qk.approval(ev.approvalId ?? ""),
    queryFn: () => api.approvals.get(ev.approvalId as string),
    enabled: ev.status === "awaiting_approval" && ev.approvalId != null,
  });
  const applicationId = approvalQuery.data?.application_id ?? null;

  const decideMut = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      api.approvals.decide(ev.approvalId as string, { decision }),
    onSuccess: (_v, decision) => setDecided(decision),
    onError: () => toast({ title: "Couldn't record your decision.", variant: "danger" }),
  });

  const applicationQuery = useQuery({
    queryKey: qk.application(applicationId ?? ""),
    queryFn: () => api.applications.get(applicationId as string),
    enabled: decided === "approve" && applicationId != null,
    refetchInterval: (q) =>
      q.state.data && q.state.data.status !== "awaiting_approval" ? false : 2000,
  });

  function startOver() {
    setRun(null);
    setDecided(null);
    setAttempt((a) => a + 1);
  }

  // --- not started ---
  if (!run) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-text-muted">
          Mana AI will tailor your résumé, write a cover letter, and draft an email —
          then stop and show you everything before anything is sent.
        </p>
        <Button loading={startMut.isPending} onClick={() => startMut.mutate()}>
          Prepare application
        </Button>
      </div>
    );
  }

  // --- terminal: rejected ---
  if (decided === "reject") {
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p className="text-sm text-text">You didn&apos;t approve this application — nothing was sent.</p>
          <Link href={`/jobs/${jobId}`} className="text-sm font-medium text-accent underline-offset-4 hover:underline">
            Back to the job
          </Link>
        </CardBody>
      </Card>
    );
  }

  // --- terminal: sent ---
  if (decided === "approve" && applicationQuery.data?.status === "applied") {
    const at = applicationQuery.data.applied_at;
    return (
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p className="text-sm font-medium text-positive">
            Application sent{at ? ` at ${new Date(at).toLocaleTimeString()}` : ""}.
          </p>
          <Link href={`/jobs/${jobId}`} className="text-sm font-medium text-accent underline-offset-4 hover:underline">
            Back to the job
          </Link>
        </CardBody>
      </Card>
    );
  }

  // --- sending (approved, polling) ---
  if (decided === "approve") {
    return (
      <Card>
        <CardBody className="flex items-center gap-2">
          <Spinner size="sm" />
          <p className="text-sm text-text-muted">Sending your application…</p>
        </CardBody>
      </Card>
    );
  }

  // --- error ---
  if (ev.status === "error") {
    return <ErrorState title={ev.error ?? "Something went wrong."} onRetry={startOver} />;
  }

  // --- awaiting approval ---
  if (ev.status === "awaiting_approval") {
    if (approvalQuery.isPending) return <Skeleton className="h-64 w-full" />;
    if (approvalQuery.isError || !approvalQuery.data) {
      return <ErrorState onRetry={() => void approvalQuery.refetch()} />;
    }
    return (
      <div key={attempt}>
        <ApprovalCard
          snapshot={approvalQuery.data.payload_snapshot}
          submitting={decideMut.isPending}
          onApprove={() => decideMut.mutate("approve")}
          onReject={() => decideMut.mutate("reject")}
        />
      </div>
    );
  }

  // --- streaming progress ---
  const last = ev.steps.at(-1);
  return (
    <Card>
      <CardBody className="flex items-center gap-2">
        <Spinner size="sm" />
        <p className="text-sm text-text-muted">
          {last ? (STEP_LABEL[last.node] ?? last.summary) : "Starting…"}
        </p>
      </CardBody>
    </Card>
  );
}
```

(`ErrorState`'s real props — confirmed — are `{ title?: string; onRetry?: () => void }`; `title` renders as the prominent line, so passing `ev.error` there is correct. `Spinner` from `@/components/ui/spinner` and `Skeleton` from `@/components/ui/skeleton` are both real, as used across the resume/jobs pages.)

- [ ] **Step 2: `tests/applications/prepare-builder.test.tsx`**
```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PrepareApplicationBuilder } from "@/components/applications/PrepareApplicationBuilder";
import { renderWithProviders } from "@/test/utils";

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

const snapshot = {
  job: { title: "Staff Engineer", company: "Acme" },
  resume_version_id: "v1",
  cover_letter: { id: "cl1", content: "Dear Hiring Team," },
  email: { id: "em1", to_email: "jobs@acme.com", to_name: null, subject: "Application", body: "Hi." },
};

describe("PrepareApplicationBuilder", () => {
  it("start → stream → approval card → approve → sent", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: step\ndata: {"event":"step","node":"cover_letter","status":"ok","summary":"wrote letter"}\n\n`,
        `event: approval\ndata: {"event":"approval","approval_id":"ap-1"}\n\n`,
        `event: done\ndata: {"event":"done","status":"awaiting_approval","totals":{}}\n\n`,
      ]),
    );
    let appStatus = "awaiting_approval";
    renderWithProviders(<PrepareApplicationBuilder jobId="j1" />, {
      authValue: { authedStream },
      api: {
        applications: {
          create: vi.fn(async () => ({ run_id: "r1", session_id: "s1" })),
          get: vi.fn(async () => ({
            id: "a1", job_id: "j1", status: appStatus, applied_at:
              appStatus === "applied" ? "2026-09-06T10:42:00Z" : null,
          })),
        },
        approvals: {
          get: vi.fn(async () => ({
            id: "ap-1", application_id: "a1", action_type: "send_application_email",
            payload_snapshot: snapshot, status: "pending", decided_at: null,
            decision_note: null, created_at: "2026-09-06T10:00:00Z",
          })),
          decide: vi.fn(async () => {
            appStatus = "applied";
          }),
        },
      },
    });

    await userEvent.click(await screen.findByRole("button", { name: /prepare application/i }));
    expect(
      await screen.findByText("Review your application for Staff Engineer"),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /approve & send/i }));
    await waitFor(
      () => expect(screen.getByText(/Application sent/)).toBeInTheDocument(),
      { timeout: 4000 },
    );
  });

  it("reject → terminal 'not sent' state", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: approval\ndata: {"event":"approval","approval_id":"ap-2"}\n\n`,
        `event: done\ndata: {"event":"done","status":"awaiting_approval","totals":{}}\n\n`,
      ]),
    );
    renderWithProviders(<PrepareApplicationBuilder jobId="j2" />, {
      authValue: { authedStream },
      api: {
        applications: { create: vi.fn(async () => ({ run_id: "r2", session_id: "s2" })), get: vi.fn() },
        approvals: {
          get: vi.fn(async () => ({
            id: "ap-2", application_id: "a2", action_type: "send_application_email",
            payload_snapshot: snapshot, status: "pending", decided_at: null,
            decision_note: null, created_at: "2026-09-06T10:00:00Z",
          })),
          decide: vi.fn(async () => {}),
        },
      },
    });
    await userEvent.click(await screen.findByRole("button", { name: /prepare application/i }));
    await userEvent.click(await screen.findByRole("button", { name: /don't send/i }));
    expect(await screen.findByText(/didn't approve this application/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/prepare-builder.test.tsx`
Expected: all PASS.

```bash
git add frontend/components/applications/PrepareApplicationBuilder.tsx frontend/tests/applications/prepare-builder.test.tsx
git commit -m "feat(applications-fe): PrepareApplicationBuilder -- start, stream, approve/reject, send"
```

---

## Task 5: the route page + Job Detail entry

**Files:** Create `frontend/app/(app)/applications/new/[jobId]/page.tsx`. Modify `frontend/app/(app)/jobs/[id]/page.tsx`.

**Interfaces:**
- Consumes: `<PrepareApplicationBuilder>` (Task 4).

- [ ] **Step 1: `app/(app)/applications/new/[jobId]/page.tsx`**
```tsx
"use client";

import { useParams } from "next/navigation";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { PrepareApplicationBuilder } from "@/components/applications/PrepareApplicationBuilder";

export default function PrepareApplicationPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId ?? "";

  return (
    <RequireAuth>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-text">Prepare application</h1>
          <p className="text-sm text-text-muted">
            You review and approve everything before anything is sent.
          </p>
        </header>
        <PrepareApplicationBuilder jobId={jobId} />
      </div>
    </RequireAuth>
  );
}
```

- [ ] **Step 2: `app/(app)/jobs/[id]/page.tsx`** — two import changes (confirmed against the current file): the line `import { Button } from "@/components/ui/button";` becomes `import { Button, buttonVariants } from "@/components/ui/button";`, and add a new `import Link from "next/link";` (this file does NOT currently import `Link` — put it in the `next/...` import group near the top, e.g. right after the `next/navigation` line). Then, right after `<TailorButton jobId={id} />` (currently line ~161):
```tsx
      <Link href={`/applications/new/${id}`} className={buttonVariants({ variant: "default" })}>
        Prepare application
      </Link>
```

- [ ] **Step 3: `tests/applications/prepare-page.test.tsx`** (small — the page is a thin shell; per RULING R11 `useParams` stays `() => ({})` so `jobId === ""`, and `PrepareApplicationBuilder`'s `create` mock ignores its argument):
```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import PrepareApplicationPage from "@/app/(app)/applications/new/[jobId]/page";

describe("PrepareApplicationPage", () => {
  it("renders the header and the builder's start button", async () => {
    renderWithProviders(<PrepareApplicationPage />, {
      api: { applications: { create: vi.fn(), get: vi.fn() }, approvals: { get: vi.fn(), decide: vi.fn() } },
    });
    expect(screen.getByRole("heading", { name: "Prepare application" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /prepare application/i }),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/prepare-page.test.tsx tests/jobs/job-detail-page.test.tsx`
Expected: all PASS (including the pre-existing job-detail-page suite — confirm the new `<Link>` didn't break it).

```bash
git add "frontend/app/(app)/applications/new/[jobId]/page.tsx" "frontend/app/(app)/jobs/[id]/page.tsx" frontend/tests/applications/prepare-page.test.tsx
git commit -m "feat(applications-fe): /applications/new/[jobId] Builder route + Job Detail entry"
```

---

## Final gate (whole branch)

From `frontend/`: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run`
Expected: all PASS, no new failures in any pre-existing suite.

Then: whole-branch review (inline — all-frontend), squash/fast-forward to `main`, push, watch CI, `finishing-a-development-branch`.

---

## Completion report

**Status: shipped.** 5 tasks via subagent-driven-development (fresh Sonnet implementer per task, inline controller review for all — lean policy, all-frontend), on branch `phase-10b-human-approval-frontend` off `main@c3b9fcb`, fast-forwarded (5 clean task commits, `ad43865`..`b83b23d`).

**What changed:** the "Prepare application" flow. `Application`/`ApprovalRequest`/`ApprovalPayloadSnapshot`/`ApprovalDecision` types + `api.applications.create/get` + `api.approvals.list/get/decide` + `qk.application/approval/approvals`. `usePrepareRunEvents` — `useTailorRunEvents` plus an `approval`-frame branch (`status: "awaiting_approval"`, `approvalId`) and a `done`-handler that won't clobber an already-set pause. `<ApprovalCard>` — the exact preview (role, company, full cover letter, email to/subject/body) with the mandated line "Nothing will be sent until you approve it." `<PrepareApplicationBuilder>` — start (`POST /applications`) → SSE step-progress checklist → on the `approval` frame, `GET /approvals/{id}` → `<ApprovalCard>` → `POST /approvals/{id}` → **poll** `GET /applications/{id}` (`refetchInterval` while `status === "awaiting_approval"`) → "Application sent at HH:MM" / "you didn't approve this" / error-with-start-over. A new `applications/new/[jobId]` route hosts it; Job Detail gets a "Prepare application" link-button after `<TailorButton>`. 13 files, +760/-1.

**Key rulings (spec R1-R7):** dedicated hook (not a shared one — repo convention); the post-approval "sending" phase **polls** `GET /applications/{id}` rather than re-watching the no-replay SSE channel (a race in the ~1s `_defer_by` window); the Builder learns `application_id` from `GET /approvals/{id}` (the `approval` SSE frame carries only `{approval_id}`); no block rendering (`respond` emits a block only on the completed path, never during the pause); the Builder is its own `applications/new/[jobId]` route (the master's `applications/[id]/prepare` can't be the entry — no id yet); reject and error are terminal on the page (no revise loop — backend `reject` is terminal from Phase 10a).

**Regression check:** `pnpm lint` + `pnpm exec tsc --noEmit` clean at every task boundary and on final `main`. Frontend test count: 151 (baseline at `c3b9fcb`, verified in a worktree) → 166 (branch tip), across 47 → 51 files. No pre-existing suite broken (the `job-detail-page` suite still green after the new `<Link>`).

**CI:** pending — watched to green as part of this closeout.

**Not verified here:** the full run→pause→approve→send round trip end to end against a live backend (each piece is unit-tested with mocked `api` + a scripted SSE stream; the real integration is proven by Phase 10a's DB-gated `test_resume_agent.py` on the backend side). Everything Phase 11 owns (the Kanban tracker, `applications` list/detail/timeline/notes) remains untouched.
