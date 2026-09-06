import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { usePrepareRunEvents } from "@/hooks/usePrepareRunEvents";

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

describe("usePrepareRunEvents", () => {
  it("accumulates steps then surfaces awaiting_approval with the approval id", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: step\ndata: {"event":"step","node":"cover_letter","status":"ok","summary":"Wrote a cover letter"}\n\n`,
        `event: step\ndata: {"event":"step","node":"application_prep","status":"ok","summary":"Ready for review"}\n\n`,
        `event: approval\ndata: {"event":"approval","approval_id":"ap-1"}\n\n`,
        `event: done\ndata: {"event":"done","status":"awaiting_approval","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => usePrepareRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("awaiting_approval"));
    expect(result.current.approvalId).toBe("ap-1");
    expect(result.current.steps.map((s) => s.node)).toEqual([
      "cover_letter", "application_prep",
    ]);
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"event":"error","message":"The run failed."}\n\n`]),
    );
    const { result } = renderHook(() => usePrepareRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("The run failed.");
  });

  it("reaches done for a run that completes without a pause", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: step\ndata: {"event":"step","node":"respond","status":"ok","summary":"done"}\n\n`,
        `event: done\ndata: {"event":"done","status":"completed","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => usePrepareRunEvents("s1", "r1"), {
      wrapper: wrap(authedStream),
    });
    await waitFor(() => expect(result.current.status).toBe("done"));
  });

  it("is inert with a null sessionId or runId", () => {
    const authedStream = vi.fn();
    const { result } = renderHook(() => usePrepareRunEvents(null, null), {
      wrapper: wrap(authedStream),
    });
    expect(authedStream).not.toHaveBeenCalled();
    expect(result.current).toEqual({
      steps: [], status: "idle", approvalId: null, error: null,
    });
  });
});
