import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth, type AuthContextValue } from "@/providers/AuthProvider";
import * as fetcher from "@/lib/api/fetcher";
import { API_BASE_URL } from "@/lib/env";

function Probe() {
  const { status, user } = useAuth();
  return <div>{status}:{user?.email ?? "-"}</div>;
}

/** Captures the live `authedStream` from context so a test can invoke it. */
let capturedStream: AuthContextValue["authedStream"] | null = null;

function StreamProbe() {
  const { status, authedStream } = useAuth();
  capturedStream = authedStream;
  return <div>stream:{status}</div>;
}

/** `apiFetch` does `res.json()`, so scripted bootstrap responses need a JSON body. */
const jsonRes = (b: unknown) => new Response(JSON.stringify(b), { status: 200 });

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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

  it("authedStream attaches the bearer token and retries once on 401", async () => {
    capturedStream = null;

    // One global `fetch` stub feeds both `apiFetch` (bootstrap) and the raw
    // `fetch` inside `authedStream`. Ordered:
    //   1-2  mount bootstrap: refresh -> t1, then me
    //   3    first authedStream attempt -> 401
    //   4    silent token refresh -> t2 (no second /me: the user is known)
    //   5    retry -> 200 SSE body
    const fetchMock = vi.fn<(input: string, init?: RequestInit) => Promise<Response>>();
    fetchMock
      .mockResolvedValueOnce(
        jsonRes({ access_token: "t1", token_type: "bearer", expires_in: 900 }),
      )
      .mockResolvedValueOnce(
        jsonRes({ id: "u1", email: "a@b.co", full_name: "A", is_admin: false, created_at: "" }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(
        jsonRes({ access_token: "t2", token_type: "bearer", expires_in: 900 }),
      )
      .mockResolvedValueOnce(new Response("data: {}\n\n", { status: 200 }))
      .mockResolvedValue(new Response(null, { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <StreamProbe />
      </AuthProvider>,
    );

    // Let the mount bootstrap (calls 1-2) finish so the stream calls land in order.
    await waitFor(() =>
      expect(screen.getByText("stream:authed")).toBeInTheDocument(),
    );
    expect(capturedStream).not.toBeNull();

    let returned: Response | undefined;
    await act(async () => {
      returned = await capturedStream!("/api/v1/resumes/r1/events");
    });

    // (a) authedStream resolves to a raw Response, never a parsed body.
    expect(returned).toBeInstanceOf(Response);
    expect(returned?.status).toBe(200);

    const streamCalls = fetchMock.mock.calls.filter(([url]) =>
      url.includes("/api/v1/resumes/r1/events"),
    );
    expect(streamCalls).toHaveLength(2);

    // Path is prefixed with API_BASE_URL and carries credentials.
    expect(streamCalls[0][0]).toBe(`${API_BASE_URL}/api/v1/resumes/r1/events`);
    expect(streamCalls[0][1]?.credentials).toBe("include");

    // (b) pre-refresh attempt carried the first token.
    expect(new Headers(streamCalls[0][1]?.headers).get("Authorization")).toBe(
      "Bearer t1",
    );
    // (c) post-refresh retry carried the refreshed token.
    expect(new Headers(streamCalls[1][1]?.headers).get("Authorization")).toBe(
      "Bearer t2",
    );
  });

  it("shares one token refresh between requests that hit a 401 together", async () => {
    let capturedApi: AuthContextValue["api"] | null = null;
    function ApiProbe() {
      const { status, api } = useAuth();
      capturedApi = api;
      return <div>api:{status}</div>;
    }

    let refreshes = 0;
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        refreshes += 1;
        const token = `t${refreshes}`;
        // Slow enough that every concurrent 401 arrives while it's in flight.
        await new Promise((resolve) => setTimeout(resolve, 20));
        return jsonRes({ access_token: token, token_type: "bearer", expires_in: 900 });
      }
      if (url.endsWith("/auth/me")) {
        return jsonRes({ id: "u1", email: "a@b.co", full_name: "A", is_admin: false, created_at: "" });
      }
      // The first token has "expired": only the refreshed one is accepted.
      const auth = new Headers(init?.headers).get("Authorization");
      return auth === "Bearer t2"
        ? jsonRes({ ok: true })
        : new Response(JSON.stringify({ code: "token_expired" }), { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <ApiProbe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("api:authed")).toBeInTheDocument());
    expect(refreshes).toBe(1);

    const api = capturedApi as AuthContextValue["api"] | null;
    if (!api) throw new Error("api not captured");
    let results: unknown[] = [];
    await act(async () => {
      results = await Promise.all(Array.from({ length: 5 }, () => api.profile.get()));
    });

    expect(results).toHaveLength(5);
    // Five simultaneous 401s, one refresh: rotating the same refresh token
    // twice would look like token theft to the server and end the session.
    expect(refreshes).toBe(2);
    expect(screen.getByText("api:authed")).toBeInTheDocument();
  });

  it("goes anon when the refresh itself is rejected", async () => {
    let capturedApi: AuthContextValue["api"] | null = null;
    function ApiProbe() {
      const { status, api } = useAuth();
      capturedApi = api;
      return <div>api:{status}</div>;
    }
    let refreshCalls = 0;
    vi.spyOn(fetcher, "apiFetch").mockImplementation(async (path: string) => {
      if (path.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        if (refreshCalls === 1) {
          return { access_token: "t1", token_type: "bearer", expires_in: 900 } as never;
        }
        throw new fetcher.ProblemError("session_revoked", 401, {});
      }
      if (path.endsWith("/auth/me")) {
        return { id: "1", email: "me@x.com", full_name: "Me", is_admin: false, created_at: "" } as never;
      }
      throw new fetcher.ProblemError("token_expired", 401, {});
    });
    render(
      <AuthProvider>
        <ApiProbe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("api:authed")).toBeInTheDocument());
    const api = capturedApi as AuthContextValue["api"] | null;
    if (!api) throw new Error("api not captured");
    await act(async () => {
      await expect(api.profile.get()).rejects.toBeInstanceOf(fetcher.ProblemError);
    });
    await waitFor(() => expect(screen.getByText("api:anon")).toBeInTheDocument());
  });
});
