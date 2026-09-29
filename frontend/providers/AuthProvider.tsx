"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { makeApi } from "@/lib/api/endpoints";
import { apiFetch, ProblemError, type Fetcher } from "@/lib/api/fetcher";
import type { AccessResponse, AuthResponse, UserOut } from "@/lib/api/types";
import { API_BASE_URL } from "@/lib/env";

export type AuthStatus = "loading" | "authed" | "anon";

type Api = ReturnType<typeof makeApi>;

export interface AuthContextValue {
  status: AuthStatus;
  user: UserOut | null;
  api: Api;
  authedStream: (path: string, init?: RequestInit) => Promise<Response>;
  login: (body: { email: string; password: string }) => Promise<void>;
  register: (body: {
    email: string;
    password: string;
    full_name: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (body: {
    current_password: string;
    new_password: string;
  }) => Promise<void>;
}

/** Name of the cross-tab Web Lock that serializes token refreshes. */
export const REFRESH_LOCK = "mana-career-token-refresh";

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within <AuthProvider>");
  }
  return ctx;
}

/**
 * Holds the access token in memory only (a `useRef`, never storage) and keeps
 * `{ status, user }` in sync with it.
 *
 * On mount it calls `bootstrap()`: the browser still holds the httpOnly refresh
 * cookie, so `POST /auth/refresh` mints a fresh access token which is then used
 * to load the current user. Any `ProblemError` there means "not signed in".
 *
 * `authedFetch` injects `Authorization: Bearer <token>` and, on a 401, does a
 * single silent token refresh + retry before giving up and going `anon`.
 *
 * Refreshes are single-flight: every request that hits a 401 at the same time
 * awaits one shared `POST /auth/refresh`, and a Web Lock serializes refreshes
 * across tabs (they share the refresh cookie). Rotating the same refresh token
 * twice would otherwise look like token theft to the server.
 *
 * `authedStream` is the same bearer + one-refresh-retry dance but returns the
 * raw `Response` (body never read) so callers can stream it — e.g. an SSE hook
 * that cannot set an `Authorization` header via `EventSource`.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const tokenRef = useRef<string | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserOut | null>(null);

  const refreshInFlight = useRef<Promise<void> | null>(null);

  const refreshAccess = useCallback((): Promise<void> => {
    if (refreshInFlight.current) return refreshInFlight.current;
    const doRefresh = async () => {
      const access = await apiFetch<AccessResponse>("/api/v1/auth/refresh", {
        method: "POST",
      });
      tokenRef.current = access.access_token;
    };
    const locks =
      typeof navigator !== "undefined" && "locks" in navigator
        ? navigator.locks
        : undefined;
    const run = locks ? locks.request(REFRESH_LOCK, doRefresh) : doRefresh();
    const shared = Promise.resolve(run).finally(() => {
      refreshInFlight.current = null;
    });
    refreshInFlight.current = shared;
    return shared;
  }, []);

  const bootstrap = useCallback(async () => {
    await refreshAccess();
    const me = await apiFetch<UserOut>("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${tokenRef.current}` },
    });
    setUser(me);
    setStatus("authed");
  }, [refreshAccess]);

  const authedFetch = useCallback(
    <T,>(path: string, init?: RequestInit): Promise<T> => {
      const withAuth = (): Promise<T> =>
        apiFetch<T>(path, {
          ...init,
          headers: {
            ...(init?.headers ?? {}),
            Authorization: `Bearer ${tokenRef.current}`,
          },
        });

      return withAuth().catch(async (err: unknown) => {
        if (!(err instanceof ProblemError) || err.status !== 401) {
          throw err;
        }
        try {
          await refreshAccess();
        } catch (refreshErr) {
          setStatus("anon");
          throw refreshErr;
        }
        return withAuth().catch((retryErr: unknown) => {
          if (retryErr instanceof ProblemError && retryErr.status === 401) {
            setStatus("anon");
          }
          throw retryErr;
        });
      });
    },
    [refreshAccess],
  ) as Fetcher;

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
        await refreshAccess();
      } catch (err) {
        setStatus("anon");
        throw err;
      }
      const retry = await go();
      if (retry.status === 401) setStatus("anon");
      return retry;
    },
    [refreshAccess],
  );

  const api = useMemo(() => makeApi(authedFetch), [authedFetch]);
  const plainApi = useMemo(() => makeApi(apiFetch), []);

  const login = useCallback(
    async (body: { email: string; password: string }) => {
      const res: AuthResponse = await plainApi.auth.login(body);
      tokenRef.current = res.access_token;
      setUser(res.user);
      setStatus("authed");
    },
    [plainApi],
  );

  const register = useCallback(
    async (body: { email: string; password: string; full_name: string }) => {
      const res: AuthResponse = await plainApi.auth.register(body);
      tokenRef.current = res.access_token;
      setUser(res.user);
      setStatus("authed");
    },
    [plainApi],
  );

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } finally {
      tokenRef.current = null;
      setUser(null);
      setStatus("anon");
    }
  }, [api]);

  const changePassword = useCallback(
    async (body: { current_password: string; new_password: string }) => {
      // The server ends every other session and starts a new one for this tab.
      const res = await api.auth.changePassword(body);
      tokenRef.current = res.access_token;
    },
    [api],
  );

  useEffect(() => {
    let active = true;
    void bootstrap().catch(() => {
      if (active) setStatus("anon");
    });
    return () => {
      active = false;
    };
  }, [bootstrap]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      api,
      authedStream,
      login,
      register,
      logout,
      changePassword,
    }),
    [status, user, api, authedStream, login, register, logout, changePassword],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
