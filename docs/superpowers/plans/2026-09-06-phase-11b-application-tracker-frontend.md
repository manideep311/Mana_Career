# Phase 11b — Application tracker (frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The application-tracker UI — a Kanban board at `/applications`, a detail page at `/applications/[id]` with the merged timeline + a note composer, a "Save to tracker" entry on Job Detail, and the "Applications" nav entry going live.

**Architecture:** Client-component pages (`"use client"` + `RequireAuth` + TanStack Query), matching every other page in the app. Status change is a native `<select>` (no drag-and-drop, no new deps) with an optimistic `PATCH` + rollback. New `components/applications/*` presentational + container components.

**Tech Stack:** Next.js 15, React 19, TanStack Query v5, react-hook-form + zod, Tailwind, Vitest + Testing Library, pnpm.

**Spec:** `docs/superpowers/specs/2026-09-06-phase-11b-application-tracker-frontend.md` — read first (9 rulings R1–R9).

## Global Constraints

- **Frontend gates** (run from `frontend/`): `pnpm lint` (= `next lint`), `pnpm exec tsc --noEmit`, `pnpm vitest run`. **NEVER run `pnpm exec eslint`** — it is broken repo-wide (ESLint 9 vs legacy `.eslintrc.json`). `pnpm lint` is the lint gate.
- No new npm dependencies. No drag-and-drop library. No new `components/ui/*` primitive — use a native `<select>` / `<textarea>` styled with Tailwind.
- Client pages only (R3). Every page: `"use client"`, wrapped in `<RequireAuth>`, data via `useQuery`, mutations via `useMutation`.
- The backend is Phase 11a as shipped on `main@d402183`: `POST /applications {job_id, intent}` (201 `ApplicationOut` for `save`), `GET /applications?status=&sort=&limit=&offset=` → `{items,total,limit,offset}`, `GET /applications/{id}`, `PATCH /applications/{id} {status?,notes?}` (status is a 6-value `Literal`, others → 422), `DELETE /applications/{id}` (204), `POST /applications/{id}/notes {body}` (201 `TimelineItemOut`), `GET /applications/{id}/timeline` → `{items: TimelineItemOut[]}`.
- `ApplicationStatus` = `"saved" | "applied" | "interview" | "offer" | "rejected" | "withdrawn"`. Column order (R4): Saved · Applied · Interview · Offer · Rejected · Withdrawn.
- Test harness: `renderWithProviders(ui, { api, authValue, route })` from `@/test/utils`; pass a partial `api` mock (e.g. `{ applications: { list: vi.fn().mockResolvedValue(...) } }`). `@/test/utils` mocks `next/navigation` — do not re-mock `useParams` in a page test (it resolves to `{}` there, so read `params.id ?? ""` and let mock `api` methods ignore their arg).
- Copy: no bare "Loading…" (use `<Skeleton>`), every list has a designed empty state with a next action, typed errors → `<ErrorState onRetry>` + toast.
- `ErrorState` props: `{ title?: string; onRetry?: () => void }` (NOT `message`). `EmptyState` props: `{ title: string; description?: string; action?: ReactNode }`.
- `FormError` takes `message` (string | unknown), NOT children — `<FormError message={errors.x?.message} />`. Import from `@/components/ui/FormError`.
- `Button` (`@/components/ui/button`) has `loading?: boolean` (shows a spinner + disables); variants `default | outline | ghost | danger | link`; sizes `sm | md | lg | icon`. `buttonVariants` is exported from the same module.
- Only semantic color tokens exist: `accent`, `accent-fg`, `accent-soft`, `positive`, `warning`, `danger`, `danger-soft`, `danger-fg`, `text`, `text-muted`, `text-subtle`, `surface`, `surface-sunk`, `border`, `bg`. There is **no** `brand` token and **no** raw Tailwind palette (`violet-500`, …) — never use them.
- Repo convention: **no non-null assertions (`x!`)**. Guard with a local `const` + `?? ""` / `enabled` instead.

---

## Task 1: `lib/api` + `qk` + nav wiring

**Files:** Modify `frontend/lib/api/types.ts`, `frontend/lib/api/endpoints.ts`, `frontend/lib/query.ts`, `frontend/components/layout/nav-items.ts`, `frontend/tests/api/endpoints.test.ts`.

**Interfaces:**
- Produces: `Application.notes` / `Application.ai_session_id`; `ApplicationListResponse`, `TimelineItem`, `ApplicationTimeline`, `ApplicationStatus` types; `api.applications.list/save/patch/remove/addNote/timeline`; `qk.applications(params?)`, `qk.applicationTimeline(id)`.

- [ ] **Step 1: `types.ts`** — in the existing `Application` interface (Phase 10 block), add two fields after `source`:
```ts
  source: string;
  notes: string | null;
  ai_session_id: string | null;
```
Then, right after `interface Application { … }`, add:
```ts
export type ApplicationStatus =
  | "saved" | "applied" | "interview" | "offer" | "rejected" | "withdrawn";

export interface ApplicationListResponse {
  items: Application[];
  total: number;
  limit: number;
  offset: number;
}

export interface TimelineItem {
  kind: string;
  at: string;
  title: string;
  detail: Record<string, unknown>;
}

export interface ApplicationTimeline {
  items: TimelineItem[];
}
```

- [ ] **Step 2: `endpoints.ts`** — add the new type imports to the top `import { … } from "@/lib/api/types"` block: `ApplicationListResponse`, `ApplicationStatus`, `ApplicationTimeline`, `TimelineItem`. Then replace the existing `applications: { … }` section with:
```ts
    applications: {
      async create(body: { job_id: string }) {
        return f<RunRef>("/api/v1/applications", json("POST", body));
      },
      async save(job_id: string) {
        return f<Application>(
          "/api/v1/applications",
          json("POST", { job_id, intent: "save" }),
        );
      },
      async get(id: string) {
        return f<Application>(`/api/v1/applications/${id}`);
      },
      async list(
        params: { status?: string; sort?: string; limit?: number; offset?: number } = {},
      ) {
        const qs = new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== "")
            .map(([k, v]) => [k, String(v)]),
        ).toString();
        return f<ApplicationListResponse>(`/api/v1/applications${qs ? `?${qs}` : ""}`);
      },
      async patch(id: string, body: { status?: ApplicationStatus; notes?: string }) {
        return f<Application>(`/api/v1/applications/${id}`, json("PATCH", body));
      },
      async remove(id: string) {
        return f<void>(`/api/v1/applications/${id}`, { method: "DELETE" });
      },
      async addNote(id: string, body: string) {
        return f<TimelineItem>(
          `/api/v1/applications/${id}/notes`,
          json("POST", { body }),
        );
      },
      async timeline(id: string) {
        return f<ApplicationTimeline>(`/api/v1/applications/${id}/timeline`);
      },
    },
```

- [ ] **Step 3: `lib/query.ts`** — in the `qk` object, `qk.application(id)` already exists. Add:
```ts
  applications: (params?: Record<string, unknown>) =>
    ["applications", "list", params ?? {}] as const,
  applicationTimeline: (id: string) => ["application", id, "timeline"] as const,
```

- [ ] **Step 4: `components/layout/nav-items.ts`** — flip the `/applications` entry:
```ts
  { href: "/applications", label: "Applications", icon: FileText, ready: true },
```

- [ ] **Step 5: extend `tests/api/endpoints.test.ts`** — there is already a `describe("applications + approvals", …)` block (it has `applications.create` / `applications.get` / `approvals.*` cases). Add these `it(...)` cases **inside that existing block** (do not create a second `describe`):
```ts
  it("save posts intent=save", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.save("job-1");
    expect(calls[0].path).toBe("/api/v1/applications");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      job_id: "job-1",
      intent: "save",
    });
  });

  it("list builds a status query string", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.list({ status: "interview", limit: 100 });
    expect(calls[0].path).toBe("/api/v1/applications?status=interview&limit=100");
  });

  it("list with no params hits the bare path", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.list();
    expect(calls[0].path).toBe("/api/v1/applications");
  });

  it("patch PATCHes status", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.patch("a-1", { status: "applied" });
    expect(calls[0].path).toBe("/api/v1/applications/a-1");
    expect(calls[0].init?.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ status: "applied" });
  });

  it("addNote posts the body", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.addNote("a-1", "called recruiter");
    expect(calls[0].path).toBe("/api/v1/applications/a-1/notes");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ body: "called recruiter" });
  });

  it("timeline GETs the timeline path", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.timeline("a-1");
    expect(calls[0].path).toBe("/api/v1/applications/a-1/timeline");
  });

  it("remove DELETEs", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).applications.remove("a-1");
    expect(calls[0].path).toBe("/api/v1/applications/a-1");
    expect(calls[0].init?.method).toBe("DELETE");
  });
```
(these close with the existing block's `});` — you are inserting, not adding a new `describe`.)

- [ ] **Step 6: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/api/endpoints.test.ts`
Expected: all green.

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts frontend/lib/query.ts frontend/components/layout/nav-items.ts frontend/tests/api/endpoints.test.ts
git commit -m "feat(applications-fe): api client + query keys + Applications nav entry"
```

---

## Task 2: pure components — `StatusSelect`, `Timeline`, `AddNoteForm`

**Files:** Create `frontend/components/applications/StatusSelect.tsx`, `frontend/components/applications/Timeline.tsx`, `frontend/components/applications/AddNoteForm.tsx`, `frontend/tests/applications/status-select.test.tsx`, `frontend/tests/applications/timeline.test.tsx`.

**Interfaces:**
- Consumes: `ApplicationStatus`, `TimelineItem` (Task 1).
- Produces: `<StatusSelect value onChange disabled? />`, `<Timeline items />`, `<AddNoteForm onSubmit submitting />`.

- [ ] **Step 1: `components/applications/StatusSelect.tsx`**
```tsx
"use client";

import type { ApplicationStatus } from "@/lib/api/types";

export const STATUS_OPTIONS: { value: ApplicationStatus; label: string }[] = [
  { value: "saved", label: "Saved" },
  { value: "applied", label: "Applied" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "withdrawn", label: "Withdrawn" },
];

export function StatusSelect({
  value,
  onChange,
  disabled,
}: {
  value: ApplicationStatus;
  onChange: (s: ApplicationStatus) => void;
  disabled?: boolean;
}) {
  return (
    <select
      aria-label="Application status"
      className="rounded-full border border-border bg-surface px-2 py-1 text-xs text-text disabled:opacity-60"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as ApplicationStatus)}
    >
      {STATUS_OPTIONS.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
```

- [ ] **Step 2: `components/applications/Timeline.tsx`**
```tsx
import type { TimelineItem } from "@/lib/api/types";

// Only semantic tokens exist in this app (accent / positive / warning / danger /
// text-muted / border) — there is no `brand` or raw Tailwind palette. Do not
// invent `bg-violet-500` etc.
const DOT: Record<string, string> = {
  status_change: "bg-accent",
  note: "bg-text-muted",
  ai_action: "bg-accent",
  email_sent: "bg-positive",
  interview_scheduled: "bg-warning",
};

function detailEntries(detail: Record<string, unknown>): [string, string][] {
  return Object.entries(detail)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v)]);
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-text-muted">No history yet.</p>;
  }
  return (
    <ol className="space-y-4">
      {items.map((it, i) => {
        const entries = detailEntries(it.detail);
        return (
          <li key={`${it.at}-${i}`} className="flex gap-3">
            <span
              aria-hidden
              className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${DOT[it.kind] ?? "bg-border"}`}
            />
            <div className="min-w-0">
              <p className="text-sm text-text">{it.title}</p>
              <p className="text-xs text-text-muted">
                {new Date(it.at).toLocaleString()}
              </p>
              {entries.length > 0 ? (
                <dl className="mt-1 space-y-0.5 text-xs text-text-muted">
                  {entries.map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="font-medium capitalize">{k}</dt>
                      <dd className="min-w-0 break-words">{v}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
```

- [ ] **Step 3: `components/applications/AddNoteForm.tsx`**
```tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/FormError";

// FormError takes a `message` prop (string | unknown), NOT children — see
// components/auth/LoginForm.tsx. Render <FormError message={errors.body?.message} />.

const schema = z.object({
  body: z.string().min(1, "Write a note first.").max(4000, "Keep it under 4000 characters."),
});
type Values = z.infer<typeof schema>;

export function AddNoteForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (body: string) => Promise<void>;
  submitting: boolean;
}) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  return (
    <form
      className="space-y-2"
      onSubmit={handleSubmit(async (v) => {
        await onSubmit(v.body);
        reset();
      })}
    >
      <textarea
        aria-label="New note"
        rows={3}
        className="w-full rounded-[var(--radius)] border border-border bg-surface p-2 text-sm text-text"
        placeholder="Add a note — a call, a follow-up, a thought…"
        {...register("body")}
      />
      <FormError message={errors.body?.message} />
      <Button type="submit" size="sm" loading={submitting}>
        Add note
      </Button>
    </form>
  );
}
```
**NOTE for the implementer:** verify the exact import path + API of the form-error component (`components/ui/FormError.tsx` exists) and `Button`'s `loading` prop (used by `<TailorButton>`/`<ApprovalCard>` — confirm it's `loading` not `isLoading`). If `FormError` takes a `message` prop instead of children, adapt. Match `components/applications/ApprovalCard.tsx` / `AddJobDialog.tsx` conventions.

- [ ] **Step 4: `tests/applications/status-select.test.tsx`**
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StatusSelect } from "@/components/applications/StatusSelect";

describe("StatusSelect", () => {
  it("renders all six statuses and reports the picked value", async () => {
    const onChange = vi.fn();
    render(<StatusSelect value="saved" onChange={onChange} />);
    const select = screen.getByRole("combobox", { name: /application status/i });
    expect(screen.getAllByRole("option")).toHaveLength(6);
    await userEvent.selectOptions(select, "interview");
    expect(onChange).toHaveBeenCalledWith("interview");
  });
});
```

- [ ] **Step 5: `tests/applications/timeline.test.tsx`**
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Timeline } from "@/components/applications/Timeline";

describe("Timeline", () => {
  it("renders items in given order with detail entries", () => {
    render(
      <Timeline
        items={[
          { kind: "note", at: "2026-09-06T10:00:00Z", title: "Note added", detail: { body: "Rang HR" } },
          { kind: "status_change", at: "2026-09-05T10:00:00Z", title: "Moved to applied", detail: { from: "saved", to: "applied" } },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Note added");
    expect(items[0]).toHaveTextContent("Rang HR");
    expect(items[1]).toHaveTextContent("Moved to applied");
  });

  it("shows the empty copy", () => {
    render(<Timeline items={[]} />);
    expect(screen.getByText(/no history yet/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/status-select.test.tsx tests/applications/timeline.test.tsx`
Expected: green.

```bash
git add frontend/components/applications/StatusSelect.tsx frontend/components/applications/Timeline.tsx frontend/components/applications/AddNoteForm.tsx frontend/tests/applications/status-select.test.tsx frontend/tests/applications/timeline.test.tsx
git commit -m "feat(applications-fe): StatusSelect, Timeline, AddNoteForm presentational components"
```

---

## Task 3: `ApplicationCard` + `KanbanBoard`

**Files:** Create `frontend/components/applications/ApplicationCard.tsx`, `frontend/components/applications/KanbanBoard.tsx`, `frontend/tests/applications/kanban-board.test.tsx`.

**Interfaces:**
- Consumes: `Application`, `ApplicationStatus` (Task 1), `<StatusSelect>` (Task 2).
- Produces: `<ApplicationCard application jobTitle? company? onStatusChange busy? />`, `<KanbanBoard applications jobs onMove movingId />`.

- [ ] **Step 1: `components/applications/ApplicationCard.tsx`**
```tsx
"use client";

import Link from "next/link";

import { StatusSelect } from "@/components/applications/StatusSelect";
import { Card, CardBody } from "@/components/ui/card";
import type { Application, ApplicationStatus } from "@/lib/api/types";

export function ApplicationCard({
  application,
  jobTitle,
  company,
  onStatusChange,
  busy,
}: {
  application: Application;
  jobTitle?: string;
  company?: string;
  onStatusChange: (s: ApplicationStatus) => void;
  busy?: boolean;
}) {
  const title = jobTitle ?? `Job ${application.job_id.slice(0, 8)}`;
  return (
    <Card className="text-sm">
      <CardBody className="space-y-2 p-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-text">{title}</p>
          {company ? <p className="truncate text-xs text-text-muted">{company}</p> : null}
        </div>
        <div className="flex items-center justify-between gap-2">
          {application.match_score != null ? (
            <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
              {Math.round(Number(application.match_score))}% match
            </span>
          ) : (
            <span />
          )}
          <StatusSelect
            value={application.status as ApplicationStatus}
            onChange={onStatusChange}
            disabled={busy}
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-text-muted">
            {new Date(application.last_status_change_at).toLocaleDateString()}
          </span>
          <Link
            href={`/applications/${application.id}`}
            className="text-xs font-medium text-accent hover:underline"
          >
            Open
          </Link>
        </div>
      </CardBody>
    </Card>
  );
}
```

- [ ] **Step 2: `components/applications/KanbanBoard.tsx`**
```tsx
"use client";

import { ApplicationCard } from "@/components/applications/ApplicationCard";
import type { Application, ApplicationStatus } from "@/lib/api/types";

const COLUMNS: { status: ApplicationStatus; label: string; muted?: boolean }[] = [
  { status: "saved", label: "Saved" },
  { status: "applied", label: "Applied" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "rejected", label: "Rejected", muted: true },
  { status: "withdrawn", label: "Withdrawn", muted: true },
];

export function KanbanBoard({
  applications,
  jobs,
  onMove,
  movingId,
}: {
  applications: Application[];
  jobs: Record<string, { title: string; company: string }>;
  onMove: (id: string, status: ApplicationStatus) => void;
  movingId: string | null;
}) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-2">
      {COLUMNS.map((col) => {
        const cards = applications.filter((a) => a.status === col.status);
        return (
          <section
            key={col.status}
            aria-label={col.label}
            className="flex w-72 shrink-0 flex-col gap-2"
          >
            <header
              className={`flex items-center justify-between text-sm font-semibold ${
                col.muted ? "text-text-muted" : "text-text"
              }`}
            >
              <span>{col.label}</span>
              <span className="text-xs text-text-muted">{cards.length}</span>
            </header>
            {cards.length === 0 ? (
              <p className="rounded-[var(--radius)] border border-dashed border-border p-3 text-xs text-text-muted">
                Nothing here yet.
              </p>
            ) : (
              cards.map((a) => (
                <ApplicationCard
                  key={a.id}
                  application={a}
                  jobTitle={jobs[a.job_id]?.title}
                  company={jobs[a.job_id]?.company}
                  busy={movingId === a.id}
                  onStatusChange={(s) => onMove(a.id, s)}
                />
              ))
            )}
          </section>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: `tests/applications/kanban-board.test.tsx`**
```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { KanbanBoard } from "@/components/applications/KanbanBoard";
import type { Application } from "@/lib/api/types";

function app(id: string, status: string, job_id = "j1"): Application {
  return {
    id, job_id, resume_version_id: null, cover_letter_id: null, application_email_id: null,
    status, match_score: null, source: "user", notes: null, ai_session_id: null,
    applied_at: null, last_status_change_at: "2026-09-06T10:00:00Z",
    created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
  };
}

describe("KanbanBoard", () => {
  it("buckets applications into columns with counts", () => {
    render(
      <KanbanBoard
        applications={[app("a", "saved"), app("b", "saved"), app("c", "applied")]}
        jobs={{ j1: { title: "Staff Eng", company: "Acme" } }}
        onMove={vi.fn()}
        movingId={null}
      />,
    );
    const saved = screen.getByRole("region", { name: "Saved" });
    expect(within(saved).getAllByText("Staff Eng")).toHaveLength(2);
    const applied = screen.getByRole("region", { name: "Applied" });
    expect(within(applied).getAllByText("Staff Eng")).toHaveLength(1);
  });

  it("calls onMove with the card id and picked status", async () => {
    const onMove = vi.fn();
    render(
      <KanbanBoard
        applications={[app("a", "saved")]}
        jobs={{ j1: { title: "Staff Eng", company: "Acme" } }}
        onMove={onMove}
        movingId={null}
      />,
    );
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /application status/i }),
      "interview",
    );
    expect(onMove).toHaveBeenCalledWith("a", "interview");
  });
});
```

- [ ] **Step 4: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/kanban-board.test.tsx`
Expected: green.

```bash
git add frontend/components/applications/ApplicationCard.tsx frontend/components/applications/KanbanBoard.tsx frontend/tests/applications/kanban-board.test.tsx
git commit -m "feat(applications-fe): ApplicationCard + KanbanBoard"
```

---

## Task 4: `/applications` board page

**Files:** Create `frontend/app/(app)/applications/page.tsx`, `frontend/tests/applications/applications-page.test.tsx`.

**Interfaces:**
- Consumes: `api.applications.list/patch`, `api.jobs.get`, `qk.applications`, `<KanbanBoard>`.
- Produces: the `/applications` route.

- [ ] **Step 1: `app/(app)/applications/page.tsx`**
```tsx
"use client";

import { useMemo, useState } from "react";

import Link from "next/link";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { KanbanBoard } from "@/components/applications/KanbanBoard";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import type { Application, ApplicationListResponse, ApplicationStatus } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

function BoardInner() {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [movingId, setMovingId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: qk.applications({ limit: 100 }),
    queryFn: () => api.applications.list({ limit: 100 }),
  });

  const jobIds = useMemo(
    () => [...new Set((listQuery.data?.items ?? []).map((a) => a.job_id))],
    [listQuery.data],
  );
  const jobQueries = useQueries({
    queries: jobIds.map((id) => ({
      queryKey: qk.job(id),
      queryFn: () => api.jobs.get(id),
      staleTime: 5 * 60_000,
    })),
  });
  const jobs = useMemo(() => {
    const map: Record<string, { title: string; company: string }> = {};
    jobQueries.forEach((q, i) => {
      if (q.data) map[jobIds[i]] = { title: q.data.title ?? "", company: q.data.company ?? "" };
    });
    return map;
  }, [jobQueries, jobIds]);

  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) =>
      api.applications.patch(id, { status }),
    onMutate: async ({ id, status }) => {
      setMovingId(id);
      const key = qk.applications({ limit: 100 });
      await queryClient.cancelQueries({ queryKey: key });
      const prev = queryClient.getQueryData<ApplicationListResponse>(key);
      if (prev) {
        queryClient.setQueryData<ApplicationListResponse>(key, {
          ...prev,
          items: prev.items.map((a) =>
            a.id === id
              ? { ...a, status, last_status_change_at: new Date().toISOString() }
              : a,
          ),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(qk.applications({ limit: 100 }), ctx.prev);
      toast({ title: "Couldn't move that application.", variant: "danger" });
    },
    onSettled: (_d, _e, vars) => {
      setMovingId(null);
      void queryClient.invalidateQueries({ queryKey: qk.applications({ limit: 100 }) });
      void queryClient.invalidateQueries({ queryKey: qk.application(vars.id) });
    },
  });

  if (listQuery.isPending) {
    return (
      <div className="flex gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-64 w-72 shrink-0" />
        ))}
      </div>
    );
  }
  if (listQuery.isError) {
    return <ErrorState title="We couldn't load your applications." onRetry={() => listQuery.refetch()} />;
  }

  const items: Application[] = listQuery.data.items;
  if (items.length === 0) {
    return (
      <EmptyState
        title="No applications yet"
        description="Save a job to start tracking it, or prepare one with Mana AI."
        action={
          <Link href="/jobs" className={buttonVariants({ variant: "default" })}>
            Browse jobs
          </Link>
        }
      />
    );
  }

  return (
    <KanbanBoard
      applications={items}
      jobs={jobs}
      movingId={movingId}
      onMove={(id, status) => move.mutate({ id, status })}
    />
  );
}

export default function ApplicationsPage() {
  return (
    <RequireAuth>
      <div className="space-y-6">
        <header>
          <h1 className="text-xl font-semibold text-text">Applications</h1>
          <p className="text-sm text-text-muted">Every role you're tracking, by stage.</p>
        </header>
        <BoardInner />
      </div>
    </RequireAuth>
  );
}
```
**NOTE for the implementer:** confirm `RequireAuth` is a wrapper component (`children`) at `@/components/auth/RequireAuth` (used by `resume/versions/[id]/page.tsx`). Confirm `buttonVariants` is exported from `@/components/ui/button` (Phase 10b `jobs/[id]/page.tsx` imports it). Confirm the toast variant string is `"danger"` (grep other `toast({` calls). Confirm `JobDetail` has `.title` / `.company` (it does — `JobCard` reads them). If `useQueries` result typing fights `tsc`, give the queries array an explicit type or `q.data as JobDetail | undefined`.

- [ ] **Step 2: `tests/applications/applications-page.test.tsx`**
```tsx
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ApplicationsPage from "@/app/(app)/applications/page";
import { renderWithProviders } from "@/test/utils";
import type { Application } from "@/lib/api/types";

function app(id: string, status: string): Application {
  return {
    id, job_id: "j1", resume_version_id: null, cover_letter_id: null, application_email_id: null,
    status, match_score: null, source: "user", notes: null, ai_session_id: null,
    applied_at: null, last_status_change_at: "2026-09-06T10:00:00Z",
    created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
  };
}

function api(over: Record<string, unknown> = {}) {
  return {
    applications: {
      list: vi.fn().mockResolvedValue({ items: [app("a", "saved")], total: 1, limit: 100, offset: 0 }),
      patch: vi.fn().mockResolvedValue(app("a", "applied")),
      ...over,
    },
    jobs: { get: vi.fn().mockResolvedValue({ title: "Staff Eng", company: "Acme" }) },
  };
}

describe("ApplicationsPage", () => {
  it("optimistically moves a card and keeps it when the patch resolves", async () => {
    renderWithProviders(<ApplicationsPage />, { api: api() as never });
    await screen.findByText("Staff Eng");
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /application status/i }),
      "applied",
    );
    await waitFor(() => {
      const applied = screen.getByRole("region", { name: "Applied" });
      expect(within(applied).getByText("Staff Eng")).toBeInTheDocument();
    });
  });

  it("rolls the card back and toasts when the patch fails", async () => {
    renderWithProviders(
      <ApplicationsPage />,
      { api: api({ patch: vi.fn().mockRejectedValue(new Error("nope")) }) as never },
    );
    await screen.findByText("Staff Eng");
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /application status/i }),
      "applied",
    );
    await waitFor(() => {
      const saved = screen.getByRole("region", { name: "Saved" });
      expect(within(saved).getByText("Staff Eng")).toBeInTheDocument();
    });
  });

  it("shows the empty state with a jobs link", async () => {
    renderWithProviders(
      <ApplicationsPage />,
      { api: api({ list: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 }) }) as never },
    );
    expect(await screen.findByText(/no applications yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /browse jobs/i })).toHaveAttribute("href", "/jobs");
  });
});
```

- [ ] **Step 3: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/applications-page.test.tsx`
Expected: green.

```bash
git add "frontend/app/(app)/applications/page.tsx" frontend/tests/applications/applications-page.test.tsx
git commit -m "feat(applications-fe): /applications Kanban board with optimistic status moves"
```

---

## Task 5: `/applications/[id]` detail page

**Files:** Create `frontend/app/(app)/applications/[id]/page.tsx`, `frontend/tests/applications/application-detail.test.tsx`.

**Interfaces:**
- Consumes: `api.applications.get/patch/remove/addNote/timeline`, `api.jobs.get`, `<StatusSelect>`, `<Timeline>`, `<AddNoteForm>`, `qk.application`, `qk.applicationTimeline`.
- Produces: the `/applications/[id]` route.

- [ ] **Step 1: `app/(app)/applications/[id]/page.tsx`**
```tsx
"use client";

import { useState } from "react";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { AddNoteForm } from "@/components/applications/AddNoteForm";
import { StatusSelect } from "@/components/applications/StatusSelect";
import { Timeline } from "@/components/applications/Timeline";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import type { ApplicationStatus, ApplicationTimeline } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

function DetailInner({ id }: { id: string }) {
  const { api } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [savingNote, setSavingNote] = useState(false);

  const appQuery = useQuery({ queryKey: qk.application(id), queryFn: () => api.applications.get(id) });
  const timelineQuery = useQuery({
    queryKey: qk.applicationTimeline(id),
    queryFn: () => api.applications.timeline(id),
  });
  const jobId = appQuery.data?.job_id ?? "";
  const jobQuery = useQuery({
    queryKey: qk.job(jobId),
    queryFn: () => api.jobs.get(jobId),
    enabled: jobId !== "",
  });

  const patch = useMutation({
    mutationFn: (status: ApplicationStatus) => api.applications.patch(id, { status }),
    onError: () => toast({ title: "Couldn't update the status.", variant: "danger" }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: qk.application(id) });
      void queryClient.invalidateQueries({ queryKey: qk.applicationTimeline(id) });
    },
  });

  async function addNote(body: string) {
    setSavingNote(true);
    const key = qk.applicationTimeline(id);
    const prev = queryClient.getQueryData<ApplicationTimeline>(key);
    queryClient.setQueryData<ApplicationTimeline>(key, {
      items: [
        { kind: "note", at: new Date().toISOString(), title: "Note added", detail: { body } },
        ...(prev?.items ?? []),
      ],
    });
    try {
      await api.applications.addNote(id, body);
    } catch {
      if (prev) queryClient.setQueryData(key, prev);
      toast({ title: "Couldn't save the note.", variant: "danger" });
    } finally {
      setSavingNote(false);
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }

  async function remove() {
    if (!window.confirm("Remove this application from your tracker?")) return;
    try {
      await api.applications.remove(id);
      void queryClient.invalidateQueries({ queryKey: qk.applications() });
      router.push("/applications");
    } catch {
      toast({ title: "Couldn't remove that application.", variant: "danger" });
    }
  }

  if (appQuery.isPending) return <Skeleton className="h-64 w-full" />;
  if (appQuery.isError) {
    return <ErrorState title="We couldn't load this application." onRetry={() => appQuery.refetch()} />;
  }

  const a = appQuery.data;
  const job = jobQuery.data;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Link href="/applications" className="text-xs text-text-muted hover:underline">
          ← All applications
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-text">
              {job?.title ?? `Job ${a.job_id.slice(0, 8)}`}
            </h1>
            {job?.company ? <p className="text-sm text-text-muted">{job.company}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            <StatusSelect
              value={a.status as ApplicationStatus}
              onChange={(s) => patch.mutate(s)}
              disabled={patch.isPending}
            />
            <Button variant="outline" size="sm" onClick={remove}>
              Remove
            </Button>
          </div>
        </div>
      </header>

      <Card>
        <CardBody className="flex flex-wrap gap-2 p-4 text-xs">
          {a.resume_version_id ? (
            <Link
              href={`/resume/versions/${a.resume_version_id}`}
              className="rounded-full border border-border px-2 py-1 text-accent hover:underline"
            >
              Tailored résumé
            </Link>
          ) : null}
          {a.cover_letter_id ? (
            <span className="rounded-full border border-border px-2 py-1 text-text-muted">
              Cover letter attached
            </span>
          ) : null}
          {a.application_email_id ? (
            <span className="rounded-full border border-border px-2 py-1 text-text-muted">
              Email drafted
            </span>
          ) : null}
          {!a.resume_version_id && !a.cover_letter_id && !a.application_email_id ? (
            <span className="text-text-muted">No documents yet.</span>
          ) : null}
        </CardBody>
      </Card>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-text">Add a note</h2>
        <AddNoteForm onSubmit={addNote} submitting={savingNote} />
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-text">History</h2>
        {timelineQuery.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <Timeline items={timelineQuery.data?.items ?? []} />
        )}
      </section>
    </div>
  );
}

export default function ApplicationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";
  return (
    <RequireAuth>
      <DetailInner id={id} />
    </RequireAuth>
  );
}
```
**NOTE for the implementer:** RULING R11 (repo convention): the page-under-test does NOT mock `useParams` — `@/test/utils` mocks it to `() => ({})`, so `params.id === ""` and the mock `api` methods must ignore their argument. Confirm `Card`/`CardBody` import path and that `Button` supports `variant="outline"` + `size="sm"` (Phase 10b `ApprovalCard` uses both).

- [ ] **Step 2: `tests/applications/application-detail.test.tsx`**
```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ApplicationDetailPage from "@/app/(app)/applications/[id]/page";
import { renderWithProviders } from "@/test/utils";
import type { Application } from "@/lib/api/types";

const appRow: Application = {
  id: "a1", job_id: "j1", resume_version_id: "rv1", cover_letter_id: null,
  application_email_id: null, status: "applied", match_score: null, source: "mana_ai",
  notes: null, ai_session_id: null, applied_at: "2026-09-06T10:00:00Z",
  last_status_change_at: "2026-09-06T10:00:00Z", created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-06T10:00:00Z",
};

function api(over: Record<string, unknown> = {}) {
  return {
    applications: {
      get: vi.fn().mockResolvedValue(appRow),
      timeline: vi.fn().mockResolvedValue({
        items: [
          { kind: "status_change", at: "2026-09-06T10:00:00Z", title: "Moved to applied", detail: { to: "applied" } },
        ],
      }),
      patch: vi.fn().mockResolvedValue(appRow),
      addNote: vi.fn().mockResolvedValue({ kind: "note", at: "2026-09-06T11:00:00Z", title: "Note added", detail: { body: "x" } }),
      ...over,
    },
    jobs: { get: vi.fn().mockResolvedValue({ title: "Staff Eng", company: "Acme" }) },
  };
}

describe("ApplicationDetailPage", () => {
  it("renders the timeline and the job header", async () => {
    renderWithProviders(<ApplicationDetailPage />, { api: api() as never });
    expect(await screen.findByText("Staff Eng")).toBeInTheDocument();
    expect(screen.getByText("Moved to applied")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /tailored résumé/i })).toHaveAttribute(
      "href", "/resume/versions/rv1",
    );
  });

  it("optimistically prepends a note on submit", async () => {
    renderWithProviders(<ApplicationDetailPage />, { api: api() as never });
    await screen.findByText("Staff Eng");
    await userEvent.type(screen.getByRole("textbox", { name: /new note/i }), "Rang the recruiter");
    await userEvent.click(screen.getByRole("button", { name: /add note/i }));
    await waitFor(() => expect(screen.getByText("Rang the recruiter")).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/application-detail.test.tsx`
Expected: green.

```bash
git add "frontend/app/(app)/applications/[id]/page.tsx" frontend/tests/applications/application-detail.test.tsx
git commit -m "feat(applications-fe): /applications/[id] detail with timeline + note composer"
```

---

## Task 6: "Save to tracker" on Job Detail

**Files:** Modify `frontend/app/(app)/jobs/[id]/page.tsx`, `frontend/tests/applications/save-to-tracker.test.tsx` (create).

**Interfaces:**
- Consumes: `api.applications.save` (Task 1).

- [ ] **Step 1:** read the current `jobs/[id]/page.tsx` where the Phase 10b "Prepare application" `<Link>` is (right after `<TailorButton jobId={id} />`). Add a "Save to tracker" button beside it. It needs `useMutation` + `useRouter` + `useToast` (router/toast are already imported/used on that page — confirm). Insert:
```tsx
// near the other hooks in JobDetailPage:
const saveToTracker = useMutation({
  mutationFn: () => api.applications.save(id),
  onSuccess: () => {
    toast({ title: "Saved to your tracker." });
    router.push("/applications");
  },
  onError: () => toast({ title: "Couldn't save that to your tracker.", variant: "danger" }),
});
```
```tsx
// beside the "Prepare application" link:
<Button
  variant="outline"
  loading={saveToTracker.isPending}
  onClick={() => saveToTracker.mutate()}
>
  Save to tracker
</Button>
```
**NOTE for the implementer:** match the exact placement/wrapper of the existing `<TailorButton>` + "Prepare application" `<Link>` block. `Button` and `buttonVariants` are already imported there (Phase 10b). Confirm `api`, `router`, `toast` are already in scope in `JobDetailPage` — the file already uses `useRouter`, `useToast`, `useAuth` (from the earlier read). If `useMutation` isn't imported yet, add it to the existing `@tanstack/react-query` import.

- [ ] **Step 2: `tests/applications/save-to-tracker.test.tsx`**
```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import JobDetailPage from "@/app/(app)/jobs/[id]/page";
import { mockPush, renderWithProviders } from "@/test/utils";

function api(over: Record<string, unknown> = {}) {
  return {
    jobs: {
      get: vi.fn().mockResolvedValue({
        id: "", title: "Staff Eng", company: "Acme", status: "ready",
        required_skills: [], responsibilities: [], preferred_skills: [],
      }),
    },
    resumes: { list: vi.fn().mockResolvedValue([]) },
    matches: { list: vi.fn().mockResolvedValue({ items: [] }) },
    applications: { save: vi.fn().mockResolvedValue({ id: "a1", status: "saved" }), ...over },
  };
}

describe("Job Detail — Save to tracker", () => {
  it("saves and routes to the board", async () => {
    const a = api();
    renderWithProviders(<JobDetailPage />, { api: a as never });
    const btn = await screen.findByRole("button", { name: /save to tracker/i });
    await userEvent.click(btn);
    await waitFor(() => expect(a.applications.save).toHaveBeenCalled());
    expect(mockPush).toHaveBeenCalledWith("/applications");
  });
});
```
**NOTE for the implementer:** `jobs/[id]/page.tsx` may call more `api.*` methods on mount (matches, resumes for `<TailorButton>`, etc.) — run the test, read the failure, and stub whatever else it needs on the mock `api` so the page renders far enough to show the button. Mirror any existing `jobs/[id]` page test if one exists (`tests/**/*job*detail*`). If the page hard-requires a real `useParams` id, follow RULING R11 and keep `id === ""`, stubbing `jobs.get` to ignore its arg.

- [ ] **Step 3: gate + commit**

Run: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run tests/applications/save-to-tracker.test.tsx`
Expected: green.

```bash
git add "frontend/app/(app)/jobs/[id]/page.tsx" frontend/tests/applications/save-to-tracker.test.tsx
git commit -m "feat(applications-fe): Save to tracker button on Job Detail"
```

---

## Task 7: whole-branch review + full gate + completion report + fast-forward + CI

Controller-only. All-frontend branch → whole-branch review is **inline** (project convention).

- [ ] Full gate from `frontend/`: `pnpm lint && pnpm exec tsc --noEmit && pnpm vitest run` — all green (note the total test count vs the pre-branch baseline; verify in a worktree/checkout at the fork point).
- [ ] Inline whole-branch review of the cumulative diff: optimistic-move rollback correctness, no `pnpm exec eslint` slipped into any script, no new deps in `package.json`/`pnpm-lock.yaml`, `nav-items.ts` only flipped the one flag, `types.ts` additions don't collide, every new page is `"use client"` + `RequireAuth`, a11y (`<select>` has `aria-label`, columns have `aria-label`), no bare "Loading…".
- [ ] Append a completion report to this plan file with directly-verified baseline vs branch test counts.
- [ ] Squash/fast-forward to `main` (per-task commits are already ~6 clean conventional commits → fast-forward), push.
- [ ] Watch CI (`frontend` job: `pnpm lint`, `tsc`, `vitest`). Fix any red.
- [ ] `superpowers:finishing-a-development-branch` — delete branch + SDD workspace `.superpowers/sdd/2026-09-06-phase-11b-application-tracker-frontend/`.
- [ ] Update the `mana-career-roadmap-progress` memory: Phase 11b done; Phases 12–14 remain.
