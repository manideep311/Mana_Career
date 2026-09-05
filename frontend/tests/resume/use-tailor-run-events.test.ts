import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { useTailorRunEvents } from "@/hooks/useTailorRunEvents";

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

describe("useTailorRunEvents", () => {
  it("accumulates step and block frames then marks done", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: open\ndata: {"event":"open","run_id":"r1"}\n\n`,
        `event: step\ndata: {"event":"step","node":"resume_tailoring","status":"ok","summary":"Tailored résumé draft ready"}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"text","markdown":"Done."}}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"resume_suggestion","suggestion_id":"v1"}}\n\n`,
        `event: done\ndata: {"event":"done","status":"completed","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useTailorRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(authedStream).toHaveBeenCalledWith(
      "/api/v1/ai/sessions/s1/events?run_id=r1",
      expect.objectContaining({ headers: { Accept: "text/event-stream" } }),
    );
    expect(result.current.steps).toHaveLength(1);
    expect(result.current.blocks.map((b) => b.kind)).toEqual(["text", "resume_suggestion"]);
    expect(result.current.error).toBeNull();
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"event":"error","message":"The run failed."}\n\n`]),
    );
    const { result } = renderHook(() => useTailorRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("The run failed.");
  });

  it("does not reconnect after a stream closes with no done frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: step\ndata: {"event":"step","node":"x","status":"ok","summary":"s"}\n\n`]),
    );
    const { result } = renderHook(() => useTailorRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("Lost the connection. Check Tailored versions shortly.");
    expect(authedStream).toHaveBeenCalledTimes(1);
  });

  it("is inert with a null sessionId or runId", () => {
    const authedStream = vi.fn();
    const { result } = renderHook(() => useTailorRunEvents(null, null), {
      wrapper: wrap(authedStream),
    });
    expect(authedStream).not.toHaveBeenCalled();
    expect(result.current).toEqual({ blocks: [], steps: [], status: "idle", error: null });
  });
});
