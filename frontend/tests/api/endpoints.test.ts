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

describe("resumes", () => {
  it("upload posts multipart to /resumes with no JSON content-type", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => {
      calls.push({ path, init });
      return {} as unknown;
    }) as unknown as Fetcher);
    const file = new File(["%PDF-1.7"], "cv.pdf", { type: "application/pdf" });
    await api.resumes.upload(file);
    expect(calls[0].path).toBe("/api/v1/resumes");
    expect(calls[0].init?.method).toBe("POST");
    expect(calls[0].init?.body).toBeInstanceOf(FormData);
    expect((calls[0].init?.headers as Record<string, string>)?.["Content-Type"]).toBeUndefined();
  });

  it("confirmProfile posts { extraction } to /confirm-profile", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => {
      calls.push({ path, init });
      return undefined as unknown;
    }) as unknown as Fetcher);
    await api.resumes.confirmProfile("r1", { full_name: "Jane" });
    expect(calls[0].path).toBe("/api/v1/resumes/r1/confirm-profile");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      extraction: { full_name: "Jane" },
    });
  });

  it("extraction GETs /resumes/{id}/extraction", async () => {
    const calls: string[] = [];
    const api = makeApi((async (path: string) => {
      calls.push(path);
      return {} as unknown;
    }) as unknown as Fetcher);
    await api.resumes.extraction("r1");
    expect(calls[0]).toBe("/api/v1/resumes/r1/extraction");
  });
});
