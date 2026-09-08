# Phase 12b — Career insights (frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An `/insights` page — recommended next step, strengths, skills to develop (with a recompute button), a learning roadmap whose milestones stream in as the planner builds them, trending skills, suggested projects. Marking a milestone done closes the matching skill gap.

**Architecture:** One client page (`app/(app)/insights/page.tsx`) fed by a single `useQuery(qk.insights)`, composed of pure section components. The roadmap block owns its own lifecycle: a "Build my roadmap" mutation → a `<RoadmapTimeline>` that merges a REST read of `GET /roadmaps/{id}` with a live SSE stream (`useRoadmapEvents` → `GET /roadmaps/{id}/events`). Per-milestone status is an optimistic `PATCH`.

**Tech Stack:** Next.js 15 / React 19 / TanStack Query v5 / pnpm. No new deps.

**Spec:** `docs/superpowers/specs/2026-09-08-phase-12b-career-insights-frontend.md` — read first (R1–R9).

## Global Constraints

- Frontend-only. Backend (Phase 12a) is shipped and CI-green (`main@9792c3c`).
- Gates, from `frontend/`: `pnpm lint` (= `next lint` — **NEVER** `pnpm exec eslint`, it is broken repo-wide), `pnpm exec tsc --noEmit` (strict, **no `x!` non-null assertions**), `pnpm vitest run`.
- Semantic Tailwind tokens only: `accent`, `positive`, `warning`, `danger`, `text`, `text-muted`, `text-subtle`, `surface`, `surface-sunk`, `border` (+ `-soft`/`-fg`). **No `brand`, no raw palette** (`violet-500` etc.).
- JSX **text** apostrophes → `&apos;` (`react/no-unescaped-entities`); apostrophes inside attribute strings (`title="..."`, `toast({title:"..."})`) are fine.
- SSE hook convention: `authedStream` from `useAuth()`; one hook per consumer with its own `parseFrame` copy + `/\r\n\r\n|\n\n/` split; **single-attempt, no reconnect**. `hooks/usePrepareRunEvents.ts` is the reference.
- Optimistic-mutation convention: `onMutate` cancel + snapshot + write, `onError` restore + `toast({variant:"danger"})`, `onSettled` invalidate. `app/(app)/applications/page.tsx`'s board move is the reference.
- Test util: `renderWithProviders(ui, { api, authValue, route })` + `mockPush` + `AuthContext`/`makeAuthValue` from `@/test/utils`. RULING R11: the page-under-test never mocks `useParams`; import `@/test/utils` **before** the page-under-test. SSE-hook tests use `renderHook` + a `streamOf(frames)` `Response` + a `wrap(authedStream)` `AuthContext.Provider` wrapper (see `tests/applications/use-prepare-run-events.test.ts`).
- `git commit -m` messages: plain text, NO backticks.

---

## Task 1: api client + types + query keys + nav entry

**Files:** Modify `frontend/lib/api/types.ts`, `frontend/lib/api/endpoints.ts`, `frontend/lib/query.ts`, `frontend/components/layout/nav-items.ts`, `frontend/tests/api/endpoints.test.ts`.

**Interfaces:**
- Produces: `Insights`, `Roadmap`, `Milestone`, `RoadmapDetail`, `RoadmapMilestoneStatus`, `SkillMention`, `NextStep`, `RoadmapSummary` types; `api.insights.get`, `api.roadmaps.{list,get,create,patch,patchMilestone}`, `api.skillGaps.aggregate`; `qk.insights`, `qk.roadmap`, `qk.roadmaps`; the Insights nav item.

- [ ] **Step 1: `lib/api/types.ts`** — append (near the existing `SkillGap` block):
```ts
export interface SkillMention {
  skill_slug: string;
  skill_label: string;
  detail: string | null;
}

export interface NextStep {
  kind: string;
  title: string;
  reason: string;
  entity_type: string | null;
  entity_id: string | null;
}

export interface RoadmapSummary {
  id: string;
  title: string;
  next_step: string | null;
  milestones_done: number;
  milestones_total: number;
}

export interface Insights {
  strengths: SkillMention[];
  skills_to_develop: SkillGap[];
  recommended_next_step: NextStep | null;
  trending_skills: SkillMention[];
  suggested_projects: string[];
  roadmap_summary: RoadmapSummary | null;
}

export type RoadmapMilestoneStatus = "not_started" | "in_progress" | "done";

export interface Roadmap {
  id: string;
  scope: string;
  job_id: string | null;
  title: string;
  summary: string | null;
  next_step: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Milestone {
  id: string;
  order_index: number;
  skill_slug: string;
  skill_label: string;
  title: string;
  why_it_matters: string;
  resource_ids: string[];
  est_hours: number | null;
  practice_project: string | null;
  checkpoint: string | null;
  status: RoadmapMilestoneStatus;
  completed_at: string | null;
}

export interface RoadmapDetail extends Roadmap {
  milestones: Milestone[];
}
```
`SkillGap` already exists (`{id, scope, job_match_id|null, skill_slug, skill_label, severity, frequency, rationale|null, status}`) — reuse it for `skills_to_develop`.

- [ ] **Step 2: `lib/api/endpoints.ts`** — add the type imports (`Insights`, `Milestone`, `Roadmap`, `RoadmapDetail`, `RoadmapMilestoneStatus`) to the existing `@/lib/api/types` import block, keeping it alphabetically sorted. Extend the existing `skillGaps` section with `aggregate`, and add `insights` + `roadmaps` sections (place `insights` after `applications`/`approvals`, `roadmaps` after `resumes` — or wherever keeps the object readable; order inside `makeApi`'s return isn't enforced):
```ts
    skillGaps: {
      async list(job_match_id: string) {
        return f<SkillGap[]>(`/api/v1/skill-gaps?scope=job&job_match_id=${job_match_id}`);
      },
      async patch(id: string, status: SkillGapStatus) {
        return f<SkillGap>(`/api/v1/skill-gaps/${id}`, { method: "PATCH", ...json("PATCH", { status }) });
      },
      async aggregate() {
        return f<SkillGap[]>("/api/v1/skill-gaps/aggregate", json("POST"));
      },
    },
    insights: {
      async get() {
        return f<Insights>("/api/v1/insights");
      },
    },
    roadmaps: {
      async list() {
        return f<{ items: Roadmap[] }>("/api/v1/roadmaps");
      },
      async get(id: string) {
        return f<RoadmapDetail>(`/api/v1/roadmaps/${id}`);
      },
      async create(body: { scope?: string; job_id?: string } = {}) {
        return f<{ id: string }>("/api/v1/roadmaps", json("POST", body));
      },
      async patch(id: string, status: "active" | "archived") {
        return f<Roadmap>(`/api/v1/roadmaps/${id}`, json("PATCH", { status }));
      },
      async patchMilestone(
        recId: string, milestoneId: string, status: RoadmapMilestoneStatus,
      ) {
        return f<Milestone>(
          `/api/v1/roadmaps/${recId}/milestones/${milestoneId}`,
          json("PATCH", { status }),
        );
      },
    },
```
**NOTE:** match the existing `skillGaps.patch` shape — check whether the repo's `patch` uses `json("PATCH", ...)` or a hand-built `{ method: "PATCH", headers, body }`. Mirror it exactly for `aggregate`/`patch`/`patchMilestone`. `json(method, body?)` is the helper at the top of `endpoints.ts` — read its signature first.

- [ ] **Step 3: `lib/query.ts`** — add to `qk` (after the `approvals` line):
```ts
  insights: ["insights"] as const,
  roadmaps: ["roadmaps"] as const,
  roadmap: (id: string) => ["roadmap", id] as const,
```

- [ ] **Step 4: `components/layout/nav-items.ts`** — import `Compass` from `lucide-react` (add to the sorted import list), and insert into `NAV` after the `applications` item, before `assistant`:
```ts
  { href: "/insights", label: "Insights", icon: Compass, ready: true },
```

- [ ] **Step 5: `tests/api/endpoints.test.ts`** — inside the existing structure (mirror how `applications`/`approvals` are tested — a `recordingFetcher()` that captures `calls`), add cases:
```ts
  it("insights.get GETs /insights", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).insights.get();
    expect(calls[0].path).toBe("/api/v1/insights");
  });

  it("skillGaps.aggregate POSTs /skill-gaps/aggregate", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).skillGaps.aggregate();
    expect(calls[0].path).toBe("/api/v1/skill-gaps/aggregate");
    expect(calls[0].init?.method).toBe("POST");
  });

  it("roadmaps.create POSTs /roadmaps with a body", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).roadmaps.create();
    expect(calls[0].path).toBe("/api/v1/roadmaps");
    expect(calls[0].init?.method).toBe("POST");
  });

  it("roadmaps.get GETs /roadmaps/{id}", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).roadmaps.get("r1");
    expect(calls[0].path).toBe("/api/v1/roadmaps/r1");
  });

  it("roadmaps.patchMilestone PATCHes the milestone path", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).roadmaps.patchMilestone("r1", "m1", "done");
    expect(calls[0].path).toBe("/api/v1/roadmaps/r1/milestones/m1");
    expect(calls[0].init?.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ status: "done" });
  });
```
Match the file's existing `describe`/helper names — do not invent a new `recordingFetcher` if one exists under another name.

- [ ] **Step 6: gate + commit**

```
pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/api/endpoints.test.ts
```
Expected: lint clean, tsc clean, endpoints tests pass (existing + 5 new).

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/lib/query.ts frontend/components/layout/nav-items.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(insights-fe): api client + types + query keys + Insights nav entry"
```

---

## Task 2: `useRoadmapEvents` hook

**Files:** Create `frontend/hooks/useRoadmapEvents.ts`, `frontend/tests/insights/use-roadmap-events.test.ts`.

**Interfaces:**
- Consumes: `authedStream` (from `useAuth()`), `Milestone` type.
- Produces: `useRoadmapEvents(recommendationId: string | null) -> { milestones: Milestone[]; status: "idle" | "streaming" | "done" | "error"; error: string | null }`.

- [ ] **Step 1: `hooks/useRoadmapEvents.ts`** — copy `hooks/usePrepareRunEvents.ts`'s structure (its `parseFrame`, the `authedStream` + `ReadableStream` reader loop, the `/\r\n\r\n|\n\n/` split, the `cancelled` guard). Differences:
```ts
"use client";

import { useEffect, useState } from "react";

import type { Milestone } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export interface RoadmapEventsState {
  milestones: Milestone[];
  status: "idle" | "streaming" | "done" | "error";
  error: string | null;
}

const INITIAL: RoadmapEventsState = { milestones: [], status: "idle", error: null };

interface Frame { event: string; data: Record<string, unknown>; }

function parseFrame(raw: string): Frame | null {
  /* verbatim from usePrepareRunEvents */
}

/**
 * Streams a roadmap's milestones as the planner builds them
 * (`GET /roadmaps/{id}/events`). The relay replays every milestone already
 * written on connect, then a terminal `done` / `error`. Single-attempt, no
 * reconnect (same rationale as usePrepareRunEvents).
 */
export function useRoadmapEvents(recommendationId: string | null): RoadmapEventsState {
  const { authedStream } = useAuth();
  const [state, setState] = useState<RoadmapEventsState>(INITIAL);

  useEffect(() => {
    if (!recommendationId) {
      setState(INITIAL);
      return;
    }
    setState({ ...INITIAL, status: "streaming" });
    let cancelled = false;

    void (async () => {
      try {
        const res = await authedStream(
          `/api/v1/roadmaps/${recommendationId}/events`,
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
            if (frame.event === "milestone") {
              const ms = frame.data.milestone as Milestone | undefined;
              if (!ms || typeof ms.id !== "string") continue;
              setState((s) =>
                s.milestones.some((x) => x.id === ms.id)
                  ? s
                  : {
                      ...s,
                      milestones: [...s.milestones, ms].sort(
                        (a, b) => a.order_index - b.order_index,
                      ),
                    },
              );
            } else if (frame.event === "error") {
              setState((s) => ({
                ...s,
                status: "error",
                error: String(frame.data.message ?? "We couldn't build your roadmap."),
              }));
            } else if (frame.event === "done") {
              setState((s) => (s.status === "error" ? s : { ...s, status: "done" }));
            }
          }
        }
        if (!cancelled) {
          // Stream closed. If we never saw a terminal frame, treat it as done
          // (a 0-milestone roadmap closes the relay without a `done` in some
          // races) unless nothing at all arrived.
          setState((s) =>
            s.status === "streaming" ? { ...s, status: "done" } : s,
          );
        }
      } catch {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            status: s.milestones.length > 0 ? "done" : "error",
            error: s.milestones.length > 0 ? s.error : "Lost the connection to this roadmap.",
          }));
        }
      }
    })();

    return () => { cancelled = true; };
  }, [recommendationId, authedStream]);

  return state;
}
```
**NOTE:** the roadmap SSE frame's `data` is `{"event":"milestone","milestone":{...Milestone...}}` (the relay does `sse_event({"event":"milestone","milestone": _milestone_payload(m)})`). So `frame.data.milestone` is the `Milestone`. Confirm against `backend/app/api/v1/roadmaps.py::roadmap_events` if unsure.

- [ ] **Step 2: `tests/insights/use-roadmap-events.test.ts`** — mirror `tests/applications/use-prepare-run-events.test.ts` (the `streamOf` + `wrap(authedStream)` helpers). Cases:
```ts
  it("accumulates milestone frames deduped + ordered, then done", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: milestone\ndata: {"event":"milestone","milestone":{"id":"m2","order_index":1,"skill_slug":"go","skill_label":"Go","title":"B","why_it_matters":"x","resource_ids":[],"est_hours":null,"practice_project":null,"checkpoint":null,"status":"not_started","completed_at":null}}\n\n`,
        `event: milestone\ndata: {"event":"milestone","milestone":{"id":"m1","order_index":0,"skill_slug":"sql","skill_label":"SQL","title":"A","why_it_matters":"x","resource_ids":[],"est_hours":null,"practice_project":null,"checkpoint":null,"status":"not_started","completed_at":null}}\n\n`,
        `event: milestone\ndata: {"event":"milestone","milestone":{"id":"m1","order_index":0,"skill_slug":"sql","skill_label":"SQL","title":"A","why_it_matters":"x","resource_ids":[],"est_hours":null,"practice_project":null,"checkpoint":null,"status":"not_started","completed_at":null}}\n\n`,
        `event: done\ndata: {"event":"done","status":"active","id":"r1"}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useRoadmapEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.milestones.map((m) => m.id)).toEqual(["m1", "m2"]);
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"event":"error","message":"We couldn't build your roadmap.","status":"archived"}\n\n`]),
    );
    const { result } = renderHook(() => useRoadmapEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("We couldn't build your roadmap.");
  });

  it("is idle with a null id", () => {
    const { result } = renderHook(() => useRoadmapEvents(null), { wrapper: wrap(vi.fn()) });
    expect(result.current.status).toBe("idle");
  });
```

- [ ] **Step 3: gate + commit**

```
pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/insights/use-roadmap-events.test.ts
```

```bash
git add frontend/hooks/useRoadmapEvents.ts frontend/tests/insights/use-roadmap-events.test.ts
git commit -m "feat(insights-fe): useRoadmapEvents -- stream milestones from GET /roadmaps/{id}/events"
```

---

## Task 3: pure presentational components

**Files:** Create `frontend/components/insights/NextStepCard.tsx`, `SkillPanels.tsx`, `MilestoneRow.tsx`, `TrendingAndProjects.tsx`; `frontend/tests/insights/next-step-card.test.tsx`, `frontend/tests/insights/milestone-row.test.tsx`.

**Interfaces:**
- Consumes: `NextStep`, `SkillMention`, `SkillGap`, `Milestone`, `RoadmapMilestoneStatus` types.
- Produces: the four components (all pure / presentational; `MilestoneRow` and the Refresh button in `SkillPanels` are `"use client"` only because they take callbacks — mark client where a hook or event handler is used).

- [ ] **Step 1: `components/insights/NextStepCard.tsx`** — per spec R3.
```tsx
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import type { NextStep } from "@/lib/api/types";

export function NextStepCard({ step }: { step: NextStep | null }) {
  if (step === null) {
    return (
      <Card>
        <CardBody className="p-4">
          <p className="text-sm text-text-muted">You&apos;re all caught up.</p>
        </CardBody>
      </Card>
    );
  }
  return (
    <Card>
      <CardBody className="flex flex-col gap-2 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-text-subtle">
          Recommended next step
        </p>
        <p className="text-base font-semibold text-text">{step.title}</p>
        <p className="text-sm text-text-muted">{step.reason}</p>
        {step.entity_type === "application" && step.entity_id ? (
          <Link
            href={`/applications/${step.entity_id}`}
            className={buttonVariants({ variant: "default" })}
          >
            Open the application
          </Link>
        ) : null}
      </CardBody>
    </Card>
  );
}
```

- [ ] **Step 2: `components/insights/SkillPanels.tsx`** (`"use client"`) — per spec R4. Props `{ strengths: SkillMention[]; gaps: SkillGap[]; onRefresh: () => void; refreshing: boolean }`. Two `<Card>`s side by side on `md+` (`grid gap-4 md:grid-cols-2`). Strengths card: list of `skill_label` + muted `detail`; empty → "No standout strengths yet — keep scoring jobs." Skills-to-develop card: header row with a `<Button variant="outline" size="sm" loading={refreshing} onClick={onRefresh}>Refresh</Button>`; rows of `skill_label` + a severity badge + `rationale`; empty → "No gaps rolled up yet — Refresh to compute them from your job matches." Severity badge: `critical` → `bg-danger-soft text-danger-fg`, `important` → `bg-warning-soft text-warning-fg`, else `bg-surface-sunk text-text-muted` (check the real token names in an existing badge — grep `components/` for `-soft` / severity chips; mirror what exists).

- [ ] **Step 3: `components/insights/MilestoneRow.tsx`** (`"use client"`) — per spec R8. Props `{ milestone: Milestone; onStatusChange: (s: RoadmapMilestoneStatus) => void; busy?: boolean }`.
```tsx
"use client";

import type { Milestone, RoadmapMilestoneStatus } from "@/lib/api/types";

const STATUS_OPTIONS: { value: RoadmapMilestoneStatus; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
];

export function MilestoneRow({
  milestone,
  onStatusChange,
  busy,
}: {
  milestone: Milestone;
  onStatusChange: (s: RoadmapMilestoneStatus) => void;
  busy?: boolean;
}) {
  const meta = [
    milestone.est_hours != null ? `~${milestone.est_hours}h` : null,
    `${milestone.resource_ids.length} resource${milestone.resource_ids.length === 1 ? "" : "s"}`,
  ].filter(Boolean);
  return (
    <li className="flex flex-col gap-2 rounded-[var(--radius)] border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-text-subtle">
            {milestone.order_index + 1} · {milestone.skill_label}
          </p>
          <p className="text-sm font-medium text-text">{milestone.title}</p>
        </div>
        <select
          aria-label="Milestone status"
          className="rounded-full border border-border bg-surface px-2 py-1 text-xs text-text disabled:opacity-60"
          value={milestone.status}
          disabled={busy}
          onChange={(e) => onStatusChange(e.target.value as RoadmapMilestoneStatus)}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <p className="text-xs text-text-muted">{milestone.why_it_matters}</p>
      {meta.length > 0 ? (
        <p className="text-xs text-text-subtle">{meta.join(" · ")}</p>
      ) : null}
      {milestone.practice_project ? (
        <p className="rounded-[var(--radius)] bg-surface-sunk p-2 text-xs text-text-muted">
          <span className="font-medium text-text">Build:</span> {milestone.practice_project}
        </p>
      ) : null}
      {milestone.checkpoint ? (
        <p className="text-xs text-text-subtle">
          <span className="font-medium">Checkpoint:</span> {milestone.checkpoint}
        </p>
      ) : null}
      {milestone.status === "done" && milestone.completed_at ? (
        <p className="text-xs text-positive">
          Done · {new Date(milestone.completed_at).toLocaleDateString()}
        </p>
      ) : null}
    </li>
  );
}
```

- [ ] **Step 4: `components/insights/TrendingAndProjects.tsx`** — per spec R9. Props `{ trending: SkillMention[]; projects: string[] }`. Two small `<Card>`s (or a `grid md:grid-cols-2`): "Trending skills" = chips `skill_label` + `detail`; "Suggested projects" = a `<ul class="list-disc pl-5">` of the strings. Each with an empty line.

- [ ] **Step 5: tests**
  - `tests/insights/next-step-card.test.tsx` — renders `title`/`reason`; with `entity_type:"application"` + `entity_id:"a1"` shows a link to `/applications/a1`; with `kind:"add_job"` (no entity) shows no link; with `step: null` shows the caught-up copy.
  - `tests/insights/milestone-row.test.tsx` — renders `title` + `why_it_matters` + "Build:" text when `practice_project` set; the `<select name="Milestone status">` starts at `milestone.status`; changing it calls `onStatusChange("done")`; `disabled` when `busy`.
  Use `@testing-library/react` `render` + `screen` + `userEvent` (no providers needed for pure components — `NextStepCard` uses `next/link` which works under the jsdom setup; if it needs the router mock, import `@/test/utils` first for its side-effect mock, matching sibling tests).

- [ ] **Step 6: gate + commit**

```
pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/insights/
```

```bash
git add frontend/components/insights/NextStepCard.tsx frontend/components/insights/SkillPanels.tsx frontend/components/insights/MilestoneRow.tsx frontend/components/insights/TrendingAndProjects.tsx frontend/tests/insights/next-step-card.test.tsx frontend/tests/insights/milestone-row.test.tsx
git commit -m "feat(insights-fe): NextStepCard, SkillPanels, MilestoneRow, TrendingAndProjects"
```

---

## Task 4: `RoadmapTimeline` + `RoadmapSection`

**Files:** Create `frontend/components/insights/RoadmapTimeline.tsx`, `frontend/components/insights/RoadmapSection.tsx`, `frontend/tests/insights/roadmap-timeline.test.tsx`.

**Interfaces:**
- Consumes: `api.roadmaps.{get,create,patchMilestone}`, `useRoadmapEvents` (Task 2), `<MilestoneRow>` (Task 3), `qk.roadmap`/`qk.insights`.
- Produces: `<RoadmapTimeline recommendationId live?>`, `<RoadmapSection summary>`.

- [ ] **Step 1: `components/insights/RoadmapTimeline.tsx`** (`"use client"`) — per spec R6.
```tsx
"use client";

import { useEffect, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { MilestoneRow } from "@/components/insights/MilestoneRow";
import { ErrorState } from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toaster";
import { useRoadmapEvents } from "@/hooks/useRoadmapEvents";
import type { Milestone, RoadmapDetail, RoadmapMilestoneStatus } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

export function RoadmapTimeline({
  recommendationId,
  live,
}: {
  recommendationId: string;
  live?: boolean;
}) {
  const { api } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [movingId, setMovingId] = useState<string | null>(null);

  const roadmapQuery = useQuery({
    queryKey: qk.roadmap(recommendationId),
    queryFn: () => api.roadmaps.get(recommendationId),
  });
  const streaming =
    !!live || roadmapQuery.data?.status === "planning";
  const events = useRoadmapEvents(streaming ? recommendationId : null);

  const { refetch } = roadmapQuery;
  useEffect(() => {
    if (events.status === "done") void refetch();
  }, [events.status, refetch]);

  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: RoadmapMilestoneStatus }) =>
      api.roadmaps.patchMilestone(recommendationId, id, status),
    onMutate: async ({ id, status }) => {
      setMovingId(id);
      const key = qk.roadmap(recommendationId);
      await queryClient.cancelQueries({ queryKey: key });
      const prev = queryClient.getQueryData<RoadmapDetail>(key);
      if (prev) {
        queryClient.setQueryData<RoadmapDetail>(key, {
          ...prev,
          milestones: prev.milestones.map((m) =>
            m.id === id ? { ...m, status } : m,
          ),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(qk.roadmap(recommendationId), ctx.prev);
      toast({ title: "Couldn't update that milestone.", variant: "danger" });
    },
    onSettled: (_d, _e, vars) => {
      setMovingId(null);
      void queryClient.invalidateQueries({ queryKey: qk.roadmap(recommendationId) });
      if (vars.status === "done") {
        void queryClient.invalidateQueries({ queryKey: qk.insights });
      }
    },
  });

  const fromQuery = roadmapQuery.data?.milestones ?? [];
  const milestones: Milestone[] =
    events.milestones.length > fromQuery.length ? events.milestones : fromQuery;

  if (roadmapQuery.isPending && !live) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (roadmapQuery.isError && events.status === "idle") {
    return <ErrorState title="We couldn't load this roadmap." onRetry={() => void roadmapQuery.refetch()} />;
  }

  return (
    <div className="flex flex-col gap-3">
      {milestones.length === 0 && events.status !== "streaming" ? (
        <p className="text-sm text-text-muted">
          No milestones yet. Your gaps may already be covered.
        </p>
      ) : (
        <ol className="flex flex-col gap-3">
          {milestones.map((m) => (
            <MilestoneRow
              key={m.id}
              milestone={m}
              busy={movingId === m.id}
              onStatusChange={(s) => move.mutate({ id: m.id, status: s })}
            />
          ))}
        </ol>
      )}
      {events.status === "streaming" ? (
        <p className="flex items-center gap-2 text-xs text-text-muted">
          <Spinner className="h-3 w-3" /> Building your roadmap…
        </p>
      ) : null}
      {events.status === "error" && milestones.length === 0 ? (
        <ErrorState title={events.error ?? "We couldn't build your roadmap."} />
      ) : null}
    </div>
  );
}
```
**NOTE:** verify `@/components/ui/spinner` exists and its prop (`className`? `size`?) — grep `components/ui/`; `TailorButton.tsx` imports `Spinner`. Use whatever it exports. If there's no `Spinner`, use a small pulsing `<span>` with `animate-pulse`. Verify `ErrorState`'s real prop is `title` (not `message`) — it is (`{ title?: string; onRetry?: () => void }`).

- [ ] **Step 2: `components/insights/RoadmapSection.tsx`** (`"use client"`) — per spec R5.
```tsx
"use client";

import { useState } from "react";

import { useMutation } from "@tanstack/react-query";

import { RoadmapTimeline } from "@/components/insights/RoadmapTimeline";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { useToast } from "@/components/ui/toaster";
import type { RoadmapSummary } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export function RoadmapSection({ summary }: { summary: RoadmapSummary | null }) {
  const { api } = useAuth();
  const { toast } = useToast();
  const [pendingId, setPendingId] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.roadmaps.create(),
    onSuccess: (ref) => setPendingId(ref.id),
    onError: () => toast({ title: "Couldn't start your roadmap.", variant: "danger" }),
  });

  return (
    <Card>
      <CardBody className="flex flex-col gap-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-text">Learning roadmap</h2>
          {summary === null && pendingId === null ? (
            <Button size="sm" loading={create.isPending} onClick={() => create.mutate()}>
              Build my roadmap
            </Button>
          ) : null}
        </div>

        {pendingId !== null ? (
          <RoadmapTimeline recommendationId={pendingId} live />
        ) : summary !== null ? (
          <>
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium text-text">{summary.title}</p>
              <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunk">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{
                    width: `${
                      summary.milestones_total > 0
                        ? Math.round(
                            (summary.milestones_done / summary.milestones_total) * 100,
                          )
                        : 0
                    }%`,
                  }}
                />
              </div>
              <p className="text-xs text-text-muted">
                {summary.milestones_done} of {summary.milestones_total} done
                {summary.next_step ? ` · next: ${summary.next_step}` : ""}
              </p>
            </div>
            <RoadmapTimeline recommendationId={summary.id} />
          </>
        ) : (
          <p className="text-sm text-text-muted">
            No learning roadmap yet — build one from your top skill gaps.
          </p>
        )}
      </CardBody>
    </Card>
  );
}
```

- [ ] **Step 3: `tests/insights/roadmap-timeline.test.tsx`** — `renderWithProviders(<RoadmapTimeline recommendationId="" />, { api: api() as never })` (RULING R11 — `useParams` mocked to `{}`, so `recommendationId` prop is what matters; pass `""` and have the mock `api.roadmaps.get` ignore its arg). Cases:
  - mock `api.roadmaps.get` → a `RoadmapDetail` with `status:"active"` + 2 milestones → both `MilestoneRow`s render; changing the first `<select>` to `done` calls `api.roadmaps.patchMilestone`.
  - mock `api.roadmaps.get` → `status:"active"`, 0 milestones → "No milestones yet" copy.
  Provide an `authValue.authedStream` that returns an empty finite stream (`streamOf([])`) so `useRoadmapEvents` (if it fires) resolves to `done` without hanging — but with `status:"active"` and no `live`, `streaming` is false so the hook stays idle.

- [ ] **Step 4: gate + commit**

```
pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/insights/
```

```bash
git add frontend/components/insights/RoadmapTimeline.tsx frontend/components/insights/RoadmapSection.tsx frontend/tests/insights/roadmap-timeline.test.tsx
git commit -m "feat(insights-fe): RoadmapTimeline (REST+SSE merge, optimistic milestone status) + RoadmapSection"
```

---

## Task 5: `/insights` page

**Files:** Create `frontend/components/insights/InsightsView.tsx`, `frontend/app/(app)/insights/page.tsx`, `frontend/tests/insights/insights-page.test.tsx`.

**Interfaces:**
- Consumes: `api.insights.get`, `api.skillGaps.aggregate`, all Task 3/4 components, `qk.insights`.
- Produces: the `/insights` route.

- [ ] **Step 1: `components/insights/InsightsView.tsx`** (`"use client"`)
```tsx
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { NextStepCard } from "@/components/insights/NextStepCard";
import { RoadmapSection } from "@/components/insights/RoadmapSection";
import { SkillPanels } from "@/components/insights/SkillPanels";
import { TrendingAndProjects } from "@/components/insights/TrendingAndProjects";
import { ErrorState } from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

export function InsightsView() {
  const { api } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const insights = useQuery({ queryKey: qk.insights, queryFn: () => api.insights.get() });

  const refresh = useMutation({
    mutationFn: () => api.skillGaps.aggregate(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.insights }),
    onError: () => toast({ title: "Couldn't refresh your skill gaps.", variant: "danger" }),
  });

  if (insights.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (insights.isError || !insights.data) {
    return <ErrorState title="We couldn't load your insights." onRetry={() => void insights.refetch()} />;
  }

  const d = insights.data;
  return (
    <div className="flex flex-col gap-6">
      <NextStepCard step={d.recommended_next_step} />
      <SkillPanels
        strengths={d.strengths}
        gaps={d.skills_to_develop}
        onRefresh={() => refresh.mutate()}
        refreshing={refresh.isPending}
      />
      <RoadmapSection summary={d.roadmap_summary} />
      <TrendingAndProjects trending={d.trending_skills} projects={d.suggested_projects} />
    </div>
  );
}
```

- [ ] **Step 2: `app/(app)/insights/page.tsx`**
```tsx
"use client";

import { InsightsView } from "@/components/insights/InsightsView";
import { RequireAuth } from "@/components/auth/RequireAuth";

export default function InsightsPage() {
  return (
    <RequireAuth>
      <div className="space-y-6">
        <header>
          <h1 className="text-xl font-semibold text-text">Career insights</h1>
          <p className="text-sm text-text-muted">
            Where you&apos;re strong, what to build next, and a roadmap to get there.
          </p>
        </header>
        <InsightsView />
      </div>
    </RequireAuth>
  );
}
```

- [ ] **Step 3: `tests/insights/insights-page.test.tsx`** — `import "@/test/utils"` FIRST, then the page. `renderWithProviders(<InsightsPage />, { api: api() as never })`. `api()` returns a mock with `insights.get` → a full `Insights` payload (some strengths, 2 gaps, a `recommended_next_step`, `roadmap_summary: null`, some trending + projects) and `roadmaps.get`/`skillGaps.aggregate` stubs. Cases:
  - renders the next-step title, a strength label, a gap label, a trending label, a project.
  - `roadmap_summary: null` → the "Build my roadmap" button shows; clicking it calls `api.roadmaps.create` (mock returns `{id:"r1"}`), and `api.roadmaps.get` gets called for `r1` (the streaming timeline mounts). Provide `authValue.authedStream = () => streamOf([])`.
  - clicking "Refresh" on the skills panel calls `api.skillGaps.aggregate`.

- [ ] **Step 4: gate + commit**

```
pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/insights/
```

```bash
git add frontend/components/insights/InsightsView.tsx "frontend/app/(app)/insights/page.tsx" frontend/tests/insights/insights-page.test.tsx
git commit -m "feat(insights-fe): /insights page -- next step, skills, roadmap, trending, projects"
```

---

## Task 6: whole-branch review + full gate + completion report + squash + push + CI

Controller-only. Mirror the Phase 11b closeout: full frontend gate (`pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm vitest run` — whole suite); inline whole-branch review of `<fork>..HEAD` (cross-task checks: the `qk.roadmap` optimistic write shape vs `RoadmapDetail`, the `useRoadmapEvents` frame shape vs `roadmap_events` relay, every `<Link href>` resolves, `Insights` nav `ready:true` has a real route, `Compass` icon imported, no `x!`, JSX apostrophes escaped); directly-verified baseline test counts (checkout the fork commit, `pnpm vitest run` count, restore); append the completion report to this plan; fast-forward `main`; push; watch CI (frontend job); `finishing-a-development-branch`; update `mana-career-roadmap-progress` memory (Phase 12b done; 13–14 remain).
