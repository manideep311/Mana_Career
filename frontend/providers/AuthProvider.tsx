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

export type AuthStatus = "loading" | "authed" | "anon";

type Api = ReturnType<typeof makeApi>;

export interface AuthContextValue {
  status: AuthStatus;
  user: UserOut | null;
  api: Api;
  login: (body: { email: string; password: string }) => Promise<void>;
  register: (body: {
    email: string;
    password: string;
    full_name: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (body: {
    old_password: string;
    new_password: string;
  }) => Promise<void>;
}

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
 * single silent `bootstrap()` + retry before giving up and going `anon`.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const tokenRef = useRef<string | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserOut | null>(null);

  const bootstrap = useCallback(async () => {
    const access = await apiFetch<AccessResponse>("/api/v1/auth/refresh", {
      method: "POST",
    });
    tokenRef.current = access.access_token;
    const me = await apiFetch<UserOut>("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${access.access_token}` },
    });
    setUser(me);
    setStatus("authed");
  }, []);

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
          await bootstrap();
        } catch (bootErr) {
          setStatus("anon");
          throw bootErr;
        }
        return withAuth().catch((retryErr: unknown) => {
          if (retryErr instanceof ProblemError && retryErr.status === 401) {
            setStatus("anon");
          }
          throw retryErr;
        });
      });
    },
    [bootstrap],
  ) as Fetcher;

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
    async (body: { old_password: string; new_password: string }) => {
      await api.auth.changePassword(body);
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
    () => ({ status, user, api, login, register, logout, changePassword }),
    [status, user, api, login, register, logout, changePassword],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
