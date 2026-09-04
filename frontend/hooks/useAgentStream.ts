"use client";

import { useCallback, useRef, useState } from "react";

import type { ResponseBlock } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

export interface AgentStep {
  node: string;
  status: string;
  summary: string;
}

export interface AgentStreamState {
  blocks: ResponseBlock[];
  steps: AgentStep[];
  status: "idle" | "streaming" | "done" | "error";
  error: string | null;
}

const INITIAL: AgentStreamState = { blocks: [], steps: [], status: "idle", error: null };

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

export function useAgentStream(
  sessionId: string | null,
): AgentStreamState & { send: (content: string) => void; reset: () => void } {
  const { authedStream } = useAuth();
  const [state, setState] = useState<AgentStreamState>(INITIAL);
  const runningRef = useRef(false);

  const reset = useCallback(() => setState(INITIAL), []);

  const send = useCallback(
    (content: string) => {
      if (!sessionId || runningRef.current) return;
      runningRef.current = true;
      setState({ ...INITIAL, status: "streaming" });

      void (async () => {
        try {
          const res = await authedStream(`/api/v1/ai/sessions/${sessionId}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify({ content }),
          });
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
              if (!frame) continue;
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
          setState((s) => (s.status === "streaming" ? { ...s, status: "done" } : s));
        } catch {
          setState((s) => ({ ...s, status: "error", error: "Lost the connection." }));
        } finally {
          runningRef.current = false;
        }
      })();
    },
    [sessionId, authedStream],
  );

  return { ...state, send, reset };
}
