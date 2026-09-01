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
    //   4-5  silent re-bootstrap: refresh -> t2, then me
    //   6    retry -> 200 SSE body
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
      .mockResolvedValueOnce(
        jsonRes({ id: "u1", email: "a@b.co", full_name: "A", is_admin: false, created_at: "" }),
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
});
