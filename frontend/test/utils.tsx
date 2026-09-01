/**
 * Shared test helper for Mana Career component tests (Tasks 6-11 build on this).
 *
 * Recommended import order — helper first, component second:
 *
 *   import { renderWithProviders, mockPush } from "@/test/utils";
 *   import { LoginForm } from "@/components/auth/LoginForm";
 *
 * That lets the `vi.mock("next/navigation")` below register before the
 * component pulls the router in. `renderWithProviders` ALSO mounts the real
 * Next.js router contexts, so `useRouter()` / `usePathname()` still resolve
 * even if the imports are reversed — the mock is belt, the contexts braces.
 */
import type { ReactElement, ReactNode } from "react";

import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import {
  AppRouterContext,
  type AppRouterInstance,
} from "next/dist/shared/lib/app-router-context.shared-runtime";
import {
  PathnameContext,
  SearchParamsContext,
} from "next/dist/shared/lib/hooks-client-context.shared-runtime";
import { vi } from "vitest";

import { Toaster } from "@/components/ui/toaster";
import { makeQueryClient } from "@/lib/query";
import { AuthContext, type AuthContextValue } from "@/providers/AuthProvider";

// Re-export straight from the source module: re-exporting the imported local
// binding (`export { AuthContext }`) trips a Vite SSR live-binding quirk where
// consumers read it as `undefined`.
export { AuthContext } from "@/providers/AuthProvider";
export type { AuthContextValue };

/* -------------------------------------------------------------------------- */
/*  next/navigation mock                                                       */
/* -------------------------------------------------------------------------- */

const mockNav = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  prefetch: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  redirect: vi.fn(),
  route: "/" as string,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockNav.push,
    replace: mockNav.replace,
    prefetch: mockNav.prefetch,
    back: mockNav.back,
    forward: mockNav.forward,
    refresh: mockNav.refresh,
  }),
  usePathname: () => mockNav.route,
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
  useSelectedLayoutSegment: () => null,
  useSelectedLayoutSegments: () => [],
  redirect: (...args: unknown[]) => mockNav.redirect(...args),
  permanentRedirect: (...args: unknown[]) => mockNav.redirect(...args),
  notFound: () => undefined,
  RedirectType: { push: "push", replace: "replace" },
}));

/** `useRouter().push` spy — assert on it after an action that should navigate. */
export const mockPush = mockNav.push;
/** `useRouter().replace` spy — used by `RequireAuth` and sign-out. */
export const mockReplace = mockNav.replace;
/** `redirect()` / `permanentRedirect()` spy. */
export const mockRedirect = mockNav.redirect;

/**
 * Clears the router spies and resets the mocked pathname to "/". Call from a
 * `beforeEach` if a suite renders more than once; `vi.clearAllMocks()` in a
 * global hook works too (it clears these spies without dropping the mock).
 */
export function resetRouterMocks(): void {
  mockNav.push.mockClear();
  mockNav.replace.mockClear();
  mockNav.prefetch.mockClear();
  mockNav.back.mockClear();
  mockNav.forward.mockClear();
  mockNav.refresh.mockClear();
  mockNav.redirect.mockClear();
  mockNav.route = "/";
}

const fakeRouter: AppRouterInstance = {
  push: mockNav.push,
  replace: mockNav.replace,
  prefetch: mockNav.prefetch,
  back: mockNav.back,
  forward: mockNav.forward,
  refresh: mockNav.refresh,
};

/* -------------------------------------------------------------------------- */
/*  mock auth context value                                                    */
/* -------------------------------------------------------------------------- */

type DeepPartial<T> = T extends (...args: never[]) => unknown
  ? T
  : T extends readonly unknown[]
    ? T
    : T extends object
      ? { [K in keyof T]?: DeepPartial<T[K]> }
      : T;

/** Anything a test may override on the auth context, nested + all optional. */
export type AuthValueOverride = DeepPartial<AuthContextValue>;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  if (typeof v !== "object" || v === null) return false;
  const proto: unknown = Object.getPrototypeOf(v);
  return proto === Object.prototype || proto === null;
}

function deepMerge<T>(base: T, override: unknown): T {
  if (override === undefined) return base;
  if (!isPlainObject(base) || !isPlainObject(override)) {
    return override as T;
  }
  const out: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (value === undefined) continue;
    out[key] =
      isPlainObject(out[key]) && isPlainObject(value)
        ? deepMerge(out[key], value)
        : value;
  }
  return out as T;
}

export interface RenderWithProvidersOptions {
  /** Value returned by the mocked `usePathname()` / `PathnameContext`. */
  route?: string;
  /** Partial override of the mock auth context (deep-merged over defaults). */
  authValue?: AuthValueOverride;
  /** Becomes `useAuth().api`; a bare `{}` is fine — pass the methods a test needs. */
  api?: unknown;
}

/**
 * Builds a complete `AuthContextValue` from sensible test defaults deep-merged
 * with `opts.authValue`. Defaults: `status: "authed"`, `user: null`, the five
 * actions (`login` / `register` / `logout` / `changePassword` / `authedStream`)
 * are `vi.fn()`s resolving `undefined`, and `api` is `opts.api ?? {}`.
 */
export function makeAuthValue(
  opts: Pick<RenderWithProvidersOptions, "authValue" | "api"> = {},
): AuthContextValue {
  const defaults: AuthContextValue = {
    status: "authed",
    user: null,
    api: (opts.api ?? {}) as AuthContextValue["api"],
    authedStream: vi.fn(async () => new Response(null, { status: 500 })),
    login: vi.fn(async () => {}),
    register: vi.fn(async () => {}),
    logout: vi.fn(async () => {}),
    changePassword: vi.fn(async () => {}),
  };
  return deepMerge(defaults, opts.authValue);
}

/* -------------------------------------------------------------------------- */
/*  renderWithProviders                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Renders `ui` inside a fresh `QueryClientProvider` (new client every call),
 * the Next router contexts (seeded with the `mockPush` / `mockReplace` spies
 * and `opts.route`), a mock `AuthContext` whose value is `makeAuthValue(opts)`,
 * and a `<Toaster>` (mirrors `app/layout.tsx`, so `useToast()` resolves).
 * Returns the Testing Library render result.
 */
export function renderWithProviders(
  ui: ReactElement,
  opts: RenderWithProvidersOptions = {},
): RenderResult {
  const route = opts.route ?? "/";
  mockNav.route = route;
  mockNav.push.mockClear();
  mockNav.replace.mockClear();
  mockNav.redirect.mockClear();

  const queryClient = makeQueryClient();
  const authValue = makeAuthValue(opts);

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AppRouterContext.Provider value={fakeRouter}>
          <PathnameContext.Provider value={route}>
            <SearchParamsContext.Provider value={new URLSearchParams()}>
              <AuthContext.Provider value={authValue}>
                <Toaster>{children}</Toaster>
              </AuthContext.Provider>
            </SearchParamsContext.Provider>
          </PathnameContext.Provider>
        </AppRouterContext.Provider>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper });
}
