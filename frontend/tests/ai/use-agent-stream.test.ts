import { renderHook, waitFor, act } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { useAgentStream } from "@/hooks/useAgentStream";

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

describe("useAgentStream", () => {
  it("accumulates step and block frames then marks done", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: open\ndata: {"event":"open","run_id":"r1"}\n\n`,
        `event: step\ndata: {"event":"step","node":"job_retrieval","status":"ok","summary":"Found 3 candidate roles"}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"text","markdown":"Here are 3 roles."}}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"job_card","job_id":"j1","match_id":null}}\n\n`,
        `event: done\ndata: {"event":"done","status":"completed","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useAgentStream("s1"), { wrapper: wrap(authedStream) });
    act(() => result.current.send("find jobs that match my experience"));
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.steps).toHaveLength(1);
    expect(result.current.blocks.map((b) => b.kind)).toEqual(["text", "job_card"]);
    expect(result.current.error).toBeNull();
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"event":"error","message":"The run failed."}\n\n`]),
    );
    const { result } = renderHook(() => useAgentStream("s1"), { wrapper: wrap(authedStream) });
    act(() => result.current.send("x"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("The run failed.");
  });

  it("is inert with a null session id", () => {
    const authedStream = vi.fn();
    const { result } = renderHook(() => useAgentStream(null), { wrapper: wrap(authedStream) });
    act(() => result.current.send("x"));
    expect(authedStream).not.toHaveBeenCalled();
  });
});
