import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { useRoadmapEvents } from "@/hooks/useRoadmapEvents";

function streamOf(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      for (const f of frames) controller.enqueue(enc.encode(f));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

function wrap(authedStream: () => Promise<Response>) {
  const value = makeAuthValue({ authValue: { authedStream } });
  return ({ children }: { children: ReactNode }) =>
    createElement(AuthContext.Provider, { value }, children);
}

describe("useRoadmapEvents", () => {
  it("accumulates milestone frames deduped + ordered, then done", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: milestone\ndata: {"event":"milestone","milestone":{"id":"m2","order_index":1,"skill_slug":"go","skill_label":"Go","title":"B","why_it_matters":"x","resource_ids":[],"est_hours":null,"practice_project":null,"checkpoint":null,"status":"not_started","completed_at":null}}\n\n`,
        `event: milestone\ndata: {"event":"milestone","milestone":{"id":"m1","order_index":0,"skill_slug":"sql","skill_label":"SQL","title":"A","why_it_matters":"x","resource_ids":[],"est_hours":null,"practice_project":null,"checkpoint":null,"status":"not_started","completed_at":null}}\n\n`,
        `event: milestone\ndata: {"event":"milestone","milestone":{"id":"m1","order_index":0,"skill_slug":"sql","skill_label":"SQL","title":"A","why_it_matters":"x","resource_ids":[],"est_hours":null,"practice_project":null,"checkpoint":null,"status":"not_started","completed_at":null}}\n\n`,
        `event: done\ndata: {"event":"done","status":"active","id":"r1"}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useRoadmapEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.milestones.map((m) => m.id)).toEqual(["m1", "m2"]);
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"event":"error","message":"We couldn't build your roadmap.","status":"archived"}\n\n`]),
    );
    const { result } = renderHook(() => useRoadmapEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("We couldn't build your roadmap.");
  });

  it("is idle with a null id", () => {
    const { result } = renderHook(() => useRoadmapEvents(null), { wrapper: wrap(vi.fn()) });
    expect(result.current.status).toBe("idle");
  });
});
