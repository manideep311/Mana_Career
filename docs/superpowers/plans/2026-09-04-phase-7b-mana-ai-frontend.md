# Phase 7b — Mana AI agent frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Mana AI agent's frontend — a right-docked chat panel that streams the `understand_job` run and renders its response blocks, plus an AI Activity feed page.

**Architecture:** A `ManaPanelDock` mounted in `AppShell` bootstraps an `AiSession`, POSTs a message to the streaming `/ai/sessions/{id}/messages` endpoint, and consumes the SSE with a `useAgentStream` hook (mirrors `useJobEvents`). Assistant response blocks are rendered through a `kind → component` registry. A separate `/activity` route lists `AiAction` rows grouped by session.

**Tech Stack:** Next.js 15 app router, React 19, TanStack Query v5, Tailwind v4 (semantic tokens), vitest + Testing Library, pnpm.

**Spec:** `docs/superpowers/specs/2026-09-03-phase-7-mana-ai-agent.md` §6 (Phase 7b summary) — executors read both.

## Global Constraints

- **Package manager is pnpm.** CI frontend gates (run from `frontend/`): `pnpm lint` → `pnpm exec tsc --noEmit` → `pnpm test run`. All three must pass. Local: same commands (`pnpm` is on PATH, v11).
- `tsconfig` is `strict: true`, `noEmit`, `moduleResolution: bundler`, path alias `@/* → ./*`. ESLint extends `next/core-web-vitals`.
- **Semantic color tokens only** — `bg-surface`, `bg-surface-sunk`, `text-text`, `text-text-muted`, `text-text-subtle`, `bg-accent-soft`, `text-accent`, `bg-positive-soft`, `text-positive`, `bg-warning-soft`, `text-warning`, `bg-danger-soft`, `text-danger`, `border-border`, `rounded-[var(--radius)]`. No raw hex, no Tailwind color literals (`bg-blue-500` etc.).
- Client components start with `"use client";`. Data comes from `useAuth().api` + `useQuery`/`useMutation` with keys from `lib/query.ts`'s `qk`.
- Streaming endpoints bypass `makeApi` — the hook calls `useAuth().authedStream(path, init)` directly (established by `hooks/useJobEvents.ts` / `hooks/useResumeEvents.ts`). `authedStream` passes `init` straight to `fetch`, so `method: "POST"` + a JSON `body` work.
- SSE frame parsing: split the decoded buffer on `/\r\n\r\n|\n\n/`; per frame read `event:` and `data:` lines (`:` prefix = keepalive comment, skip); `data` is JSON. Copy `parseFrame` verbatim from `hooks/useJobEvents.ts`.
- Tests use `renderWithProviders(ui, { api, authValue, route })` and `makeAuthValue` from `@/test/utils`; a canned SSE body is a `new Response(new ReadableStream({...}), { status: 200 })` — copy `streamOf(frames)` from `tests/resume/use-resume-events.test.ts`.
- New nav entry uses a `lucide-react` icon already importable there (`Activity`).
- Backend contract (Phase 7a, already on `main`):
  - `POST /api/v1/ai/sessions {kind?, context?}` → 201 `SessionOut`.
  - `GET /api/v1/ai/sessions?limit&offset` → `{ items: SessionSummary[], total }`.
  - `GET /api/v1/ai/sessions/{id}` → `SessionOut` (with `messages`).
  - `POST /api/v1/ai/sessions/{id}/messages {content}` → **SSE stream** (`text/event-stream`). Frames: `open {run_id}`, `step {node,status,summary}`, `block {block}`, `error {message}`, `done {status,totals}`.
  - `POST /api/v1/ai/sessions/{id}/goal {goal,inputs}` → 202 `{run_id}`.
  - `POST /api/v1/ai/sessions/{id}/stop` → 202.
  - `GET /api/v1/ai/actions?session_id&limit&offset` → `{ items: AiAction[], total }`.
  - `SessionOut`: `{ id, kind, goal, title, status, run_id, totals, error, created_at, started_at, ended_at, messages }`. `SessionSummary` = same minus `messages`.
  - `Message`: `{ id, role, content, blocks, created_at }`.
  - `AiAction`: `{ id, ai_session_id, run_id, node, action_key, summary, status, entity_type, entity_id, occurred_at }`.
  - Response block shapes: `{kind:"text", markdown}`, `{kind:"job_card", job_id, match_id|null}`, `{kind:"insufficient_info", topic, missing[]}`; stub kinds (`match_score`/`skill_gap`/`career_recommendation`/`learning_recommendation`/`resume_suggestion`/`application_draft`/`approval_action`) carry a single id field and get a muted fallback for now.
- Out of scope: the `prepare_application` UI, `/approvals`, real markdown rendering (plain-paragraph split is fine), reconnect UX beyond what `useJobEvents` already does.

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `lib/api/types.ts` | Modify | + `AgentGoal`, `AiSessionStatus`, `MessageRole`, block interfaces, `ResponseBlock` union, `Message`, `AiSession`, `AiSessionSummary`, `AiSessionList`, `AiAction`, `AiActionList`, `RunRef` |
| `lib/api/endpoints.ts` | Modify | + `ai` group (6 JSON methods; no `sendMessage` — streaming bypasses `makeApi`) |
| `lib/query.ts` | Modify | + `qk.aiSessions`, `qk.aiSession(id)`, `qk.aiActions(q)` |
| `hooks/useAgentStream.ts` | Create | POST a message, consume the SSE, expose `{ blocks, steps, status, error, streaming, send }` |
| `components/ai/blocks/TextBlockView.tsx` | Create | render a `TextBlock` (paragraph split) |
| `components/ai/blocks/JobCardBlockView.tsx` | Create | `useQuery(qk.job)` → `<JobCard>`; when `match_id`, poll `qk.match` until `ready`/`failed` and thread the score in |
| `components/ai/blocks/InsufficientInfoBlockView.tsx` | Create | "not enough info yet" card + the `missing` list |
| `components/ai/blocks/block-registry.tsx` | Create | `kind → component` map + `<BlockView block={...}/>`; unknown kind → muted fallback |
| `components/ai/ManaPanelDock.tsx` | Create | right-docked collapsible panel: session bootstrap, message list, composer, suggested-prompt chip, streaming |
| `components/layout/AppShell.tsx` | Modify | mount `<ManaPanelDock/>` |
| `components/layout/nav-items.ts` | Modify | + `{ href: "/activity", label: "Activity", icon: Activity, ready: true }` |
| `app/(app)/activity/page.tsx` | Create | AI Activity feed grouped by session |
| `tests/api/endpoints.test.ts` | Modify | + assertions for each `ai` method |
| `tests/ai/use-agent-stream.test.ts` | Create | canned SSE → blocks/steps/status accumulate; error frame; done |
| `tests/ai/block-registry.test.tsx` | Create | each kind renders; unknown → fallback; job card shows the job title + score |
| `tests/ai/mana-panel.test.tsx` | Create | open panel → send the suggested prompt → a text block + a job card render |
| `tests/ai/activity-page.test.tsx` | Create | rows grouped by session, status pills, "Try again" re-runs the goal |

---

## Task 1: types + `api.ai` + query keys

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/api/endpoints.ts`
- Modify: `frontend/lib/query.ts`
- Test: `frontend/tests/api/endpoints.test.ts`

**Interfaces:**
- Consumes: existing `types.ts` exports (`JobCard`, `MatchStatus`), the `makeApi`/`json` pattern in `endpoints.ts`, the `qk` object.
- Produces:
  - `AgentGoal = "understand_job" | "enrich_job" | "analyze_profile" | "prepare_application"`
  - `AiSessionStatus = "idle" | "running" | "awaiting_approval" | "completed" | "rejected" | "halted" | "error"`
  - `MessageRole = "user" | "assistant" | "tool" | "system"`
  - `TextBlock`, `JobCardBlock`, `InsufficientInfoBlock`, `StubBlock`, `ResponseBlock`
  - `Message`, `AiSession`, `AiSessionSummary`, `AiSessionList`, `AiAction`, `AiActionList`, `RunRef`
  - `api.ai`: `createSession(body?) → AiSession`, `listSessions(q?) → AiSessionList`, `getSession(id) → AiSession`, `startGoal(id, body) → RunRef`, `stopRun(id) → void`, `listActions(q?) → AiActionList`
  - `qk.aiSessions`, `qk.aiSession(id)`, `qk.aiActions(q)`

- [ ] **Step 1: Add types to `lib/api/types.ts`** (append a new section at the end)

```ts
/* -------------------------------------------------------------------------- */
/*  Mana AI agent (Phase 7)                                                    */
/* -------------------------------------------------------------------------- */

export type AgentGoal =
  | "understand_job"
  | "enrich_job"
  | "analyze_profile"
  | "prepare_application";

export type AiSessionStatus =
  | "idle"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "rejected"
  | "halted"
  | "error";

export type MessageRole = "user" | "assistant" | "tool" | "system";

export interface TextBlock {
  kind: "text";
  markdown: string;
}
export interface JobCardBlock {
  kind: "job_card";
  job_id: string;
  match_id: string | null;
}
export interface InsufficientInfoBlock {
  kind: "insufficient_info";
  topic: string;
  missing: string[];
}
/** Declared-but-unrendered block kinds (Phases 8–12) — the registry shows a muted fallback. */
export interface StubBlock {
  kind:
    | "match_score"
    | "skill_gap"
    | "career_recommendation"
    | "learning_recommendation"
    | "resume_suggestion"
    | "application_draft"
    | "approval_action";
  [field: string]: unknown;
}
export type ResponseBlock =
  | TextBlock
  | JobCardBlock
  | InsufficientInfoBlock
  | StubBlock;

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  blocks: ResponseBlock[];
  created_at: string;
}
export interface AiSessionSummary {
  id: string;
  kind: "chat" | "agent_run";
  goal: string | null;
  title: string | null;
  status: AiSessionStatus;
  run_id: string | null;
  totals: Record<string, unknown>;
  error: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
}
export interface AiSession extends AiSessionSummary {
  messages: Message[];
}
export interface AiSessionList {
  items: AiSessionSummary[];
  total: number;
}
export interface AiAction {
  id: string;
  ai_session_id: string | null;
  run_id: string | null;
  node: string;
  action_key: string;
  summary: string;
  status: "ok" | "warning" | "error";
  entity_type: string | null;
  entity_id: string | null;
  occurred_at: string;
}
export interface AiActionList {
  items: AiAction[];
  total: number;
}
export interface RunRef {
  run_id: string;
}
```

- [ ] **Step 2: Add the `ai` group to `lib/api/endpoints.ts`**

Add the imports to the top `import { ... } from "@/lib/api/types"` block: `AiAction`, `AiActionList`, `AiSession`, `AiSessionList`, `AgentGoal`, `RunRef`.

Add this group after `eval:` inside the object returned by `makeApi` (mind the trailing comma):

```ts
    ai: {
      async createSession(body: { kind?: "chat" | "agent_run"; context?: Record<string, unknown> } = {}) {
        return f<AiSession>("/api/v1/ai/sessions", json("POST", body));
      },
      async listSessions(query: { limit?: number; offset?: number } = {}) {
        const qs = new URLSearchParams(
          Object.entries(query).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
        ).toString();
        return f<AiSessionList>(`/api/v1/ai/sessions${qs ? `?${qs}` : ""}`);
      },
      async getSession(id: string) {
        return f<AiSession>(`/api/v1/ai/sessions/${id}`);
      },
      async startGoal(id: string, body: { goal: AgentGoal; inputs?: Record<string, unknown> }) {
        return f<RunRef>(`/api/v1/ai/sessions/${id}/goal`, json("POST", { inputs: {}, ...body }));
      },
      async stopRun(id: string) {
        return f<void>(`/api/v1/ai/sessions/${id}/stop`, { method: "POST" });
      },
      async listActions(query: { session_id?: string; limit?: number; offset?: number } = {}) {
        const qs = new URLSearchParams(
          Object.entries(query).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
        ).toString();
        return f<AiActionList>(`/api/v1/ai/actions${qs ? `?${qs}` : ""}`);
      },
    },
```

- [ ] **Step 3: Add query keys to `lib/query.ts`** (append inside the `qk` object)

```ts
  aiSessions: ["ai", "sessions"] as const,
  aiSession: (id: string) => ["ai", "session", id] as const,
  aiActions: (q: Record<string, unknown>) => ["ai", "actions", q] as const,
```

- [ ] **Step 4: Extend `tests/api/endpoints.test.ts`** — add a `describe("ai", ...)` block

```ts
describe("ai", () => {
  it("creates a session with a JSON body", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.createSession({ kind: "chat" });
    expect(calls[0].path).toBe("/api/v1/ai/sessions");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ kind: "chat" });
  });

  it("lists sessions with query params", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.listSessions({ limit: 20, offset: 0 });
    expect(calls[0].path).toBe("/api/v1/ai/sessions?limit=20&offset=0");
  });

  it("startGoal always sends an inputs object", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.startGoal("s1", { goal: "understand_job" });
    expect(calls[0].path).toBe("/api/v1/ai/sessions/s1/goal");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ inputs: {}, goal: "understand_job" });
  });

  it("stopRun posts with no body", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.stopRun("s1");
    expect(calls[0].path).toBe("/api/v1/ai/sessions/s1/stop");
    expect(calls[0].init?.method).toBe("POST");
  });

  it("listActions filters by session", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.listActions({ session_id: "s1" });
    expect(calls[0].path).toBe("/api/v1/ai/actions?session_id=s1");
  });
});
```

- [ ] **Step 5: Gates** — from `frontend/`: `pnpm exec tsc --noEmit && pnpm exec eslint lib/api/endpoints.ts lib/api/types.ts lib/query.ts && pnpm exec vitest run tests/api/endpoints.test.ts`. Expected: tsc clean; eslint clean; endpoints tests pass (old + 5 new).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/lib/query.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(ai-fe): AI agent types, api.ai endpoint group, query keys"
```

---

## Task 2: `useAgentStream` hook

**Files:**
- Create: `frontend/hooks/useAgentStream.ts`
- Test: `frontend/tests/ai/use-agent-stream.test.ts`

**Interfaces:**
- Consumes: `useAuth().authedStream`; `ResponseBlock`, `AiSessionStatus` from `types.ts`.
- Produces:
  - `interface AgentStep { node: string; status: string; summary: string }`
  - `interface AgentStreamState { blocks: ResponseBlock[]; steps: AgentStep[]; status: "idle" | "streaming" | "done" | "error"; error: string | null }`
  - `function useAgentStream(sessionId: string | null): AgentStreamState & { send: (content: string) => void; reset: () => void }`
  - `send(content)` POSTs `{content}` to `/api/v1/ai/sessions/{sessionId}/messages` with `Accept: text/event-stream`, then reads the SSE: `block` frames push to `blocks`, `step` frames push to `steps`, `error` sets `error` + status `"error"`, `done` sets status `"done"`. A network throw → status `"error"`, `error = "Lost the connection."`. No auto-reconnect (a completed run has nothing to resume).

- [ ] **Step 1: Write `tests/ai/use-agent-stream.test.ts`**

```ts
import { renderHook, waitFor, act } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { useAgentStream } from "@/hooks/useAgentStream";

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

describe("useAgentStream", () => {
  it("accumulates step and block frames then marks done", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: open\ndata: {"event":"open","run_id":"r1"}\n\n`,
        `event: step\ndata: {"event":"step","node":"job_retrieval","status":"ok","summary":"Found 3 candidate roles"}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"text","markdown":"Here are 3 roles."}}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"job_card","job_id":"j1","match_id":null}}\n\n`,
        `event: done\ndata: {"event":"done","status":"completed","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useAgentStream("s1"), { wrapper: wrap(authedStream) });
    act(() => result.current.send("find jobs that match my experience"));
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.steps).toHaveLength(1);
    expect(result.current.blocks.map((b) => b.kind)).toEqual(["text", "job_card"]);
    expect(result.current.error).toBeNull();
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"event":"error","message":"The run failed."}\n\n`]),
    );
    const { result } = renderHook(() => useAgentStream("s1"), { wrapper: wrap(authedStream) });
    act(() => result.current.send("x"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("The run failed.");
  });

  it("is inert with a null session id", () => {
    const authedStream = vi.fn();
    const { result } = renderHook(() => useAgentStream(null), { wrapper: wrap(authedStream) });
    act(() => result.current.send("x"));
    expect(authedStream).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run — expect fail** (`useAgentStream` not found).

- [ ] **Step 3: Write `hooks/useAgentStream.ts`**

```ts
"use client";

import { useCallback, useRef, useState } from "react";

import type { ResponseBlock } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export interface AgentStep {
  node: string;
  status: string;
  summary: string;
}

export interface AgentStreamState {
  blocks: ResponseBlock[];
  steps: AgentStep[];
  status: "idle" | "streaming" | "done" | "error";
  error: string | null;
}

const INITIAL: AgentStreamState = { blocks: [], steps: [], status: "idle", error: null };

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

export function useAgentStream(
  sessionId: string | null,
): AgentStreamState & { send: (content: string) => void; reset: () => void } {
  const { authedStream } = useAuth();
  const [state, setState] = useState<AgentStreamState>(INITIAL);
  const runningRef = useRef(false);

  const reset = useCallback(() => setState(INITIAL), []);

  const send = useCallback(
    (content: string) => {
      if (!sessionId || runningRef.current) return;
      runningRef.current = true;
      setState({ ...INITIAL, status: "streaming" });

      void (async () => {
        try {
          const res = await authedStream(`/api/v1/ai/sessions/${sessionId}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify({ content }),
          });
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
              if (!frame) continue;
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
          setState((s) => (s.status === "streaming" ? { ...s, status: "done" } : s));
        } catch {
          setState((s) => ({ ...s, status: "error", error: "Lost the connection." }));
        } finally {
          runningRef.current = false;
        }
      })();
    },
    [sessionId, authedStream],
  );

  return { ...state, send, reset };
}
```

- [ ] **Step 4: Gates** — `pnpm exec tsc --noEmit && pnpm exec eslint hooks/useAgentStream.ts && pnpm exec vitest run tests/ai/use-agent-stream.test.ts`. Expected: clean; 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/hooks/useAgentStream.ts frontend/tests/ai/use-agent-stream.test.ts
git commit -m "feat(ai-fe): useAgentStream — POST a message, consume the SSE run"
```

---

## Task 3: block views + registry

**Files:**
- Create: `frontend/components/ai/blocks/TextBlockView.tsx`
- Create: `frontend/components/ai/blocks/JobCardBlockView.tsx`
- Create: `frontend/components/ai/blocks/InsufficientInfoBlockView.tsx`
- Create: `frontend/components/ai/blocks/block-registry.tsx`
- Test: `frontend/tests/ai/block-registry.test.tsx`

**Interfaces:**
- Consumes: `ResponseBlock`, `TextBlock`, `JobCardBlock`, `InsufficientInfoBlock`, `JobCard as JobCardT`, `JobMatch` from `types.ts`; `useAuth().api`; `qk.job`, `qk.match`; `<JobCard>` from `@/components/jobs/JobCard`.
- Produces:
  - `TextBlockView({ block: TextBlock })`
  - `JobCardBlockView({ block: JobCardBlock })`
  - `InsufficientInfoBlockView({ block: InsufficientInfoBlock })`
  - `block-registry.tsx`: `BlockView({ block: ResponseBlock })` — dispatches on `block.kind`; unknown/stub kinds → a muted `<p>`.

- [ ] **Step 1: Write `tests/ai/block-registry.test.tsx`**

```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BlockView } from "@/components/ai/blocks/block-registry";
import { renderWithProviders } from "@/test/utils";

const job = {
  id: "j1", title: "Staff Engineer", company: "Acme", location: "Remote",
  work_mode: "remote", seniority: "staff", employment_type: "full_time",
  salary_min: null, salary_max: null, salary_currency: null, salary_period: null,
  is_seed: false, status: "ready", posted_at: null, created_at: "2026-09-01T00:00:00Z",
  required_skills: [],
};

describe("BlockView", () => {
  it("renders a text block as paragraphs", () => {
    renderWithProviders(<BlockView block={{ kind: "text", markdown: "Line one.\n\nLine two." }} />);
    expect(screen.getByText("Line one.")).toBeInTheDocument();
    expect(screen.getByText("Line two.")).toBeInTheDocument();
  });

  it("renders a job_card block by fetching the job", async () => {
    renderWithProviders(
      <BlockView block={{ kind: "job_card", job_id: "j1", match_id: null }} />,
      { api: { jobs: { get: vi.fn(async () => job) }, matches: { get: vi.fn() } } },
    );
    expect(await screen.findByText("Staff Engineer")).toBeInTheDocument();
  });

  it("renders insufficient_info with the missing list", () => {
    renderWithProviders(
      <BlockView block={{ kind: "insufficient_info", topic: "job_match", missing: ["a job in your corpus", "a fuller profile"] }} />,
    );
    expect(screen.getByText(/a job in your corpus/)).toBeInTheDocument();
    expect(screen.getByText(/a fuller profile/)).toBeInTheDocument();
  });

  it("shows a muted fallback for an unknown kind", () => {
    renderWithProviders(<BlockView block={{ kind: "approval_action", approval_id: "a1" } as never} />);
    expect(screen.getByText(/not available yet/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Write `components/ai/blocks/TextBlockView.tsx`**

```tsx
import type { TextBlock } from "@/lib/api/types";

/** A plain-text assistant block. Paragraphs split on blank lines — no markdown engine yet. */
export function TextBlockView({ block }: { block: TextBlock }) {
  const paras = block.markdown.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  return (
    <div className="flex flex-col gap-2 text-sm text-text">
      {paras.map((p, i) => (
        <p key={i}>{p}</p>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Write `components/ai/blocks/JobCardBlockView.tsx`**

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";

import { JobCard } from "@/components/jobs/JobCard";
import { Spinner } from "@/components/ui/spinner";
import type { JobCard as JobCardT, JobCardBlock } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Fetches the referenced job and renders the standard `<JobCard>`. When the
 * block carries a `match_id`, the match is polled until it settles and the
 * score/band/status are threaded onto the card (mirrors the discovery grid).
 */
export function JobCardBlockView({ block }: { block: JobCardBlock }) {
  const { api } = useAuth();

  const jobQuery = useQuery({
    queryKey: qk.job(block.job_id),
    queryFn: () => api.jobs.get(block.job_id),
  });

  const matchQuery = useQuery({
    queryKey: qk.match(block.job_id),
    queryFn: () => api.matches.get(block.match_id as string),
    enabled: block.match_id != null,
    refetchInterval: (q) =>
      q.state.data && q.state.data.status === "scoring" ? 2000 : false,
  });

  if (jobQuery.isPending) {
    return (
      <div className="flex justify-center rounded-[var(--radius)] border border-border bg-surface p-4 text-text-muted">
        <Spinner size="sm" />
      </div>
    );
  }
  if (jobQuery.isError) {
    return (
      <p className="rounded-[var(--radius)] border border-border bg-surface p-3 text-sm text-text-muted">
        Couldn’t load this role.
      </p>
    );
  }

  const m = matchQuery.data;
  const job: JobCardT = {
    ...jobQuery.data,
    match_score: m?.score ?? jobQuery.data.match_score,
    match_band: m?.band ?? jobQuery.data.match_band,
    match_status: m?.status ?? jobQuery.data.match_status,
  };
  return <JobCard job={job} />;
}
```

- [ ] **Step 5: Write `components/ai/blocks/InsufficientInfoBlockView.tsx`**

```tsx
import type { InsufficientInfoBlock } from "@/lib/api/types";

/** The agent could not gather enough to answer — shows what is still missing. */
export function InsufficientInfoBlockView({ block }: { block: InsufficientInfoBlock }) {
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-sm">
      <p className="text-text">I need a bit more to go on here.</p>
      {block.missing.length > 0 ? (
        <ul className="list-disc pl-5 text-text-muted">
          {block.missing.map((m, i) => (
            <li key={i}>{m}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 6: Write `components/ai/blocks/block-registry.tsx`**

```tsx
import { InsufficientInfoBlockView } from "@/components/ai/blocks/InsufficientInfoBlockView";
import { JobCardBlockView } from "@/components/ai/blocks/JobCardBlockView";
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
    default:
      return (
        <p className="rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-xs text-text-subtle">
          {`This kind of result ("${block.kind}") isn’t available yet.`}
        </p>
      );
  }
}
```

- [ ] **Step 7: Gates** — `pnpm exec tsc --noEmit && pnpm exec eslint components/ai && pnpm exec vitest run tests/ai/block-registry.test.tsx`. Expected: clean; 4 tests pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/ai/blocks frontend/tests/ai/block-registry.test.tsx
git commit -m "feat(ai-fe): response-block views + kind→component registry"
```

---

## Task 4: `ManaPanelDock` + AppShell mount

**Files:**
- Create: `frontend/components/ai/ManaPanelDock.tsx`
- Modify: `frontend/components/layout/AppShell.tsx`
- Test: `frontend/tests/ai/mana-panel.test.tsx`

**Interfaces:**
- Consumes: `useAuth().api.ai.createSession`; `useAgentStream`; `BlockView`; `Button` from `@/components/ui/button`; `Spinner`.
- Produces: `ManaPanelDock()` — a fixed bottom-right widget.
  - Collapsed by default: a round "Mana AI" trigger button (`fixed bottom-4 right-4`, `md:` only — hidden on mobile with `hidden md:block`).
  - Expanded: a `w-96 h-[32rem]` card — header with a collapse button, a scrollable body (user bubbles + assistant `BlockView`s + a live step ticker while streaming), a footer composer (`<textarea>` + Send) and, when there are no messages yet, one suggested-prompt chip: **"find jobs that match my experience"**.
  - On first expand (or first send) it lazily `createSession()` then `send(content)` via `useAgentStream`. A user message renders immediately; assistant blocks stream in.
  - `AppShell` renders `<ManaPanelDock />` as a sibling after `<MobileNav />`.

- [ ] **Step 1: Write `tests/ai/mana-panel.test.tsx`**

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ManaPanelDock } from "@/components/ai/ManaPanelDock";
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

const job = {
  id: "j1", title: "Staff Engineer", company: "Acme", location: "Remote",
  work_mode: "remote", seniority: null, employment_type: null,
  salary_min: null, salary_max: null, salary_currency: null, salary_period: null,
  is_seed: false, status: "ready", posted_at: null, created_at: "2026-09-01T00:00:00Z",
  required_skills: [],
};

describe("ManaPanelDock", () => {
  it("streams a reply with a text block and a job card from the suggested prompt", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: open\ndata: {"event":"open","run_id":"r1"}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"text","markdown":"Here are 1 role."}}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"job_card","job_id":"j1","match_id":null}}\n\n`,
        `event: done\ndata: {"event":"done","status":"completed","totals":{}}\n\n`,
      ]),
    );
    renderWithProviders(<ManaPanelDock />, {
      authValue: { authedStream },
      api: {
        ai: { createSession: vi.fn(async () => ({ id: "s1", messages: [] })) },
        jobs: { get: vi.fn(async () => job) },
        matches: { get: vi.fn() },
      },
    });

    await userEvent.click(screen.getByRole("button", { name: /mana ai/i }));
    await userEvent.click(screen.getByRole("button", { name: /find jobs that match my experience/i }));

    expect(await screen.findByText("Here are 1 role.")).toBeInTheDocument();
    expect(await screen.findByText("Staff Engineer")).toBeInTheDocument();
  });

  it("is collapsed by default", () => {
    renderWithProviders(<ManaPanelDock />);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mana ai/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Write `components/ai/ManaPanelDock.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Sparkles, X } from "lucide-react";

import { BlockView } from "@/components/ai/blocks/block-registry";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useAgentStream } from "@/hooks/useAgentStream";
import type { ResponseBlock } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

const SUGGESTED = "find jobs that match my experience";

interface Turn {
  role: "user" | "assistant";
  text?: string;
  blocks?: ResponseBlock[];
}

export function ManaPanelDock() {
  const { api } = useAuth();
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);

  const stream = useAgentStream(sessionId);

  // Fold the live stream's blocks into the last assistant turn.
  useEffect(() => {
    if (stream.status === "idle") return;
    setTurns((t) => {
      const next = [...t];
      const last = next[next.length - 1];
      if (last && last.role === "assistant") {
        next[next.length - 1] = { ...last, blocks: stream.blocks };
      }
      return next;
    });
  }, [stream.blocks, stream.status]);

  useEffect(() => {
    const el = bodyRef.current;
    // jsdom has no Element.scrollTo — guard so tests don't throw.
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    }
  }, [turns, stream.steps.length]);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    const s = await api.ai.createSession({ kind: "chat" });
    setSessionId(s.id);
    return s.id;
  }, [sessionId, api]);

  const send = useCallback(
    async (content: string) => {
      const body = content.trim();
      if (!body || stream.status === "streaming") return;
      setDraft("");
      setTurns((t) => [...t, { role: "user", text: body }, { role: "assistant", blocks: [] }]);
      await ensureSession();
      // `sessionId` state may not have flushed yet; `useAgentStream.send` reads
      // the latest via its own closure only after this state settles, so defer.
      queueMicrotask(() => stream.send(body));
    },
    [ensureSession, stream],
  );

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-40 hidden items-center gap-2 rounded-full border border-border bg-surface px-4 py-2 text-sm font-medium text-text shadow-[var(--shadow-1)] md:flex"
      >
        <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />
        Mana AI
      </button>
    );
  }

  return (
    <section
      aria-label="Mana AI"
      className="fixed bottom-4 right-4 z-40 hidden h-[32rem] w-96 flex-col rounded-[var(--radius)] border border-border bg-surface shadow-[var(--shadow-1)] md:flex"
    >
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="flex items-center gap-2 text-sm font-semibold text-text">
          <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />
          Mana AI
        </span>
        <button type="button" onClick={() => setOpen(false)} aria-label="Collapse">
          <X className="h-4 w-4 text-text-muted" />
        </button>
      </header>

      <div ref={bodyRef} className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">
        {turns.length === 0 ? (
          <p className="text-sm text-text-muted">
            Ask about your job matches, skill gaps, or a role you’re eyeing.
          </p>
        ) : null}

        {turns.map((turn, i) =>
          turn.role === "user" ? (
            <p
              key={i}
              className="ml-auto max-w-[85%] rounded-[var(--radius)] bg-accent-soft px-3 py-2 text-sm text-accent"
            >
              {turn.text}
            </p>
          ) : (
            <div key={i} className="flex flex-col gap-2">
              {(turn.blocks ?? []).map((b, j) => (
                <BlockView key={j} block={b} />
              ))}
            </div>
          ),
        )}

        {stream.status === "streaming" ? (
          <span className="flex items-center gap-2 text-xs text-text-muted">
            <Spinner size="sm" />
            {stream.steps.at(-1)?.summary ?? "Thinking…"}
          </span>
        ) : null}
        {stream.status === "error" ? (
          <p className="text-xs text-danger">{stream.error}</p>
        ) : null}
      </div>

      <footer className="flex flex-col gap-2 border-t border-border px-4 py-3">
        {turns.length === 0 ? (
          <button
            type="button"
            onClick={() => void send(SUGGESTED)}
            className="self-start rounded-full border border-border px-3 py-1 text-xs text-text-muted hover:bg-surface-sunk"
          >
            {SUGGESTED}
          </button>
        ) : null}
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(draft);
              }
            }}
            rows={1}
            placeholder="Message Mana…"
            className="flex-1 resize-none rounded-[var(--radius)] border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
          />
          <Button size="sm" onClick={() => void send(draft)} disabled={stream.status === "streaming"}>
            Send
          </Button>
        </div>
      </footer>
    </section>
  );
}
```

- [ ] **Step 4: Mount in `components/layout/AppShell.tsx`**

Add the import `import { ManaPanelDock } from "@/components/ai/ManaPanelDock";` and render `<ManaPanelDock />` right after `<MobileNav />`:

```tsx
      <MobileNav />
      <ManaPanelDock />
    </div>
```

- [ ] **Step 5: Gates** — `pnpm exec tsc --noEmit && pnpm exec eslint components/ai components/layout/AppShell.tsx && pnpm exec vitest run tests/ai/mana-panel.test.tsx tests/layout/app-shell.test.tsx`. Expected: clean; mana-panel 2 pass; `app-shell.test.tsx` stays green unchanged (it only asserts nav links + `aria-current`; the collapsed dock adds a "Mana AI" button, nothing it queries).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ai/ManaPanelDock.tsx frontend/components/layout/AppShell.tsx frontend/tests/ai/mana-panel.test.tsx
git commit -m "feat(ai-fe): ManaPanelDock — streaming chat dock, mounted in AppShell"
```

---

## Task 5: Activity page + nav entry

**Files:**
- Create: `frontend/app/(app)/activity/page.tsx`
- Modify: `frontend/components/layout/nav-items.ts`
- Test: `frontend/tests/ai/activity-page.test.tsx`

**Interfaces:**
- Consumes: `useAuth().api.ai.listActions` + `api.ai.startGoal`; `qk.aiActions`; `useQuery`/`useMutation`/`useQueryClient`; `ErrorState`, `Spinner`, `Card`/`CardBody`, `useToast`; `AiAction` from `types.ts`.
- Produces: `ActivityPage` default export. Nav gains `{ href: "/activity", label: "Activity", icon: Activity, ready: true }` (no `adminOnly`).

- [ ] **Step 1: Add the nav entry to `components/layout/nav-items.ts`**

Add `Activity` to the `lucide-react` import. Insert into `NAV` after the `Mana AI` line:

```ts
  { href: "/activity", label: "Activity", icon: Activity, ready: true },
```

- [ ] **Step 2: Write `tests/ai/activity-page.test.tsx`**

```tsx
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ActivityPage from "@/app/(app)/activity/page";
import { renderWithProviders } from "@/test/utils";

const actions = [
  {
    id: "a1", ai_session_id: "s1", run_id: "r1", node: "job_retrieval",
    action_key: "searched_corpus", summary: "Searched your job corpus — 3 roles",
    status: "ok", entity_type: null, entity_id: null, occurred_at: "2026-09-04T10:00:00Z",
  },
  {
    id: "a2", ai_session_id: "s1", run_id: "r1", node: "respond",
    action_key: "responded", summary: "Answered with 2 block(s)",
    status: "warning", entity_type: null, entity_id: null, occurred_at: "2026-09-04T10:00:05Z",
  },
];

describe("ActivityPage", () => {
  it("lists actions with status pills", async () => {
    renderWithProviders(<ActivityPage />, {
      api: { ai: { listActions: vi.fn(async () => ({ items: actions, total: 2 })), startGoal: vi.fn() } },
    });
    expect(await screen.findByText(/Searched your job corpus/)).toBeInTheDocument();
    expect(screen.getByText(/Answered with 2 block/)).toBeInTheDocument();
  });

  it("re-runs the session goal from a warning row", async () => {
    const startGoal = vi.fn(async () => ({ run_id: "r2" }));
    renderWithProviders(<ActivityPage />, {
      api: { ai: { listActions: vi.fn(async () => ({ items: actions, total: 2 })), startGoal } },
    });
    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));
    expect(startGoal).toHaveBeenCalledWith("s1", { goal: "understand_job", inputs: {} });
  });
});
```

- [ ] **Step 3: Run — expect fail.**

- [ ] **Step 4: Write `app/(app)/activity/page.tsx`**

```tsx
"use client";

import { useMemo } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorState } from "@/components/common/ErrorState";
import { Card, CardBody } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import type { AiAction } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const STATUS_CLASS: Record<AiAction["status"], string> = {
  ok: "bg-positive-soft text-positive",
  warning: "bg-warning-soft text-warning",
  error: "bg-danger-soft text-danger",
};

function rel(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function ActivityPage() {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const query = useQuery({
    queryKey: qk.aiActions({}),
    queryFn: () => api.ai.listActions({ limit: 100 }),
  });

  const rerun = useMutation({
    mutationFn: (sessionId: string) =>
      api.ai.startGoal(sessionId, { goal: "understand_job", inputs: {} }),
    onSuccess: () => {
      toast({ title: "Re-running…" });
      void queryClient.invalidateQueries({ queryKey: qk.aiActions({}) });
    },
    onError: () => toast({ title: "Couldn’t start the run.", variant: "danger" }),
  });

  const groups = useMemo(() => {
    const items = query.data?.items ?? [];
    const bySession = new Map<string, AiAction[]>();
    for (const a of items) {
      const key = a.ai_session_id ?? "—";
      const list = bySession.get(key) ?? [];
      list.push(a);
      bySession.set(key, list);
    }
    return [...bySession.entries()];
  }, [query.data]);

  function body() {
    if (query.isPending) {
      return (
        <div className="flex justify-center py-10 text-text-muted">
          <Spinner />
        </div>
      );
    }
    if (query.isError) {
      return <ErrorState onRetry={() => void query.refetch()} />;
    }
    if (groups.length === 0) {
      return <p className="text-sm text-text-muted">Nothing yet — ask Mana something.</p>;
    }
    return (
      <div className="flex flex-col gap-6">
        {groups.map(([sessionId, list]) => (
          <div key={sessionId} className="flex flex-col gap-2">
            {list.map((a) => (
              <div
                key={a.id}
                className="flex items-center gap-3 rounded-[var(--radius)] border border-border bg-surface px-3 py-2 text-sm"
              >
                <span className="font-mono text-xs text-text-muted">{a.node}</span>
                <span className="flex-1 text-text">{a.summary}</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-semibold capitalize",
                    STATUS_CLASS[a.status],
                  )}
                >
                  {a.status}
                </span>
                <span className="text-xs text-text-muted">{rel(a.occurred_at)}</span>
                {a.status !== "ok" && a.ai_session_id ? (
                  <button
                    type="button"
                    onClick={() => rerun.mutate(a.ai_session_id as string)}
                    disabled={rerun.isPending}
                    className="text-xs font-medium text-accent underline-offset-4 hover:underline"
                  >
                    Try again
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-text">Activity</h1>
        <p className="text-sm text-text-muted">
          Everything Mana has done on your behalf, newest first.
        </p>
      </header>
      <Card>
        <CardBody className="text-text">{body()}</CardBody>
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Gates** — `pnpm exec tsc --noEmit && pnpm exec eslint "app/(app)/activity/page.tsx" components/layout/nav-items.ts && pnpm exec vitest run tests/ai/activity-page.test.tsx tests/layout/app-shell.test.tsx`. Expected: clean; activity 2 pass; app-shell green (update it if it asserts the exact NAV list).

- [ ] **Step 6: Commit**

```bash
git add "frontend/app/(app)/activity/page.tsx" frontend/components/layout/nav-items.ts frontend/tests/ai/activity-page.test.tsx
git commit -m "feat(ai-fe): AI Activity feed page + Activity nav entry"
```

---

## Task 6: verification & Phase 7b completion report

- [ ] **Step 1: Full frontend gate** — from `frontend/`:

```bash
pnpm lint
pnpm exec tsc --noEmit
pnpm test run
```

All three clean. Note the new test count (was N → M).

- [ ] **Step 2: Sanity — the dock does not render on the auth routes.** `ManaPanelDock` is inside `AppShell`, which is inside `app/(app)/layout.tsx`'s `RequireAuth` — so it never mounts on `/login` or `/register`. Confirm by inspection; no code needed.

- [ ] **Step 3: Fill the completion report below; commit** `docs: Phase 7b completion report`.

---

## Phase 7b completion report

**Status: COMPLETE** — 5 feature tasks + verification, subagent-driven, all INLINE reviews, 0 blocking findings. 5 thematic commits on `main`.

- **What changed:** `lib/api/types.ts` (+14 AI types: `AgentGoal`, `AiSessionStatus`, `MessageRole`, the block interfaces, `ResponseBlock` union, `Message`, `AiSession`/`AiSessionSummary`/`AiSessionList`, `AiAction`/`AiActionList`, `RunRef`); `lib/api/endpoints.ts` (+`api.ai` group — `createSession`, `listSessions`, `getSession`, `startGoal`, `stopRun`, `listActions`); `lib/query.ts` (+`qk.aiSessions`/`aiSession`/`aiActions`); `hooks/useAgentStream.ts` (POST a message → consume the SSE run: `step`/`block`/`error`/`done` frames → `{ blocks, steps, status, error, send, reset }`); `components/ai/blocks/` (`TextBlockView`, `JobCardBlockView` — fetches the job + polls the match score, `InsufficientInfoBlockView`, `block-registry.tsx` — `kind → component` with a muted fallback for stub kinds); `components/ai/ManaPanelDock.tsx` (right-docked collapsible streaming chat panel, eager session on open, suggested-prompt chip) mounted in `AppShell`; `app/(app)/activity/page.tsx` (AI Activity feed — actions grouped by session, status pills, relative time, "Try again" re-runs the goal) + an "Activity" nav entry.
- **Why:** closes Phase 7 — the user can now talk to the agent and see its work; the block registry + dock are the surface Phases 8–12 extend.
- **Files changed:** 17 files, +899, all under `frontend/`. New: `hooks/useAgentStream.ts`, `components/ai/ManaPanelDock.tsx`, `components/ai/blocks/{TextBlockView,JobCardBlockView,InsufficientInfoBlockView,block-registry}.tsx`, `app/(app)/activity/page.tsx`, 5 test files. Modified: `lib/api/{types,endpoints,query}.ts`, `components/layout/{AppShell,nav-items}.ts`, `tests/api/endpoints.test.ts`.
- **How to test:** `cd frontend && pnpm test run` · `pnpm lint` · `pnpm exec tsc --noEmit`
- **Regression check:** existing suites green; `endpoints.test.ts` extended (+5); `AppShell` gains one child (`<ManaPanelDock/>`); `NAV` gains one `ready` entry; no backend change, no change to any file outside `frontend/`.
- **Baseline:** frontend tests ~40 files/~118 → **42 files / 129** (+5 test files, +11 tests). `tsc --noEmit` clean; `next lint` clean.
- **As-built rulings (recorded in the SDD ledger):** R2 — `parseFrame` is copied verbatim a 3rd time (`useJobEvents`/`useResumeEvents` already carry it; the repo has not extracted a shared helper). R5-lint — the lint gate is `pnpm lint` (= `next lint`); `pnpm exec eslint` is broken repo-wide (ESLint 9 installed against the legacy `.eslintrc.json`). R6 — `block-registry.tsx` fallback copy is "…is not available yet." (the plan wrote "isn't", which its own test's `/not available yet/i` would not match). **R7** — `ManaPanelDock` creates the chat session EAGERLY when the dock opens and `send()` calls `stream.send()` directly; the plan's lazy `ensureSession()` + `queueMicrotask(() => stream.send())` did not work — `useAgentStream(sessionId)`'s `send` closes over `sessionId`, still `null` on the first message, so nothing streamed. The composer + suggested chip are disabled until the session id lands.
- **Deviations (scope):** streaming `sendMessage` is NOT in `api.ai` — `useAgentStream` calls `authedStream` directly, matching `useJobEvents`/`useResumeEvents` (spec §6 listed it in the group). Plain-paragraph text rendering, no markdown engine. Stub block kinds render a muted "not available yet" line. The dock is `md:` only (hidden on mobile) — mobile gets the panel in a later polish pass. `/assistant` "Mana AI" nav entry left `ready: false` (untouched); the always-available dock supersedes a dedicated assistant route.
- **Not verified here:** a real end-to-end stream against a running backend (tests use canned SSE — and per memory, `EventSourceResponse` endpoints can't go through the httpx/ASGI test client anyway); the dock under a real slow network; mobile layout.

---

## Self-Review

**1. Spec coverage (§6):**
- `lib/api/types.ts` AI types → Task 1. ✓
- `lib/api/endpoints.ts` `api.ai` group → Task 1 (6 methods; `sendMessage` deviation noted). ✓
- `lib/query.ts` `qk.aiSessions` / `aiSession(id)` / `aiActions(q)` → Task 1. ✓
- `components/ai/blocks/` `TextBlockView` / `JobCardBlockView` (wraps `JobCard` + polls the score) / `InsufficientInfoBlockView` + `block-registry` (unknown → fallback) → Task 3. ✓
- `components/layout/ManaPanelDock.tsx` — right-docked collapsible, message list, input, suggested-prompt chip, streams via the message endpoint, mounted in `AppShell` → Task 4. (Lives at `components/ai/ManaPanelDock.tsx` — same component, tidier home; spec said `components/layout/`.) ✓
- `app/(app)/activity/page.tsx` — `useQuery(qk.aiActions({}))`, timeline of `AiAction` rows (node · summary · status pill · relative time) grouped by session, "Try again" on error/warning re-runs the goal → Task 5. ✓
- Nav "Activity" entry, `ready: true`, not admin-only → Task 5. ✓
- Tests: `endpoints.test.ts` extended; `mana-panel.test.tsx` (canned SSE → text block + job card); `activity-page.test.tsx`; plus `use-agent-stream.test.ts` and `block-registry.test.tsx` → Tasks 1–5. ✓

**2. Placeholder scan:** every task carries the full component/hook code and its test. No "TBD".

**3. Type consistency:**
- `ResponseBlock` union (Task 1) — consumed by `useAgentStream` (Task 2), `BlockView` (Task 3), `ManaPanelDock` (Task 4).
- `api.ai` method names/shapes (Task 1) — called by `ManaPanelDock` (`createSession`), `ActivityPage` (`listActions`, `startGoal`), and asserted in `endpoints.test.ts`.
- `qk.aiActions` (Task 1) — used by `ActivityPage` (Task 5).
- `useAgentStream` returns `{ blocks, steps, status, error, send, reset }` (Task 2) — `ManaPanelDock` (Task 4) reads `blocks`, `steps`, `status`, `error`, calls `send`.
- `AiAction.status` is `"ok" | "warning" | "error"` (Task 1) — `ActivityPage`'s `STATUS_CLASS` keys match exactly.
- `JobCardBlockView` builds a `JobCard` object with `match_score`/`match_band`/`match_status` (Task 3) — those are the optional fields on `types.ts`'s `JobCard`.
