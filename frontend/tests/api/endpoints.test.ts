import { describe, expect, it, vi } from "vitest";

import { makeApi } from "@/lib/api/endpoints";
import type { Fetcher } from "@/lib/api/fetcher";

function recordingFetcher() {
  const calls: { path: string; init?: RequestInit }[] = [];
  const f = vi.fn(async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return {} as unknown;
  }) as unknown as Fetcher;
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
