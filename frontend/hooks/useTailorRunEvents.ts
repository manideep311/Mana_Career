"use client";

import { useEffect, useState } from "react";

import type { AgentStep } from "@/hooks/useAgentStream";
import type { ResponseBlock } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export interface TailorRunState {
  blocks: ResponseBlock[];
  steps: AgentStep[];
  status: "idle" | "streaming" | "done" | "error";
  error: string | null;
}

const INITIAL: TailorRunState = { blocks: [], steps: [], status: "idle", error: null };

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
 * Watches an already-started agent run: `GET /ai/sessions/{sessionId}/events
 * ?run_id={runId}`. Deliberately single-attempt, no reconnect — unlike
 * `useJobEvents`/`useResumeEvents`, which reconnect because the backend
 * re-reads DB status on every fresh `open` frame. The AI run relay (`_relay`
 * in `app/api/v1/ai.py`) has no such re-read — it only forwards live Redis
 * pub/sub messages for the run's channel, which has no replay buffer. A
 * reconnect after a drop would subscribe to a channel that already finished
 * emitting and just sit until the relay's own 300s cap synthesizes a timeout
 * `done`. A single-attempt design (matching `useAgentStream`, which already
 * accepts this for the chat flow) that surfaces a drop as an immediate,
 * honest error is strictly better UX here.
 *
 * A dropped stream surfaces as a terminal `"error"` pointing at "Tailored
 * versions", where the result will already be sitting if the run actually
 * finished.
 */
export function useTailorRunEvents(
  sessionId: string | null,
  runId: string | null,
): TailorRunState {
  const { authedStream } = useAuth();
  const [state, setState] = useState<TailorRunState>(INITIAL);

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
            } else if (frame.event === "block") {
              const block = frame.data.block as ResponseBlock | undefined;
              if (block) setState((s) => ({ ...s, blocks: [...s.blocks, block] }));
            } else if (frame.event === "error") {
              setState((s) => ({
                ...s,
                status: "error",
                error: String(frame.data.message ?? "The run failed."),
              }));
            } else if (frame.event === "done") {
              setState((s) => (s.status === "error" ? s : { ...s, status: "done" }));
            }
          }
        }
        if (!cancelled) {
          setState((s) =>
            s.status === "streaming"
              ? {
                  ...s,
                  status: "error",
                  error: "Lost the connection. Check Tailored versions shortly.",
                }
              : s,
          );
        }
      } catch {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            status: "error",
            error: "Lost the connection. Check Tailored versions shortly.",
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
