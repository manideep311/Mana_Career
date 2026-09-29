import type { ReactNode } from "react";

import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { MATCH_POLL, nextPollDelay, useMatch } from "@/hooks/useMatch";
import { makeQueryClient } from "@/lib/query";

function setup(statuses: Array<"scoring" | "ready" | "failed">) {
  let call = 0;
  const get = vi.fn(async () => {
    const status = statuses[Math.min(call, statuses.length - 1)];
    call += 1;
    return { id: "m1", status } as never;
  });
  const api = { matches: { create: vi.fn(async () => ({ id: "m1" }) as never), get } };
  const client = makeQueryClient();
  const auth = makeAuthValue({ api });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
      </QueryClientProvider>
    );
  }
  const hook = renderHook(() => useMatch("job-1"), { wrapper: Wrapper });
  return { hook, get };
}

const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("nextPollDelay", () => {
  it("starts at 2 s, doubles every 15 s and caps at 10 s", () => {
    expect([0, 14_999, 15_000, 30_000, 45_000, 600_000].map(nextPollDelay)).toEqual([
      2_000, 2_000, 4_000, 8_000, 10_000, 10_000,
    ]);
  });
});

describe("useMatch polling", () => {
  it("stops polling once the match is ready", async () => {
    const { hook, get } = setup(["scoring", "scoring", "ready"]);
    await advance(10_000);
    expect(hook.result.current.match?.status).toBe("ready");
    const calls = get.mock.calls.length;
    await advance(60_000);
    expect(get.mock.calls.length).toBe(calls);
    expect(hook.result.current.stalled).toBe(false);
  });

  it("gives up after the polling budget instead of spinning forever", async () => {
    const { hook, get } = setup(["scoring"]);
    await advance(1_000);
    expect(hook.result.current.match?.status).toBe("scoring");

    await advance(MATCH_POLL.budgetMs + 1_000);
    expect(hook.result.current.stalled).toBe(true);

    const calls = get.mock.calls.length;
    await advance(120_000);
    expect(get.mock.calls.length).toBe(calls); // no more polling after giving up
    // Backoff: far fewer requests than a fixed 2 s interval would make.
    expect(calls).toBeLessThan(MATCH_POLL.budgetMs / 2_000);
  });

  it("retrying after a stall resumes polling", async () => {
    const { hook, get } = setup(["scoring"]);
    await advance(MATCH_POLL.budgetMs + 2_000);
    expect(hook.result.current.stalled).toBe(true);
    const calls = get.mock.calls.length;

    act(() => hook.result.current.refetch());
    await advance(5_000);
    expect(hook.result.current.stalled).toBe(false);
    expect(get.mock.calls.length).toBeGreaterThan(calls);
  });
});
