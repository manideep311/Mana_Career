"use client";

import { useEffect, useState } from "react";

import type { Milestone } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export interface RoadmapEventsState {
  milestones: Milestone[];
  status: "idle" | "streaming" | "done" | "error";
  error: string | null;
}

const INITIAL: RoadmapEventsState = { milestones: [], status: "idle", error: null };

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
 * Streams a roadmap's milestones as the planner builds them
 * (`GET /roadmaps/{id}/events`). The relay replays every milestone already
 * written on connect, then a terminal `done` / `error`. Single-attempt, no
 * reconnect (same rationale as usePrepareRunEvents).
 */
export function useRoadmapEvents(recommendationId: string | null): RoadmapEventsState {
  const { authedStream } = useAuth();
  const [state, setState] = useState<RoadmapEventsState>(INITIAL);

  useEffect(() => {
    if (!recommendationId) {
      setState(INITIAL);
      return;
    }
    setState({ ...INITIAL, status: "streaming" });
    let cancelled = false;

    void (async () => {
      try {
        const res = await authedStream(
          `/api/v1/roadmaps/${recommendationId}/events`,
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
            if (frame.event === "milestone") {
              const ms = frame.data.milestone as Milestone | undefined;
              if (!ms || typeof ms.id !== "string") continue;
              setState((s) =>
                s.milestones.some((x) => x.id === ms.id)
                  ? s
                  : {
                      ...s,
                      milestones: [...s.milestones, ms].sort(
                        (a, b) => a.order_index - b.order_index,
                      ),
                    },
              );
            } else if (frame.event === "error") {
              setState((s) => ({
                ...s,
                status: "error",
                error: String(frame.data.message ?? "We couldn't build your roadmap."),
              }));
            } else if (frame.event === "done") {
              setState((s) => (s.status === "error" ? s : { ...s, status: "done" }));
            }
          }
        }
        if (!cancelled) {
          // Stream closed. If we never saw a terminal frame, treat it as done
          // (a 0-milestone roadmap closes the relay without a `done` in some
          // races) unless nothing at all arrived.
          setState((s) =>
            s.status === "streaming" ? { ...s, status: "done" } : s,
          );
        }
      } catch {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            status: s.milestones.length > 0 ? "done" : "error",
            error: s.milestones.length > 0 ? s.error : "Lost the connection to this roadmap.",
          }));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [recommendationId, authedStream]);

  return state;
}
