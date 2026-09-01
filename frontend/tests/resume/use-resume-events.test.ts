import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, makeAuthValue } from "@/test/utils";
import { useResumeEvents } from "@/hooks/useResumeEvents";

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

describe("useResumeEvents", () => {
  it("advances status from stream frames and marks done", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: open\ndata: {"event":"open"}\n\n`,
        `event: status\ndata: {"status":"parsing","message":"Reading your résumé…"}\n\n`,
        `event: status\ndata: {"status":"extracting","message":"Understanding the details…"}\n\n`,
        `event: status\ndata: {"status":"extracted","message":"Ready to review"}\n\n`,
        `event: done\ndata: {"status":"extracted","totals":{}}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useResumeEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true));
    expect(result.current.status).toBe("extracted");
    expect(result.current.error).toBeNull();
  });

  it("surfaces an error frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([`event: error\ndata: {"code":"stream.bad_payload","message":"bad"}\n\n`]),
    );
    const { result } = renderHook(() => useResumeEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true));
    expect(result.current.error).toBe("bad");
  });

  it("is inert when resumeId is null", () => {
    const authedStream = vi.fn();
    const { result } = renderHook(() => useResumeEvents(null), { wrapper: wrap(authedStream) });
    expect(authedStream).not.toHaveBeenCalled();
    expect(result.current).toEqual({ status: null, message: null, done: false, error: null });
  });

  it("reconnects after an early disconnect and resumes", async () => {
    const authedStream = vi
      .fn()
      .mockResolvedValueOnce(streamOf([`event: status\ndata: {"status":"parsing"}\n\n`])) // ends with no `done`
      .mockResolvedValueOnce(
        streamOf([`event: status\ndata: {"status":"extracted"}\n\n`, `event: done\ndata: {"status":"extracted"}\n\n`]),
      );
    const { result } = renderHook(() => useResumeEvents("r1", { baseDelayMs: 10 }), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true), { timeout: 3000 });
    expect(authedStream).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("extracted");
  });

  it("parses CRLF-delimited frames (sse-starlette DEFAULT_SEPARATOR) end to end", async () => {
    // Mirrors `ServerSentEvent(...).encode()` on the wire: `\r\n` between lines,
    // `\r\n\r\n` between frames.
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: status\r\ndata: {"status": "parsing", "message": "Reading your résumé…"}\r\n\r\n`,
        `event: status\r\ndata: {"status": "extracting"}\r\n\r\n`,
        `event: done\r\ndata: {"status": "extracted"}\r\n\r\n`,
      ]),
    );
    const { result } = renderHook(() => useResumeEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true));
    expect(result.current.status).toBe("extracted");
    expect(result.current.message).toBe("Reading your résumé…");
    expect(result.current.error).toBeNull();
  });

  it("merges partial status frames — each field keeps its prior value when omitted", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: status\ndata: {"status":"parsing","message":"Reading your résumé…"}\n\n`,
        `event: status\ndata: {"message":"Understanding the details…"}\n\n`, // no `status` → keeps "parsing"
        `event: status\ndata: {"status":"extracting"}\n\n`, // no `message` → keeps "Understanding the details…"
        `event: done\ndata: {}\n\n`, // no `status` → keeps "extracting"
      ]),
    );
    const { result } = renderHook(() => useResumeEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true));
    expect(result.current.status).toBe("extracting");
    expect(result.current.message).toBe("Understanding the details…");
  });

  it("skips keepalive comments and empty-data frames without dropping the next real frame", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `: ping - 1712345678\n\n`,
        `data:\n\n`,
        `event: status\ndata: {"status":"parsing","message":"Reading your résumé…"}\n\n`,
        `event: done\ndata: {"status":"extracted"}\n\n`,
      ]),
    );
    const { result } = renderHook(() => useResumeEvents("r1"), { wrapper: wrap(authedStream) });
    await waitFor(() => expect(result.current.done).toBe(true));
    expect(result.current.status).toBe("extracted");
    expect(result.current.message).toBe("Reading your résumé…");
    expect(result.current.error).toBeNull();
  });
});
