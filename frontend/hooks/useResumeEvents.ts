"use client";

import { useEffect, useState } from "react";

import type { ResumeStatus } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export interface ResumeEventState {
  status: ResumeStatus | null;
  message: string | null;
  done: boolean;
  error: string | null;
}

const INITIAL: ResumeEventState = { status: null, message: null, done: false, error: null };
const MAX_ATTEMPTS = 5;

interface Frame {
  event: string;
  data: Record<string, unknown>;
}

function parseFrame(raw: string): Frame | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue; // keepalive comment
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (data.length === 0) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
  } catch {
    return null;
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useResumeEvents(
  resumeId: string | null,
  opts: { enabled?: boolean; baseDelayMs?: number } = {},
): ResumeEventState {
  const { authedStream } = useAuth();
  const enabled = (opts.enabled ?? true) && resumeId !== null;
  const baseDelayMs = opts.baseDelayMs ?? 1000;
  const [state, setState] = useState<ResumeEventState>(INITIAL);

  useEffect(() => {
    if (!enabled || !resumeId) {
      setState(INITIAL);
      return;
    }
    setState(INITIAL);
    let cancelled = false;
    const ctrl = new AbortController();

    const consume = async (): Promise<"done" | "closed"> => {
      const res = await authedStream(`/api/v1/resumes/${resumeId}/events`, {
        signal: ctrl.signal,
        headers: { Accept: "text/event-stream" },
      });
      if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return "closed";
        buf += decoder.decode(value, { stream: true });
        // Frame boundary is `\r\n\r\n` on the wire (sse-starlette's
        // DEFAULT_SEPARATOR is `\r\n`); `\n\n` is tolerated too. The delimiter
        // length varies, so advance by the actual match length.
        let m: RegExpExecArray | null;
        while ((m = /\r\n\r\n|\n\n/.exec(buf)) !== null) {
          const frame = parseFrame(buf.slice(0, m.index));
          buf = buf.slice(m.index + m[0].length);
          if (!frame || cancelled) continue;
          if (frame.event === "status") {
            setState((s) => ({
              ...s,
              status: (frame.data.status as ResumeStatus) ?? s.status,
              message: (frame.data.message as string) ?? s.message,
            }));
          } else if (frame.event === "done") {
            setState((s) => ({ ...s, done: true, status: (frame.data.status as ResumeStatus) ?? s.status }));
            return "done";
          } else if (frame.event === "error") {
            setState((s) => ({ ...s, done: true, error: (frame.data.message as string) ?? "Stream error" }));
            return "done";
          }
        }
      }
    };

    const run = async () => {
      for (let attempt = 0; attempt <= MAX_ATTEMPTS && !cancelled; attempt++) {
        try {
          const result = await consume();
          if (result === "done" || cancelled) return;
          // "closed" with no `done`: reconnect (the backend re-reads status on `open`).
        } catch {
          if (cancelled || ctrl.signal.aborted) return;
        }
        if (attempt === MAX_ATTEMPTS) {
          setState((s) => ({ ...s, done: true, error: "Lost the connection to status updates." }));
          return;
        }
        await sleep(Math.min(baseDelayMs * 2 ** attempt, 16000));
      }
    };

    void run();
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [enabled, resumeId, authedStream, baseDelayMs]);

  return state;
}
