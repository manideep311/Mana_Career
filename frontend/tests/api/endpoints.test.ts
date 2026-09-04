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

describe("profile skills", () => {
  it("skills GETs /profile/skills", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return []; }) as unknown as Fetcher);
    await api.profile.skills();
    expect(calls[0]).toBe("/api/v1/profile/skills");
  });
  it("rebuild POSTs /profile/rebuild", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return undefined; }) as unknown as Fetcher);
    await api.profile.rebuild();
    expect(calls[0].path).toBe("/api/v1/profile/rebuild");
    expect(calls[0].init?.method).toBe("POST");
  });
});

describe("jobs", () => {
  it("list serialises query params and GETs /jobs", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return { items: [], total: 0 }; }) as unknown as Fetcher);
    await api.jobs.list({ q: "rust", work_mode: "remote", limit: 12 });
    expect(calls[0]).toBe("/api/v1/jobs?q=rust&work_mode=remote&limit=12");
  });
  it("list with no params GETs bare /jobs", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return { items: [] }; }) as unknown as Fetcher);
    await api.jobs.list();
    expect(calls[0]).toBe("/api/v1/jobs");
  });
  it("create POSTs { raw_text } to /jobs", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return { id: "j1", status: "ingesting" }; }) as unknown as Fetcher);
    await api.jobs.create("Senior ML Engineer ...");
    expect(calls[0].path).toBe("/api/v1/jobs");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ raw_text: "Senior ML Engineer ..." });
  });
  it("remove DELETEs /jobs/{id}", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return undefined; }) as unknown as Fetcher);
    await api.jobs.remove("j1");
    expect(calls[0].path).toBe("/api/v1/jobs/j1");
    expect(calls[0].init?.method).toBe("DELETE");
  });
});

describe("matches", () => {
  it("create POSTs { job_id } to /api/v1/matches", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return { id: "m1", status: "scoring" }; }) as unknown as Fetcher);
    await api.matches.create("j1");
    expect(calls[0].path).toBe("/api/v1/matches");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ job_id: "j1" });
  });
  it("get GETs /api/v1/matches/{id}", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return {}; }) as unknown as Fetcher);
    await api.matches.get("m1");
    expect(calls[0]).toBe("/api/v1/matches/m1");
  });
  it("recompute POSTs { scope } to /api/v1/matches/recompute", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return { status: "ok", count: 5 }; }) as unknown as Fetcher);
    await api.matches.recompute({ scope: "all" });
    expect(calls[0].path).toBe("/api/v1/matches/recompute");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ scope: "all" });
  });
  it("components GETs /api/v1/matches/{id}/components", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return []; }) as unknown as Fetcher);
    await api.matches.components("m1");
    expect(calls[0]).toBe("/api/v1/matches/m1/components");
  });
});

describe("skill gaps", () => {
  it("list GETs /api/v1/skill-gaps?scope=job&job_match_id={id}", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return []; }) as unknown as Fetcher);
    await api.skillGaps.list("jm1");
    expect(calls[0]).toBe("/api/v1/skill-gaps?scope=job&job_match_id=jm1");
  });
  it("patch PATCHes { status } to /api/v1/skill-gaps/{id}", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return {}; }) as unknown as Fetcher);
    await api.skillGaps.patch("g1", "learning");
    expect(calls[0].path).toBe("/api/v1/skill-gaps/g1");
    expect(calls[0].init?.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ status: "learning" });
  });
});

describe("eval", () => {
  it("listRuns GETs /api/v1/eval/runs", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return { items: [], total: 0 }; }) as unknown as Fetcher);
    await api.eval.listRuns();
    expect(calls[0]).toBe("/api/v1/eval/runs");
  });
  it("listRuns serialises query params", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return { items: [], total: 0 }; }) as unknown as Fetcher);
    await api.eval.listRuns({ suite: "retrieval", limit: 5 });
    expect(calls[0]).toBe("/api/v1/eval/runs?suite=retrieval&limit=5");
  });
  it("getRun GETs /api/v1/eval/runs/{id}", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return {}; }) as unknown as Fetcher);
    await api.eval.getRun("r1");
    expect(calls[0]).toBe("/api/v1/eval/runs/r1");
  });
  it("runResults GETs /api/v1/eval/runs/{id}/results", async () => {
    const calls: string[] = [];
    const api = makeApi((async (p: string) => { calls.push(p); return []; }) as unknown as Fetcher);
    await api.eval.runResults("r1");
    expect(calls[0]).toBe("/api/v1/eval/runs/r1/results");
  });
  it("createRun POSTs { suite: 'retrieval' } to /api/v1/eval/runs", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const api = makeApi((async (path: string, init?: RequestInit) => { calls.push({ path, init }); return {}; }) as unknown as Fetcher);
    await api.eval.createRun("retrieval");
    expect(calls[0].path).toBe("/api/v1/eval/runs");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ suite: "retrieval" });
  });
});

describe("ai", () => {
  it("creates a session with a JSON body", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.createSession({ kind: "chat" });
    expect(calls[0].path).toBe("/api/v1/ai/sessions");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ kind: "chat" });
  });

  it("lists sessions with query params", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.listSessions({ limit: 20, offset: 0 });
    expect(calls[0].path).toBe("/api/v1/ai/sessions?limit=20&offset=0");
  });

  it("startGoal always sends an inputs object", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.startGoal("s1", { goal: "understand_job" });
    expect(calls[0].path).toBe("/api/v1/ai/sessions/s1/goal");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ inputs: {}, goal: "understand_job" });
  });

  it("stopRun posts with no body", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.stopRun("s1");
    expect(calls[0].path).toBe("/api/v1/ai/sessions/s1/stop");
    expect(calls[0].init?.method).toBe("POST");
  });

  it("listActions filters by session", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).ai.listActions({ session_id: "s1" });
    expect(calls[0].path).toBe("/api/v1/ai/actions?session_id=s1");
  });
});

describe("resume tailoring", () => {
  it("tailor POSTs { job_id } to /resumes/{id}/tailor", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.tailor("r1", { job_id: "j1" });
    expect(calls[0].path).toBe("/api/v1/resumes/r1/tailor");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ job_id: "j1" });
  });

  it("versions GETs /resumes/{id}/versions", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.versions("r1");
    expect(calls[0].path).toBe("/api/v1/resumes/r1/versions");
  });

  it("version GETs /resumes/versions/{id}", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.version("v1");
    expect(calls[0].path).toBe("/api/v1/resumes/versions/v1");
  });

  it("diff GETs /resumes/versions/{id}/diff with no query by default", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.diff("v1");
    expect(calls[0].path).toBe("/api/v1/resumes/versions/v1/diff");
  });

  it("diff GETs /resumes/versions/{id}/diff?against=... when given", async () => {
    const { f, calls } = recordingFetcher();
    await makeApi(f).resumes.diff("v1", "base");
    expect(calls[0].path).toBe("/api/v1/resumes/versions/v1/diff?against=base");
  });

  it("renderUrl builds a fmt-qualified path with no fetch call", () => {
    const { f } = recordingFetcher();
    const url = makeApi(f).resumes.renderUrl("v1", "pdf");
    expect(url).toBe("/api/v1/resumes/versions/v1/render?fmt=pdf");
    expect(f).not.toHaveBeenCalled();
  });
});
