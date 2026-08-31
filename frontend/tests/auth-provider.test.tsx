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
