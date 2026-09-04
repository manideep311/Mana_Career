"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Sparkles, X } from "lucide-react";

import { BlockView } from "@/components/ai/blocks/block-registry";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useAgentStream } from "@/hooks/useAgentStream";
import type { ResponseBlock } from "@/lib/api/types";
import { useAuth } from "@/providers/AuthProvider";

const SUGGESTED = "find jobs that match my experience";

interface Turn {
  role: "user" | "assistant";
  text?: string;
  blocks?: ResponseBlock[];
}

export function ManaPanelDock() {
  const { api } = useAuth();
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);

  const stream = useAgentStream(sessionId);

  // Create the chat session eagerly, the moment the dock is first opened. The
  // `sessionId` dep makes this fire exactly once: it re-runs when the id lands
  // and then early-returns. `useAgentStream.send` closes over `sessionId`, so
  // the session must exist *before* the first `send` — hence eager, not lazy.
  useEffect(() => {
    if (!open || sessionId) return;
    void api.ai.createSession({ kind: "chat" }).then((s) => setSessionId(s.id));
  }, [open, sessionId, api]);

  // Fold the live stream's blocks into the last assistant turn.
  useEffect(() => {
    if (stream.status === "idle") return;
    setTurns((t) => {
      const next = [...t];
      const last = next[next.length - 1];
      if (last && last.role === "assistant") {
        next[next.length - 1] = { ...last, blocks: stream.blocks };
      }
      return next;
    });
  }, [stream.blocks, stream.status]);

  useEffect(() => {
    const el = bodyRef.current;
    // jsdom has no Element.scrollTo — guard so tests don't throw.
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    }
  }, [turns, stream.steps.length]);

  const send = useCallback(
    (content: string) => {
      const body = content.trim();
      if (!body || stream.status === "streaming" || !sessionId) return;
      setDraft("");
      setTurns((t) => [...t, { role: "user", text: body }, { role: "assistant", blocks: [] }]);
      stream.send(body);
    },
    [stream, sessionId],
  );

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-40 hidden items-center gap-2 rounded-full border border-border bg-surface px-4 py-2 text-sm font-medium text-text shadow-[var(--shadow-1)] md:flex"
      >
        <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />
        Mana AI
      </button>
    );
  }

  return (
    <section
      aria-label="Mana AI"
      className="fixed bottom-4 right-4 z-40 hidden h-[32rem] w-96 flex-col rounded-[var(--radius)] border border-border bg-surface shadow-[var(--shadow-1)] md:flex"
    >
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="flex items-center gap-2 text-sm font-semibold text-text">
          <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />
          Mana AI
        </span>
        <button type="button" onClick={() => setOpen(false)} aria-label="Collapse">
          <X className="h-4 w-4 text-text-muted" />
        </button>
      </header>

      <div ref={bodyRef} className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">
        {turns.length === 0 ? (
          <p className="text-sm text-text-muted">
            Ask about your job matches, skill gaps, or a role you’re eyeing.
          </p>
        ) : null}

        {turns.map((turn, i) =>
          turn.role === "user" ? (
            <p
              key={i}
              className="ml-auto max-w-[85%] rounded-[var(--radius)] bg-accent-soft px-3 py-2 text-sm text-accent"
            >
              {turn.text}
            </p>
          ) : (
            <div key={i} className="flex flex-col gap-2">
              {(turn.blocks ?? []).map((b, j) => (
                <BlockView key={j} block={b} />
              ))}
            </div>
          ),
        )}

        {stream.status === "streaming" ? (
          <span className="flex items-center gap-2 text-xs text-text-muted">
            <Spinner size="sm" />
            {stream.steps.at(-1)?.summary ?? "Thinking…"}
          </span>
        ) : null}
        {stream.status === "error" ? (
          <p className="text-xs text-danger">{stream.error}</p>
        ) : null}
      </div>

      <footer className="flex flex-col gap-2 border-t border-border px-4 py-3">
        {turns.length === 0 ? (
          <button
            type="button"
            onClick={() => send(SUGGESTED)}
            disabled={!sessionId || stream.status === "streaming"}
            className="self-start rounded-full border border-border px-3 py-1 text-xs text-text-muted hover:bg-surface-sunk"
          >
            {SUGGESTED}
          </button>
        ) : null}
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
            rows={1}
            disabled={!sessionId}
            placeholder="Message Mana…"
            className="flex-1 resize-none rounded-[var(--radius)] border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
          />
          <Button
            size="sm"
            onClick={() => send(draft)}
            disabled={!sessionId || stream.status === "streaming"}
          >
            Send
          </Button>
        </div>
      </footer>
    </section>
  );
}
