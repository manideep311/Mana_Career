"use client";

import { useEffect, useState } from "react";

import type { AgentStep } from "@/hooks/useAgentStream";
import { useAuth } from "@/providers/AuthProvider";

export interface PrepareRunState {
  steps: AgentStep[];
  status: "idle" | "streaming" | "awaiting_approval" | "done" | "error";
  approvalId: string | null;
  error: string | null;
}

const INITIAL: PrepareRunState = {
  steps: [], status: "idle", approvalId: null, error: null,
};

interface Frame {
  event: string;
  data: Record<string, unknown>;
}

function parseFrame(raw: string): Frame | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue;
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

/**
 * Watches an in-flight `prepare_application` run
 * (`GET /ai/sessions/{sessionId}/events?run_id=...`). Single-attempt, no
 * reconnect — same rationale as `useTailorRunEvents` (the AI relay forwards
 * live Redis pub/sub with no replay). On the `approval` frame it stops
 * advancing and surfaces `status: "awaiting_approval"` + `approvalId`; the
 * caller then drives the approval + the post-approval poll (spec R2/R3).
 */
export function usePrepareRunEvents(
  sessionId: string | null,
  runId: string | null,
): PrepareRunState {
  const { authedStream } = useAuth();
  const [state, setState] = useState<PrepareRunState>(INITIAL);

  useEffect(() => {
    if (!sessionId || !runId) {
      setState(INITIAL);
      return;
    }
    setState({ ...INITIAL, status: "streaming" });
    let cancelled = false;

    void (async () => {
      try {
        const res = await authedStream(
          `/api/v1/ai/sessions/${sessionId}/events?run_id=${encodeURIComponent(runId)}`,
          { headers: { Accept: "text/event-stream" } },
        );
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let m: RegExpExecArray | null;
          while ((m = /\r\n\r\n|\n\n/.exec(buf)) !== null) {
            const frame = parseFrame(buf.slice(0, m.index));
            buf = buf.slice(m.index + m[0].length);
            if (!frame || cancelled) continue;
            if (frame.event === "step") {
              setState((s) => ({
                ...s,
                steps: [
                  ...s.steps,
                  {
                    node: String(frame.data.node ?? ""),
                    status: String(frame.data.status ?? ""),
                    summary: String(frame.data.summary ?? ""),
                  },
                ],
              }));
            } else if (frame.event === "approval") {
              const id = frame.data.approval_id;
              setState((s) => ({
                ...s,
                status: "awaiting_approval",
                approvalId: typeof id === "string" ? id : null,
              }));
            } else if (frame.event === "error") {
              setState((s) => ({
                ...s,
                status: "error",
                error: String(frame.data.message ?? "The run failed."),
              }));
            } else if (frame.event === "done") {
              setState((s) =>
                s.status === "error" || s.status === "awaiting_approval"
                  ? s
                  : { ...s, status: "done" },
              );
            }
          }
        }
        if (!cancelled) {
          setState((s) =>
            s.status === "streaming"
              ? { ...s, status: "error", error: "Lost the connection to this run." }
              : s,
          );
        }
      } catch {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            status: "error",
            error: "Lost the connection to this run.",
          }));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId, runId, authedStream]);

  return state;
}
