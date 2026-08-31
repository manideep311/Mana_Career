# Phase 1c — Frontend Shell (Design System · Auth · Profile UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** A signed-in user can register, log in, and edit their whole career profile — scalars, the four sub-entity lists (with reorder), and a live strength meter — in a responsive, accessible Next.js app that talks to the Phase 1a/1b API.

**Architecture:** Next.js 15 App Router + React 19 + Tailwind v4 (CSS `@theme`, no config file). Hand-rolled shadcn-style primitives (`cva` + `clsx` + `tailwind-merge`, Radix for Label/Toast) — the shadcn CLI is skipped because it is interactive and fragile against TW4 + React 19; the dependency set and approach are the same. The access token lives **in memory** in an `AuthProvider` (never `localStorage`); the httpOnly refresh cookie bootstraps the session via `POST /auth/refresh`; a single 401→refresh→retry wraps every authed call. Server state is TanStack Query; forms are `react-hook-form` + `zod`, with backend `problem+json` mapped onto fields.

**Tech Stack:** Next.js 15.1, React 19, TypeScript (strict), Tailwind CSS v4, `class-variance-authority`, `clsx`, `tailwind-merge`, `@radix-ui/react-label`, `@radix-ui/react-toast`, `@tanstack/react-query` 5, `react-hook-form`, `zod`, `@hookform/resolvers`, `lucide-react`, `next/font`. Tests: Vitest + Testing Library + jsdom. `pnpm` is available locally, so `pnpm-lock.yaml` is regenerated when deps change.

**Spec:** `docs/superpowers/specs/2026-08-30-mana-career-design.md` — implements the frontend slice of §9 Phase 1 ("Design system + authentication + profile"; done-when: *login → profile editable → strength shown*), plus §7 (UI architecture), §7.7 (design tokens), §19 (microcopy), §20 (responsive), §21 (accessibility), §22 (stack).

## Global Constraints

Every task's requirements implicitly include this section.

- **Framework:** Next.js 15 App Router, React 19, TypeScript `strict`. `output: "standalone"`. No `tailwind.config.*` — Tailwind v4 is configured in `app/globals.css` via `@theme inline`, tokens in `styles/tokens.css`.
- **Design tokens (spec §7.7):** warm off-white `--bg`, deep charcoal `--text`, indigo `--accent`, green `--positive`, amber `--warning`, red `--danger` (errors only), `--radius: 14px`, subtle `--shadow-1/2`, font Inter (fallback Geist, Manrope, system-ui). Light theme only ships; keep token **names** stable so a dark set is a later drop-in — never hard-code a hex in a component.
- **Microcopy (spec §19):** human language. "Prepare my application" not "Execute workflow"; "AI suggestion" not "LLM output"; "Your review is needed" not "Action required"; empty states say "Your career workspace is ready.", never "No data found". A control says exactly what happens ("Save", then a toast "Profile saved").
- **Responsive (spec §20):** desktop = left sidebar + main; mobile = bottom nav with **Home · Jobs · Applications · Mana AI · Profile**. Every screen usable at 375px with no horizontal scroll.
- **Accessibility (spec §21):** full keyboard reach, visible token-based focus rings, accessible labels, `aria-live` for toasts and streaming, focus trap + restore in dialogs, WCAG AA contrast, `prefers-reduced-motion` respected, fluid type.
- **Trust treatment (spec §7.3):** three visually distinct states — *retrieved fact*, *calculated score*, *AI suggestion* — plus a real "I don't have enough information to determine this." state. Phase 1c only needs the **calculated score** treatment (the strength meter): mono numerals, a meter, and a "how this is calculated" affordance.
- **API contract:** base `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`). Every request sends `credentials: "include"` (refresh cookie). Errors arrive as `application/problem+json` `{type,title,status,detail,instance,code,errors[]}`; surface `detail` and route `code` / `errors[].loc` to the right field.
- **Auth model:** access token in memory only. `GET /api/v1/auth/me` with `Authorization: Bearer` resolves the user. `POST /api/v1/auth/refresh` (cookie, no body) rotates the token. `POST /api/v1/auth/logout` clears it. A 401 on any non-auth call → one silent `refresh` → retry; a second 401 → sign out.
- **Lint/type/test:** `pnpm lint` (`next/core-web-vitals`), `pnpm exec tsc --noEmit`, `pnpm test run` (Vitest). CI's `frontend` job runs all three on `pnpm install --frozen-lockfile`. No `next/image`-avoidable `<img>`, no missing `key`, hooks rules clean.
- **Workflow:** TDD (failing test first), DRY, YAGNI, commit after every green step. `"use client"` only where hooks/interactivity require it.

---

## File Structure

**Created**
- `frontend/lib/cn.ts` — `cn(...)` class merge.
- `frontend/lib/api/types.ts` — TS mirrors of the backend response models used in 1c.
- `frontend/lib/api/endpoints.ts` — `makeApi(fetcher)` → typed `auth` + `profile` call objects.
- `frontend/lib/query.ts` — `QueryClient` factory + `qk` query-key registry.
- `frontend/components/ui/button.tsx` · `input.tsx` · `label.tsx` · `field.tsx` · `card.tsx` · `skeleton.tsx` · `spinner.tsx` · `toast.tsx` · `toaster.tsx`
- `frontend/components/common/ErrorState.tsx` · `StrengthMeter.tsx`
- `frontend/components/layout/AppShell.tsx` · `Sidebar.tsx` · `MobileNav.tsx` · `UserMenu.tsx` · `nav-items.ts`
- `frontend/components/auth/LoginForm.tsx` · `RegisterForm.tsx` · `RequireAuth.tsx`
- `frontend/components/profile/ProfileScalarForm.tsx` · `SubEntityList.tsx` · `SubEntityForm.tsx` · `subentity-config.ts`
- `frontend/providers/QueryProvider.tsx` · `AuthProvider.tsx`
- `frontend/app/(auth)/layout.tsx` · `(auth)/login/page.tsx` · `(auth)/register/page.tsx`
- `frontend/app/(app)/layout.tsx` · `(app)/dashboard/page.tsx` · `(app)/profile/page.tsx`
- `frontend/test/utils.tsx` — `renderWithProviders`, `mockRouter`.
- Test files alongside each unit under `frontend/tests/`.

**Modified**
- `frontend/package.json` + `frontend/pnpm-lock.yaml` — add deps.
- `frontend/styles/tokens.css` — add `--*-soft`, `--surface-sunk`, `--text-subtle`, `--ring`, `--danger-fg`.
- `frontend/app/globals.css` — map the new tokens into `@theme inline`.
- `frontend/app/layout.tsx` — `next/font` Inter; wrap children in `QueryProvider` → `AuthProvider` → `Toaster`.
- `frontend/app/page.tsx` — point the CTA at `/register`, keep the landing copy (already spec-aligned).

---

## Task 1: Dependencies, design tokens, `cn()`

**Files:**
- Modify: `frontend/package.json`, `frontend/pnpm-lock.yaml`, `frontend/styles/tokens.css`, `frontend/app/globals.css`
- Create: `frontend/lib/cn.ts`
- Test: `frontend/tests/cn.test.ts`

**Interfaces — Produces:**
- `cn(...inputs: ClassValue[]) => string` (`clsx` + `tailwind-merge`).
- New tokens (light values): `--accent-soft: #eef0fb`, `--positive-soft: #e6f4ec`, `--warning-soft: #f7edd9`, `--danger-soft: #fbeae8`, `--danger-fg: #ffffff`, `--surface-sunk: #f2efe9`, `--text-subtle: #8a8f9c`, `--ring: rgba(79,70,229,.45)`. Mapped in `globals.css` as `--color-accent-soft` etc. + `--color-surface-sunk`, `--color-text-subtle`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/cn.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { cn } from "@/lib/cn";

describe("cn", () => {
  it("merges conflicting tailwind classes, last wins", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });
  it("drops falsy values", () => {
    expect(cn("a", false && "b", undefined, "c")).toBe("a c");
  });
});
```

- [ ] **Step 2: Run — expect fail** (`Cannot find module '@/lib/cn'`).

Run: `cd frontend && pnpm test run tests/cn.test.ts`

- [ ] **Step 3: Implement**

```bash
cd frontend && pnpm add class-variance-authority clsx tailwind-merge @radix-ui/react-label @radix-ui/react-toast react-hook-form zod @hookform/resolvers
```

`frontend/lib/cn.ts`:

```ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

Append to `:root` in `frontend/styles/tokens.css`:

```css
  --accent-soft: #eef0fb;
  --positive-soft: #e6f4ec;
  --warning-soft: #f7edd9;
  --danger-soft: #fbeae8;
  --danger-fg: #ffffff;
  --surface-sunk: #f2efe9;
  --text-subtle: #8a8f9c;
```
(`--ring` already exists.)

Add to the `@theme inline` block in `frontend/app/globals.css`:

```css
  --color-accent-soft: var(--accent-soft);
  --color-positive-soft: var(--positive-soft);
  --color-warning-soft: var(--warning-soft);
  --color-danger: var(--danger);
  --color-danger-soft: var(--danger-soft);
  --color-danger-fg: var(--danger-fg);
  --color-surface-sunk: var(--surface-sunk);
  --color-text-subtle: var(--text-subtle);
```

- [ ] **Step 4: Run — expect pass**

Run: `cd frontend && pnpm test run tests/cn.test.ts && pnpm exec tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/lib/cn.ts frontend/styles/tokens.css frontend/app/globals.css frontend/tests/cn.test.ts
git commit -m "feat(fe): design-system deps, semantic tokens, cn() helper"
```

---

## Task 2: Primitives — Button, Input, Label, Field

**Files:**
- Create: `frontend/components/ui/button.tsx`, `input.tsx`, `label.tsx`, `field.tsx`
- Test: `frontend/tests/ui/button.test.tsx`, `frontend/tests/ui/field.test.tsx`

**Interfaces — Produces:**
- `Button` — `React.forwardRef<HTMLButtonElement, ButtonProps>`; `ButtonProps = ComponentProps<"button"> & { variant?: "default"|"outline"|"ghost"|"danger"|"link"; size?: "sm"|"md"|"lg"|"icon"; loading?: boolean }`. `loading` disables and renders a leading `<Spinner/>` (Task 3 — until then a `<span aria-hidden>…</span>` placeholder; wire the real Spinner in Task 3's commit). Exports `buttonVariants` (cva).
- `Input` — `forwardRef<HTMLInputElement, ComponentProps<"input">>`; token classes; `aria-invalid` styles a red ring.
- `Label` — thin wrapper over `@radix-ui/react-label` `Root`.
- `Field` — `{ id: string; label: string; error?: string; hint?: string; children: ReactNode }`; renders `<Label htmlFor={id}>`, the child control, then `hint` (`id={`${id}-hint`}`) and `error` (`id={`${id}-error`}`, `role="alert"`). The caller wires `aria-describedby` / `aria-invalid` on the control from rhf state.

- [ ] **Step 1: Write the failing tests**

`frontend/tests/ui/button.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("renders its label", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });
  it("is disabled and busy while loading", () => {
    render(<Button loading>Save</Button>);
    const b = screen.getByRole("button", { name: /save/i });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute("aria-busy", "true");
  });
});
```

`frontend/tests/ui/field.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

describe("Field", () => {
  it("labels the control and shows an alerting error", () => {
    render(
      <Field id="email" label="Email" error="That email is not right.">
        <Input id="email" />
      </Field>,
    );
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("That email is not right.");
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement**

`frontend/components/ui/button.tsx`:

```tsx
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-[var(--radius)] text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] disabled:opacity-60 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        default: "bg-accent text-accent-fg shadow-[var(--shadow-1)] hover:brightness-95",
        outline: "border border-border bg-surface text-text hover:bg-surface-sunk",
        ghost: "text-text hover:bg-surface-sunk",
        danger: "bg-danger text-danger-fg hover:brightness-95",
        link: "text-accent underline-offset-4 hover:underline p-0 h-auto",
      },
      size: { sm: "h-8 px-3", md: "h-10 px-4", lg: "h-11 px-5", icon: "h-10 w-10" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { loading?: boolean };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <span aria-hidden>…</span> : null}
      {children}
    </button>
  ),
);
Button.displayName = "Button";
```

`frontend/components/ui/input.tsx`:

```tsx
import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Input = forwardRef<HTMLInputElement, ComponentProps<"input">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-[var(--radius)] border border-border bg-surface px-3 text-sm text-text outline-none placeholder:text-text-subtle focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
        "aria-[invalid=true]:border-danger aria-[invalid=true]:ring-[color-mix(in_srgb,var(--danger)_45%,transparent)]",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
```

`frontend/components/ui/label.tsx`:

```tsx
import * as LabelPrimitive from "@radix-ui/react-label";
import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Label = forwardRef<
  HTMLLabelElement,
  ComponentProps<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn("text-sm font-medium text-text", className)}
    {...props}
  />
));
Label.displayName = "Label";
```

`frontend/components/ui/field.tsx`:

```tsx
import type { ReactNode } from "react";

import { Label } from "@/components/ui/label";

export function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-text-subtle">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/ui && pnpm exec tsc --noEmit && pnpm lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ui/button.tsx frontend/components/ui/input.tsx frontend/components/ui/label.tsx frontend/components/ui/field.tsx frontend/tests/ui/
git commit -m "feat(fe): Button / Input / Label / Field primitives"
```

---

## Task 3: Primitives — Card, Skeleton, Spinner, Toast

**Files:**
- Create: `frontend/components/ui/card.tsx`, `skeleton.tsx`, `spinner.tsx`, `toast.tsx`, `toaster.tsx`
- Modify: `frontend/components/ui/button.tsx` (swap the `…` placeholder for `<Spinner size="sm" />`)
- Test: `frontend/tests/ui/card.test.tsx`, `frontend/tests/ui/toast.test.tsx`

**Interfaces — Produces:**
- `Card`, `CardHeader`, `CardTitle`, `CardBody`, `CardFooter` — token-styled `div`s; `CardTitle` renders `<h2>` by default via a `as` prop (`"h2"|"h3"`, default `"h2"`).
- `Skeleton` — `<div className="animate-pulse rounded-[var(--radius)] bg-surface-sunk" />` passing through `className`.
- `Spinner` — `{ size?: "sm"|"md" }` → an SVG with `role="status"` + visually-hidden "Loading"; CSS spin, disabled under `prefers-reduced-motion`.
- `ToastProvider` (wraps `@radix-ui/react-toast` `Provider` + `Viewport`), `useToast()` → `{ toast: (t: { title: string; description?: string; variant?: "default"|"danger" }) => void }`. `Toaster` = `ToastProvider` mounted once at the root; viewport is `aria-live="polite"`, bottom on mobile / bottom-right on `md`.

- [ ] **Step 1: Write the failing tests**

`frontend/tests/ui/card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, CardBody, CardTitle } from "@/components/ui/card";

describe("Card", () => {
  it("renders a titled card", () => {
    render(
      <Card>
        <CardTitle>Profile strength</CardTitle>
        <CardBody>62 / 100</CardBody>
      </Card>,
    );
    expect(screen.getByRole("heading", { name: "Profile strength" })).toBeInTheDocument();
    expect(screen.getByText("62 / 100")).toBeInTheDocument();
  });
});
```

`frontend/tests/ui/toast.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Toaster, useToast } from "@/components/ui/toaster";

function Trigger() {
  const { toast } = useToast();
  return <button onClick={() => toast({ title: "Profile saved" })}>go</button>;
}

describe("toast", () => {
  it("shows a toast when triggered", async () => {
    render(
      <Toaster>
        <Trigger />
      </Toaster>,
    );
    await userEvent.click(screen.getByRole("button", { name: "go" }));
    expect(await screen.findByText("Profile saved")).toBeInTheDocument();
  });
});
```

> Add `@testing-library/user-event` if missing: `pnpm add -D @testing-library/user-event`.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** `card.tsx`, `skeleton.tsx`, `spinner.tsx` as described (token classes only, no logic). `toast.tsx` = the styled Radix `Root`/`Title`/`Description`/`Close`; `toaster.tsx` = a context holding an array of toasts + `useToast`, `<ToastProvider>` renders them, `<Viewport>` fixed-positioned. Then edit `button.tsx`: `import { Spinner } from "@/components/ui/spinner"` and render `{loading ? <Spinner size="sm" /> : null}`.

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/ui && pnpm exec tsc --noEmit && pnpm lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ui/ frontend/tests/ui/ frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat(fe): Card / Skeleton / Spinner / Toast primitives"
```

---

## Task 4: API types + typed endpoints + fetcher upgrade

**Files:**
- Create: `frontend/lib/api/types.ts`, `frontend/lib/api/endpoints.ts`, `frontend/lib/query.ts`
- Modify: `frontend/lib/api/fetcher.ts`
- Test: `frontend/tests/api/endpoints.test.ts`

**Interfaces — Produces:**
- `fetcher.ts`: `type Fetcher = <T>(path: string, init?: RequestInit) => Promise<T>`. `apiFetch<T>(path, init?)` — unchanged behaviour, plus **always** `credentials: "include"`; still throws `ProblemError` (`.code`, `.status`, `.problem`). Exports `apiFetch`, `ProblemError`, `type Fetcher`.
- `types.ts`: `UserOut { id; email; full_name; is_admin; created_at }`, `AuthResponse { access_token; token_type; expires_in; user: UserOut }`, `AccessResponse { access_token; token_type; expires_in }`, `CareerProfile` (all scalar fields + `profile_strength`, `completeness`), `Strength { score; completeness: Record<string,boolean>; missing: string[] }`, `ProfileFull = CareerProfile & { experiences: ItemOut[]; education: ItemOut[]; projects: ItemOut[]; certifications: ItemOut[] }`, `ItemOut = { id: string; order_index: number; source: string; created_at: string; updated_at: string } & Record<string, unknown>`, `Section = "experiences"|"education"|"projects"|"certifications"`.
- `endpoints.ts`: `makeApi(f: Fetcher)` → `{ auth: { register(body), login(body), refresh(), logout(), me(), changePassword(body) }, profile: { get(): Promise<ProfileFull>, update(patch): Promise<CareerProfile>, strength(): Promise<Strength>, items: { list(s: Section): Promise<ItemOut[]>, add(s, body): Promise<ItemOut>, update(s, id, patch): Promise<ItemOut>, remove(s, id): Promise<void>, reorder(s, ids: string[]): Promise<ItemOut[]> } } }`. Every path is `/api/v1/...`.
- `query.ts`: `makeQueryClient()` (`staleTime: 30_000`, `retry: 1`) and `qk = { profile: ["profile"] as const, strength: ["profile","strength"] as const, section: (s: Section) => ["profile", s] as const }`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/api/endpoints.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";

import { makeApi } from "@/lib/api/endpoints";

function recordingFetcher() {
  const calls: { path: string; init?: RequestInit }[] = [];
  const f = vi.fn(async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return {} as unknown;
  });
  return { f, calls };
}

describe("makeApi", () => {
  it("posts login to the right path with a JSON body", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).auth.login({ email: "a@b.com", password: "x" });
    expect(calls[0].path).toBe("/api/v1/auth/login");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      email: "a@b.com",
      password: "x",
    });
  });

  it("reorders a section", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).profile.items.reorder("education", ["b", "a"]);
    expect(calls[0].path).toBe("/api/v1/profile/education/reorder");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ ids: ["b", "a"] });
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** `endpoints.ts` — a small `json(method, body)` helper returning `{ method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }`; each method calls `f<T>(path, ...)`. `fetcher.ts` — add `credentials: "include"` to the `fetch` options.

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/api && pnpm exec tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/ frontend/lib/query.ts frontend/tests/api/
git commit -m "feat(fe): typed API client (auth + profile) and query keys"
```

---

## Task 5: QueryProvider + AuthProvider + root layout

**Files:**
- Create: `frontend/providers/QueryProvider.tsx`, `frontend/providers/AuthProvider.tsx`
- Modify: `frontend/app/layout.tsx`
- Create: `frontend/test/utils.tsx`
- Test: `frontend/tests/auth-provider.test.tsx`

**Interfaces — Produces:**
- `QueryProvider` — `"use client"`; `useState(() => makeQueryClient())`; `<QueryClientProvider>`.
- `AuthProvider` — `"use client"`. State: `status: "loading"|"authed"|"anon"`, `user: UserOut | null`; token in a `useRef<string|null>`. On mount, `bootstrap()`: `apiFetch<AccessResponse>("/api/v1/auth/refresh", { method: "POST" })` → store token → `me()` → `user`, `status="authed"`; any `ProblemError` → `status="anon"`. `authedFetch: Fetcher` = call `apiFetch(path, { ...init, headers: { ...init.headers, Authorization: `Bearer ${tokenRef.current}` } })`; on `ProblemError` 401 → `await bootstrap()` once → retry once → if still 401, `setStatus("anon")` and rethrow. Context value: `{ status, user, api: makeApi(authedFetch), login, register, logout, changePassword }` where `login`/`register` set token+user+status and `logout` calls `auth.logout()` then clears.
- `useAuth()` — throws if outside provider.
- `app/layout.tsx` — `Inter` from `next/font/google` (`variable: "--font-inter"`, applied on `<body>`); wrap: `<QueryProvider><AuthProvider><Toaster>{children}</Toaster></AuthProvider></QueryProvider>`.
- `test/utils.tsx` — `renderWithProviders(ui, { route })` wrapping in a fresh `QueryClientProvider` + a **mock** `AuthProvider` value (pass `authValue` override); `mockNextNavigation()` returning `{ push, replace }` spies via `vi.mock("next/navigation")`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/auth-provider.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/providers/AuthProvider";
import * as fetcher from "@/lib/api/fetcher";

function Probe() {
  const { status, user } = useAuth();
  return <div>{status}:{user?.email ?? "-"}</div>;
}

afterEach(() => vi.restoreAllMocks());

describe("AuthProvider", () => {
  it("bootstraps an authed session from the refresh cookie", async () => {
    const spy = vi.spyOn(fetcher, "apiFetch");
    spy.mockImplementation(async (path: string) => {
      if (path.endsWith("/auth/refresh")) return { access_token: "t", token_type: "bearer", expires_in: 900 } as never;
      if (path.endsWith("/auth/me")) return { id: "1", email: "me@x.com", full_name: "Me", is_admin: false, created_at: "" } as never;
      throw new Error("unexpected " + path);
    });
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText(/loading:/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("authed:me@x.com")).toBeInTheDocument());
  });

  it("falls to anon when refresh fails", async () => {
    const { ProblemError } = fetcher;
    vi.spyOn(fetcher, "apiFetch").mockRejectedValue(new ProblemError("invalid_refresh", 401, {}));
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByText("anon:-")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** the two providers + `app/layout.tsx` wiring + `test/utils.tsx`.

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/auth-provider.test.tsx && pnpm exec tsc --noEmit && pnpm lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/providers/ frontend/app/layout.tsx frontend/test/utils.tsx frontend/tests/auth-provider.test.tsx
git commit -m "feat(fe): QueryProvider + in-memory AuthProvider with refresh-on-401"
```

---

## Task 6: Login + Register screens

**Files:**
- Create: `frontend/components/auth/LoginForm.tsx`, `RegisterForm.tsx`
- Create: `frontend/app/(auth)/layout.tsx`, `(auth)/login/page.tsx`, `(auth)/register/page.tsx`
- Modify: `frontend/app/page.tsx` (CTA `href="/register"` — already correct; confirm)
- Test: `frontend/tests/auth/login-form.test.tsx`, `frontend/tests/auth/register-form.test.tsx`

**Interfaces — Produces:**
- `LoginForm` — `"use client"`; `zod` `{ email: z.string().email(), password: z.string().min(1) }`; `useForm` + `zodResolver`; `onSubmit` → `useAuth().login(values)` → on ok `router.push("/dashboard")`; on `ProblemError`: `invalid_credentials` / `account_disabled` → `setError("root", { message: problem.detail })`; `validation_error` → for each `problem.errors[].loc` last segment, `setError(field, ...)`. Renders `Field` + `Input` + a submit `Button loading={isSubmitting}` + a "Create an account" link.
- `RegisterForm` — same shape; zod `{ full_name: min 1, email: email, password: min 10 }`; calls `useAuth().register`; `email_taken` → `setError("email", { message: "That email is already registered." })`.
- `(auth)/layout.tsx` — full-height centered, `<Card className="w-full max-w-sm">`, brand wordmark above.

- [ ] **Step 1: Write the failing tests**

`frontend/tests/auth/login-form.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/LoginForm";
import { ProblemError } from "@/lib/api/fetcher";
import { renderWithProviders, mockPush } from "@/test/utils";

describe("LoginForm", () => {
  it("submits and redirects on success", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<LoginForm />, { authValue: { login } });
    await userEvent.type(screen.getByLabelText("Email"), "a@b.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-passphrase");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(login).toHaveBeenCalledWith({ email: "a@b.com", password: "correct-passphrase" }));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("shows the server message on bad credentials", async () => {
    const login = vi.fn().mockRejectedValue(
      new ProblemError("invalid_credentials", 401, { detail: "That email or password is not right." }),
    );
    renderWithProviders(<LoginForm />, { authValue: { login } });
    await userEvent.type(screen.getByLabelText("Email"), "a@b.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/not right/i)).toBeInTheDocument();
  });
});
```

`frontend/tests/auth/register-form.test.tsx` — mirror: success calls `register` + pushes `/dashboard`; a rejected `email_taken` shows "already registered" on the Email field.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** the two form components + the three route files. `renderWithProviders`/`mockPush` come from `test/utils.tsx` (extend it here: accept `authValue` partial, default the rest to no-ops; `mockPush` is the `next/navigation` `useRouter().push` spy).

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/auth && pnpm exec tsc --noEmit && pnpm lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/components/auth/ "frontend/app/(auth)/" frontend/test/utils.tsx frontend/tests/auth/
git commit -m "feat(fe): login and register screens with problem+json field errors"
```

---

## Task 7: App shell + auth guard

**Files:**
- Create: `frontend/components/layout/nav-items.ts`, `Sidebar.tsx`, `MobileNav.tsx`, `UserMenu.tsx`, `AppShell.tsx`
- Create: `frontend/components/auth/RequireAuth.tsx`
- Create: `frontend/app/(app)/layout.tsx`
- Test: `frontend/tests/layout/app-shell.test.tsx`, `frontend/tests/auth/require-auth.test.tsx`

**Interfaces — Produces:**
- `nav-items.ts`: `NAV: { href: string; label: string; icon: LucideIcon; ready: boolean }[]` — `/dashboard` "Home" (ready), `/jobs` "Jobs" (false), `/applications` "Applications" (false), `/assistant` "Mana AI" (false), `/profile` "Profile" (ready). Not-ready items render disabled with a "Soon" chip.
- `Sidebar` — `"use client"`; `usePathname()` for the active item (`aria-current="page"`); brand wordmark at top; `<UserMenu>` pinned bottom. `hidden md:flex`, fixed width `w-60`.
- `MobileNav` — `"use client"`; `md:hidden` fixed bottom bar; icon + label per ready item; active state.
- `UserMenu` — shows `useAuth().user?.email`; a "Sign out" `Button variant="ghost"` → `await logout()` → `router.push("/login")`.
- `AppShell` — `{ children }`; grid: sidebar + `<main className="mx-auto w-full max-w-3xl px-4 py-8 md:py-10">`; `MobileNav` after main; adds `pb-20 md:pb-0` so the bottom bar never covers content.
- `RequireAuth` — `"use client"`; `useAuth()`: `loading` → centered `<Spinner />` full height; `anon` → `useEffect(() => router.replace("/login"), [])` and render `null`; `authed` → `<>{children}</>`.
- `(app)/layout.tsx` — `<RequireAuth><AppShell>{children}</AppShell></RequireAuth>`.

- [ ] **Step 1: Write the failing tests**

`frontend/tests/layout/app-shell.test.tsx`:

```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { renderWithProviders } from "@/test/utils";

describe("AppShell", () => {
  it("renders the primary nav and marks the active route", () => {
    renderWithProviders(<AppShell>hi</AppShell>, {
      route: "/profile",
      authValue: { user: { email: "me@x.com" } },
    });
    expect(screen.getAllByRole("link", { name: /profile/i }).length).toBeGreaterThan(0);
    const active = screen.getAllByRole("link", { name: /profile/i })[0];
    expect(active).toHaveAttribute("aria-current", "page");
  });
});
```

`frontend/tests/auth/require-auth.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { renderWithProviders, mockReplace } from "@/test/utils";

describe("RequireAuth", () => {
  it("renders children when authed", () => {
    renderWithProviders(<RequireAuth>secret</RequireAuth>, { authValue: { status: "authed" } });
    expect(screen.getByText("secret")).toBeInTheDocument();
  });
  it("redirects to /login when anon", async () => {
    renderWithProviders(<RequireAuth>secret</RequireAuth>, { authValue: { status: "anon" } });
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** Extend `test/utils.tsx` with `mockReplace` and a `route` option (sets `usePathname` mock return).

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/layout tests/auth/require-auth.test.tsx && pnpm exec tsc --noEmit && pnpm lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/components/layout/ frontend/components/auth/RequireAuth.tsx "frontend/app/(app)/layout.tsx" frontend/test/utils.tsx frontend/tests/layout/ frontend/tests/auth/require-auth.test.tsx
git commit -m "feat(fe): app shell (sidebar + mobile nav) behind a client auth guard"
```

---

## Task 8: StrengthMeter + Dashboard

**Files:**
- Create: `frontend/components/common/StrengthMeter.tsx`, `frontend/components/common/ErrorState.tsx`
- Create: `frontend/app/(app)/dashboard/page.tsx`
- Test: `frontend/tests/common/strength-meter.test.tsx`, `frontend/tests/dashboard.test.tsx`

**Interfaces — Produces:**
- `StrengthMeter` — `{ score: number; missing: string[] }`. A labelled bar: `role="progressbar"` `aria-valuenow={score}` `aria-valuemin=0` `aria-valuemax=100` `aria-label="Profile strength"`; the number in `font-[var(--font-inter)] tabular-nums`; band colour from `--positive` (≥75) / `--warning` (≥40) / `--danger` (<40) via a `style` var, never a hard hex; a `<details>` "How this is calculated" with a one-line explanation; then `missing` as a `<ul>` (each "△ " + text). If `missing` is empty, a positive "Your profile is complete." line.
- `ErrorState` — `{ title?: string; onRetry?: () => void }` → card with message + a "Try again" `Button` when `onRetry` given.
- `dashboard/page.tsx` — `"use client"`; `useAuth().user`, `useApi()`, `useQuery({ queryKey: qk.strength, queryFn: () => api.profile.strength() })`. Greeting: `Good ${partOfDay()}, ${firstName} 👋` + spec line "Here's where you stand in your career journey." Loading → `<Skeleton>` blocks. Error → `<ErrorState onRetry={refetch} />`. Success → `<StrengthMeter>` + if `score < 100` a `<Link href="/profile">` "Complete your profile →" styled as `buttonVariants({ variant: "outline" })`.

- [ ] **Step 1: Write the failing tests**

`frontend/tests/common/strength-meter.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StrengthMeter } from "@/components/common/StrengthMeter";

describe("StrengthMeter", () => {
  it("exposes the score to assistive tech and lists gaps", () => {
    render(<StrengthMeter score={38} missing={["Add your work experience"]} />);
    const bar = screen.getByRole("progressbar", { name: /profile strength/i });
    expect(bar).toHaveAttribute("aria-valuenow", "38");
    expect(screen.getByText(/Add your work experience/)).toBeInTheDocument();
  });
  it("celebrates a complete profile", () => {
    render(<StrengthMeter score={100} missing={[]} />);
    expect(screen.getByText(/complete/i)).toBeInTheDocument();
  });
});
```

`frontend/tests/dashboard.test.tsx` — `renderWithProviders(<DashboardPage/>, { authValue: { user: { full_name: "Ada Lovelace" } }, api: { profile: { strength: async () => ({ score: 20, completeness: {}, missing: ["Add a project"] }) } } })` → finds `/Good .*, Ada/` and the progressbar and a `link` to `/profile`.

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.** Extend `test/utils.tsx` so `renderWithProviders` accepts an `api` override that `useApi()` returns.

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/common tests/dashboard.test.tsx && pnpm exec tsc --noEmit && pnpm lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/components/common/ "frontend/app/(app)/dashboard/" frontend/test/utils.tsx frontend/tests/common/ frontend/tests/dashboard.test.tsx
git commit -m "feat(fe): strength meter + dashboard landing"
```

---

## Task 9: Profile scalar form

**Files:**
- Create: `frontend/components/profile/ProfileScalarForm.tsx`
- Test: `frontend/tests/profile/scalar-form.test.tsx`

**Interfaces — Produces:**
- `ProfileScalarForm` — `{ profile: CareerProfile }`. `zod` schema mirrors `CareerProfileUpdate`: `location` (opt str), three URL fields (`z.string().url().or(z.literal("")).optional()`), `preferred_roles`/`preferred_locations` (a comma-separated `<Input>` ⇄ `string[]`), `work_modes` (checkbox group `remote|hybrid|onsite`), `expected_salary_min`/`_max` (`z.coerce.number().int().min(0).optional()`), `salary_currency` (opt, `maxLength 3`), `salary_period` (`select` `year|month|""`), `years_experience` (`z.coerce.number().min(0).max(70).optional()`), `seniority` (`select` of the six), `career_goals` (`<textarea>`). `defaultValues` from `profile`. On submit: build a patch of **dirty fields only** (`formState.dirtyFields`), `api.profile.update(patch)` → `queryClient.setQueryData(qk.profile, merge)` + `invalidateQueries(qk.strength)` + `toast({ title: "Profile saved" })`. Field errors from a rejected `validation_error` map by `loc`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/profile/scalar-form.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProfileScalarForm } from "@/components/profile/ProfileScalarForm";
import { renderWithProviders } from "@/test/utils";

const base = { id: "p1", location: "Berlin", career_goals: "", github_url: null } as never;

describe("ProfileScalarForm", () => {
  it("prefills from the profile and saves only what changed", async () => {
    const update = vi.fn().mockResolvedValue({});
    renderWithProviders(<ProfileScalarForm profile={base} />, {
      api: { profile: { update } },
    });
    const goals = screen.getByLabelText(/career goals/i);
    expect(screen.getByLabelText(/location/i)).toHaveValue("Berlin");
    await userEvent.type(goals, "Ship models.");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith({ career_goals: "Ship models." }),
    );
  });

  it("rejects a non-URL github link", async () => {
    renderWithProviders(<ProfileScalarForm profile={base} />, { api: { profile: { update: vi.fn() } } });
    await userEvent.type(screen.getByLabelText(/github/i), "not a url");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/valid url/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/profile/scalar-form.test.tsx && pnpm exec tsc --noEmit && pnpm lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/components/profile/ProfileScalarForm.tsx frontend/tests/profile/scalar-form.test.tsx
git commit -m "feat(fe): career-profile scalar editor (dirty-field PUT + rescored)"
```

---

## Task 10: Sub-entity editors (generic, four sections)

**Files:**
- Create: `frontend/components/profile/subentity-config.ts`, `SubEntityForm.tsx`, `SubEntityList.tsx`
- Test: `frontend/tests/profile/subentity-list.test.tsx`

**Interfaces — Produces:**
- `subentity-config.ts`: `FieldSpec = { name: string; label: string; type: "text"|"url"|"date"|"textarea"|"chips"|"checkboxes"; options?: string[]; required?: boolean }`. `CONFIG: Record<Section, { singular: string; addLabel: string; fields: FieldSpec[]; summary: (item: ItemOut) => string }>` — e.g. `experiences`: fields `company*`, `title*`, `employment_type`, `start_date` (date), `end_date` (date), `is_current` (checkbox), `location`, `description` (textarea), `highlights` (chips), `tech` (chips); `summary: (i) => `${i.title} · ${i.company}``. The other three per the Phase 1b schema (`education`: institution*, degree, field, dates, grade; `projects`: name*, description, url, dates, highlights, tech; `certifications`: name*, issuer, dates, credential_id, url).
- `SubEntityForm` — `{ section: Section; item?: ItemOut; onDone: () => void }`; builds a `zod` object from `CONFIG[section].fields`; `useForm`; submit → `api.profile.items.add(section, values)` or `.update(section, item.id, dirty)` → `invalidateQueries(qk.section(section))` + `invalidateQueries(qk.strength)` + `onDone()`.
- `SubEntityList` — `{ section: Section }`; `useQuery({ queryKey: qk.section(section), queryFn: () => api.profile.items.list(section) })`. Renders a `<Card>` per item (`CONFIG.summary`) with **Edit** (toggles inline `SubEntityForm`), **Delete** (`items.remove` + invalidate + toast), **Move up / Move down** (compute the reordered id array, `items.reorder`, optimistic `setQueryData`). An **"Add {singular}"** `Button` toggles a create `SubEntityForm`. Loading → 2 `<Skeleton>` rows. Empty → `<EmptyState title={`No ${plural} yet.`} description="Add one to strengthen your profile." />`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/profile/subentity-list.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SubEntityList } from "@/components/profile/SubEntityList";
import { renderWithProviders } from "@/test/utils";

function api(over: Record<string, unknown> = {}) {
  return {
    profile: {
      items: {
        list: vi.fn().mockResolvedValue([
          { id: "a", order_index: 0, title: "Eng", company: "Acme" },
          { id: "b", order_index: 1, title: "Sr Eng", company: "Beta" },
        ]),
        add: vi.fn().mockResolvedValue({}),
        update: vi.fn().mockResolvedValue({}),
        remove: vi.fn().mockResolvedValue(undefined),
        reorder: vi.fn().mockResolvedValue([]),
        ...over,
      },
    },
  };
}

describe("SubEntityList", () => {
  it("lists items and reorders", async () => {
    const a = api();
    renderWithProviders(<SubEntityList section="experiences" />, { api: a });
    expect(await screen.findByText(/Eng · Acme/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: /move down/i })[0]);
    await waitFor(() =>
      expect(a.profile.items.reorder).toHaveBeenCalledWith("experiences", ["b", "a"]),
    );
  });

  it("deletes an item", async () => {
    const a = api();
    renderWithProviders(<SubEntityList section="experiences" />, { api: a });
    await screen.findByText(/Eng · Acme/);
    await userEvent.click(screen.getAllByRole("button", { name: /delete/i })[0]);
    await waitFor(() => expect(a.profile.items.remove).toHaveBeenCalledWith("experiences", "a"));
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run — expect pass.**

Run: `cd frontend && pnpm test run tests/profile/subentity-list.test.tsx && pnpm exec tsc --noEmit && pnpm lint`

- [ ] **Step 5: Commit**

```bash
git add frontend/components/profile/ frontend/tests/profile/subentity-list.test.tsx
git commit -m "feat(fe): generic sub-entity editors (list / add / edit / delete / reorder)"
```

---

## Task 11: Profile page wiring + verification & report

**Files:**
- Create: `frontend/app/(app)/profile/page.tsx`
- Modify: `frontend/app/page.tsx` (confirm CTA), `docs/superpowers/plans/2026-08-31-phase-1c-frontend-shell.md` (report)
- Test: `frontend/tests/profile-page.test.tsx`

**Interfaces — Produces:**
- `profile/page.tsx` — `"use client"`; `useQuery(qk.profile → api.profile.get())` and `useQuery(qk.strength → api.profile.strength())`. Layout: page title "Your profile", `<StrengthMeter>` card, `<ProfileScalarForm profile={profile} />`, then `<section>` per section with an `<h2>` and `<SubEntityList section=… />` for `experiences`, `education`, `projects`, `certifications`. Loading → `<Skeleton>` blocks. Error → `<ErrorState onRetry={refetch} />`.

- [ ] **Step 1: Write the failing test**

`frontend/tests/profile-page.test.tsx`:

```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProfilePage from "@/app/(app)/profile/page";
import { renderWithProviders } from "@/test/utils";

const profile = {
  id: "p1", location: "Berlin", profile_strength: 20, completeness: {},
  experiences: [], education: [], projects: [], certifications: [],
} as never;

it("renders every profile section", async () => {
  renderWithProviders(<ProfilePage />, {
    api: {
      profile: {
        get: vi.fn().mockResolvedValue(profile),
        strength: vi.fn().mockResolvedValue({ score: 20, completeness: {}, missing: ["Add a project"] }),
        items: { list: vi.fn().mockResolvedValue([]) },
      },
    },
  });
  expect(await screen.findByRole("heading", { name: /your profile/i })).toBeInTheDocument();
  for (const s of ["Experience", "Education", "Projects", "Certifications"]) {
    expect(screen.getByRole("heading", { name: new RegExp(s, "i") })).toBeInTheDocument();
  }
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement** the page.

- [ ] **Step 4: Full frontend gate**

Run: `cd frontend && pnpm install --frozen-lockfile && pnpm lint && pnpm exec tsc --noEmit && pnpm test run`
Expected: install clean against the committed lock; lint clean; tsc clean; **all Vitest suites green** (Phase 0's 2 + Phase 1c's new files).

- [ ] **Step 5: Fill the completion report below, commit**

```bash
git add "frontend/app/(app)/profile/" frontend/tests/profile-page.test.tsx docs/superpowers/plans/2026-08-31-phase-1c-frontend-shell.md
git commit -m "feat(fe): profile page wiring + Phase 1c report"
```

---

## Phase 1c completion report (fill in when done)

- **What changed:**
  - **Task 1 — deps / tokens / `cn()`:** added `class-variance-authority`, `clsx`, `tailwind-merge`, `@radix-ui/react-label`, `@radix-ui/react-toast`, `react-hook-form`, `zod`, `@hookform/resolvers`, `lucide-react` (+ `@testing-library/user-event` dev); new light semantic tokens (`--accent-soft`, `--positive-soft`, `--warning-soft`, `--danger-soft`, `--danger-fg`, `--surface-sunk`, `--text-subtle`) mapped into `@theme inline`; `cn()` = `twMerge(clsx(...))`.
  - **Task 2 — form primitives:** `Button` (cva `buttonVariants`, `loading` → disabled + `aria-busy` + spinner), `Input` (`aria-invalid` red ring), `Label` (Radix), `Field` (`<Label htmlFor>` + hint + `role="alert"` error, id-wired).
  - **Task 3 — surface primitives:** `Card`/`CardHeader`/`CardTitle`(`as` h2|h3)/`CardBody`/`CardFooter`, `Skeleton`, `Spinner` (`role="status"`, reduced-motion aware), `Toast`/`Toaster` + `useToast()` with an `aria-live="polite"` viewport.
  - **Task 4 — API layer:** `lib/api/types.ts` (TS mirrors of the 1a/1b models), `makeApi(fetcher)` → typed `auth` + `profile` (+ `profile.items` list/add/update/remove/reorder) on `/api/v1/...`, `fetcher` now always sends `credentials: "include"`, `makeQueryClient()` (`staleTime 30s`, `retry 1`) + `qk` key registry.
  - **Task 5 — providers + session:** `QueryProvider`; in-memory `AuthProvider` (access token in a `useRef`, refresh-cookie `bootstrap()`, single 401 → refresh → retry → `anon`), `useAuth()`; root `layout.tsx` wires Inter + `QueryProvider → AuthProvider → Toaster`; `test/utils.tsx` `renderWithProviders` (+ `next/navigation` mock, `mockPush`/`mockReplace`).
  - **Task 6 — auth screens:** `LoginForm` / `RegisterForm` (rhf + zod, `problem+json` `code`/`errors[].loc` → root + field errors, redirect to `/dashboard`); `(auth)` route group (centered card layout + `login` / `register` pages).
  - **Task 7 — app shell + guard:** `nav-items` (Home/Jobs/Applications/Mana AI/Profile; not-ready items disabled with a "Soon" chip), `Sidebar` (`hidden md:flex`, `aria-current="page"`), `MobileNav` (`md:hidden` bottom bar), `UserMenu` (sign out → `/login`), `AppShell`; client `RequireAuth` (loading → spinner, `anon` → `router.replace("/login")`); `(app)/layout.tsx`.
  - **Task 8 — strength + dashboard:** `StrengthMeter` (`role="progressbar"` 0–100, tabular numerals, band colour from `--positive`/`--warning`/`--danger` via a CSS var, `<details>` "How this is calculated", `missing[]` gap list / complete state), `ErrorState` (`title?` + "Try again"), `(app)/dashboard/page.tsx` (greeting + strength query + nudge link).
  - **Task 9 — scalar editor:** `ProfileScalarForm` (zod mirror of `CareerProfileUpdate`, CSV ⇄ `string[]`, work-mode checkboxes, coerced numbers/selects); submit builds a **dirty-fields-only** patch → `api.profile.update` → `setQueryData(qk.profile)` merge + `invalidateQueries(qk.strength)` + "Profile saved" toast; `validation_error` mapped by `loc`.
  - **Task 10 — sub-entity editors:** `subentity-config.ts` (field specs + one-line summaries for all four sections, mirroring the 1b schemas), generic `SubEntityForm` (zod built from the config, add / edit), `SubEntityList` (per-item `Card`, add, inline edit, delete, optimistic move up / move down posting the full id order, `EmptyState` when empty).
  - **Task 11 — profile page + gate:** `(app)/profile/page.tsx` — `<h1>Your profile</h1>`, a `StrengthMeter` card, `ProfileScalarForm`, then four `<section>`s (`<h2>` "Work experience" / "Education" / "Projects" / "Certifications") each with a `SubEntityList`; profile-query loading → `Skeleton` blocks, error → `ErrorState onRetry={refetch}`, strength query loads independently (inline note on failure). Ran the full frontend gate; filled this report.
- **Why:** this is the frontend half of spec Phase 1 — it makes *login → profile editable → strength shown* real, and establishes the design-system primitives, the auth session model, and the app shell that every later screen builds on.
- **Files changed:** 35 new source files + `frontend/test/utils.tsx` (test helper) + 16 new Vitest spec files under `frontend/tests/`. 6 existing files modified: `frontend/app/globals.css`, `frontend/app/layout.tsx`, `frontend/lib/api/fetcher.ts`, `frontend/package.json`, `frontend/pnpm-lock.yaml`, `frontend/styles/tokens.css`. `frontend/app/page.tsx` already pointed its CTA at `/register` — confirmed, left unchanged. This plan doc is added to git in the Task 11 commit (it was untracked on the branch).
- **How to test:** `cd frontend && pnpm test run` (units); `docker compose up` then visit `http://localhost:3000` for the real flow.
- **Regression check:** Phase 0's `landing` + `EmptyState` tests still green; full gate run 2026-08-31 — `pnpm install --frozen-lockfile` clean ("Already up to date"), `pnpm lint` clean ("No ESLint warnings or errors"), `pnpm exec tsc --noEmit` clean (exit 0), `pnpm test run` **18 files / 30 tests, all green**. Backend untouched.
- **Baseline:** 18 frontend test files / 30 tests (Vitest, jsdom) — Phase 0's 2 (`tests/landing.test.tsx`, `tests/EmptyState.test.tsx`) + Phase 1c's 16 (one spec per task, plus the extra `require-auth` and per-primitive specs).
- **Deviations:**
  - **shadcn CLI skipped** — every primitive is hand-rolled on `cva` + `clsx` + `tailwind-merge` (+ Radix `Label` / `Toast`); the dependency set and component API are the same as a shadcn scaffold. (Flagged in Architecture / Self-Review §1.)
  - **`test/utils.tsx` mounts `<Toaster>`** around every `renderWithProviders` render (mirrors `app/layout.tsx`) so `useToast()` resolves in component tests without each test re-wrapping — introduced in refactor commit `cb57f06`.
  - **`CareerProfile` type extended in the Task 9 fix** (commit `b1b6451` / `cb57f06`) to carry every scalar column (`github_url`, `linkedin_url`, `portfolio_url`, `preferred_roles`, `work_modes`, `expected_salary_min/_max`, `salary_currency`, `salary_period`, `years_experience`, `seniority`, `career_goals`) so `ProfileScalarForm` prefills without casts.
  - **Profile-page heading names fixed by ruling:** page title is `<h1>` "Your profile"; the four section headings are `<h2>` with the exact strings "Work experience" / "Education" / "Projects" / "Certifications". `SubEntityList`'s empty-state `<h2>` ("No experiences yet." …) would otherwise collide with a case-insensitive regex match, so `tests/profile-page.test.tsx` asserts each section heading by exact name.
- **Not verified here:** visual and interaction review needs a running stack (Docker → API + DB). Unit tests cover behaviour and a11y wiring, not layout/spacing/visual polish — a design pass on the running app is a follow-up.

---

## Self-Review

**1. Spec coverage (frontend slice of §9 Phase 1 + §7 / §7.7 / §19 / §20 / §21 / §22):**
- Design system + shadcn-style primitives (§22) → Tasks 1–3. ✓ (CLI skipped; deps + approach identical — noted in Architecture.)
- Design tokens (§7.7) → Task 1 (light only; names stable for a later dark set). ✓
- Authentication UI (login / register), session model, guard (§7.4 auth handling) → Tasks 5–7. ✓
- App shell: sidebar + mobile bottom nav Home/Jobs/Applications/Mana AI/Profile (§20) → Task 7. ✓ (Jobs/Applications/Mana AI are present but disabled with a "Soon" chip — their screens are Phases 4/11/7.)
- Profile editor: scalars + four sub-entity lists + reorder, strength shown (§9 done-when) → Tasks 8–11. ✓
- Calculated-score trust treatment (§7.3) → `StrengthMeter` in Task 8 (mono numerals, meter, "how this is calculated"). ✓
- TanStack Query for server state, rhf + zod forms mapping `problem+json` (§7.2) → Tasks 4–6, 9, 10. ✓
- Loading skeletons / empty states / error+retry / toasts (§7.5) → Tasks 3, 8, 10, 11. ✓
- Accessibility: labels, focus rings via `--ring`, `aria-current`, `role="alert"` / `progressbar`, `aria-live` toasts, `prefers-reduced-motion` (§21) → threaded through Tasks 2, 3, 7, 8. ✓
- Microcopy (§19) → "Save" / "Profile saved" / "Your career workspace is ready." / "Sign in" throughout. ✓
- **Deferred (later phases, flagged):** Mana AI docked panel (§7.4 / §16 → Phase 7); real dashboard widgets — best matches, recent applications, AI activity (§8 → Phases 5/11/7); dark theme toggle (§7.7 → later); résumé workspace 3-pane (§11 → Phase 8); full drag-and-drop reorder (up/down buttons ship now).

**2. Placeholder scan:** Tasks 1–8 carry literal code for the mechanism-bearing units (`cn`, primitives, `makeApi`, `AuthProvider`, `StrengthMeter`) and a concrete test for every task. The form-heavy Tasks 6, 9, 10 give the full interface contract + zod shape + the test, and describe the JSX rather than transcribing every field row — the repetition there is mechanical and the one row pattern is fixed by the primitives in Tasks 2–3. No "TBD".

**3. Type consistency:**
- `Fetcher` (Task 4) is consumed by `makeApi` (Task 4) and `AuthProvider.authedFetch` (Task 5).
- `makeApi(...)` shape (Task 4) is the `api` object surfaced by `useAuth()` / `useApi()` and overridden in every component test via `renderWithProviders({ api })`.
- `Section = "experiences"|"education"|"projects"|"certifications"` (Task 4) keys `qk.section`, `CONFIG`, and every `items.*` call — same four strings as the backend's `SUBENTITY_MODELS` / `SUBENTITY_SCHEMAS`.
- `Strength { score; completeness; missing }` (Task 4) is exactly what `GET /api/v1/profile/strength` returns (backend Phase 1b `StrengthOut`) and what `<StrengthMeter>` consumes.
- `ProblemError` (`.code`, `.status`, `.problem`) from the existing `fetcher.ts` is the single error type every form catches.
- `renderWithProviders(ui, { route?, authValue?, api? })` + `mockPush` / `mockReplace` — defined in Task 5's `test/utils.tsx`, extended (never renamed) in Tasks 6, 7, 8.
- `buttonVariants` (Task 2) reused for link-styled `<Link>`s in Tasks 6 and 8.

**4. Ambiguity check:** the access token is **in memory only** — never `localStorage`/cookie-readable-by-JS (Task 5); route protection is a **client** `RequireAuth` component, not `middleware.ts`, because the token is not visible to middleware (Task 7). `PUT /profile` sends **only dirty fields** (Task 9). Reorder is **up/down buttons** posting the full reordered id list, not drag-and-drop (Task 10, flagged in Self-Review §1).

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-08-31-phase-1c-frontend-shell.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks.
**2. Inline Execution** — `superpowers:executing-plans`, batched with checkpoints.

**Environment note:** `pnpm` + Node work locally, so every task's Vitest / `tsc` / `lint` gate runs here, and CI's `frontend` job is the backstop. What is **not** possible without a running stack (Docker → API + Postgres): seeing the screens render, checking layout/spacing at 375px and desktop, and exercising the real login→profile→strength flow end to end. Plan a visual/interaction pass on the running app as a follow-up before calling Phase 1 done.
