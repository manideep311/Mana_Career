"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { ChevronLeft, ChevronRight, Pause, Play, PlayCircle, X } from "lucide-react";

import { PaperRocket } from "@/components/motion/PaperRocket";
import { cn } from "@/lib/cn";
import { keepTabInside } from "@/lib/focus-trap";

export const STEP_MS = 4500;

const Example = () => (
  <span className="absolute right-3 top-3 rounded-full bg-surface-sunk px-2 py-0.5 text-[11px] font-medium text-text-muted">
    Example
  </span>
);

const STEPS: { title: string; body: string; visual: ReactNode }[] = [
  {
    title: "Share your résumé",
    body: "We read it and map your experience and skills. You check what we found before anything uses it.",
    visual: (
      <div className="flex items-center gap-4">
        <PaperRocket size={84} />
        <p className="text-lg font-semibold text-text">Reading your résumé…</p>
      </div>
    ),
  },
  {
    title: "See where it can take you",
    body: "Paths your experience points to, why each one fits, and what's missing, described in words, not made-up odds.",
    visual: (
      <ul className="flex w-full max-w-sm flex-col gap-2">
        {[
          ["Data Analyst", "Close fit", "bg-positive-soft text-positive"],
          ["Data Scientist", "Reachable stretch", "bg-accent-soft text-accent"],
          ["Data Engineer", "Significant pivot", "bg-surface-sunk text-text-muted"],
        ].map(([title, fit, cls], i) => (
          <li
            key={title}
            className="flex animate-rise items-center justify-between rounded-xl border border-border bg-surface px-4 py-3 text-sm shadow-[var(--shadow-1)]"
            style={{ animationDelay: `${i * 120}ms` }}
          >
            <span className="font-semibold text-text">{title}</span>
            <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", cls)}>{fit}</span>
          </li>
        ))}
      </ul>
    ),
  },
  {
    title: "Get a practical plan",
    body: "The few skills worth building next, each with a project to prove it, laid out over the next 30 to 90 days.",
    visual: (
      <ol className="flex w-full max-w-sm flex-col gap-3 text-sm">
        {[
          ["Now", "Window functions in SQL"],
          ["Next 30 days", "A dashboard from public data"],
          ["Days 30 to 90", "Python for analysis"],
        ].map(([when, what], i) => (
          <li key={when} className="flex animate-rise gap-3" style={{ animationDelay: `${i * 120}ms` }}>
            <span className="w-24 shrink-0 text-xs font-semibold uppercase tracking-wide text-text-muted">
              {when}
            </span>
            <span className="font-medium text-text">{what}</span>
          </li>
        ))}
      </ol>
    ),
  },
  {
    title: "Take the next step",
    body: "Tailor your résumé to a role and prepare an application. Nothing is sent until you approve it.",
    visual: (
      <div className="flex w-full max-w-sm animate-rise flex-col gap-3 rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-1)]">
        <p className="text-sm font-semibold text-text">Application ready for your review</p>
        <p className="text-xs text-text-muted">Nothing will be sent until you approve it.</p>
        <div className="flex gap-2">
          <span className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg">Approve</span>
          <span className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-text">Not yet</span>
        </div>
      </div>
    ),
  },
];

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/**
 * "Watch how it works": a four-step walkthrough in a modal. It advances on its
 * own every few seconds (paused from the start under reduced motion), and can
 * be paused, stepped with the arrow keys, and closed with Escape. Visuals are
 * labelled as examples.
 */
export function HowItWorksPlayer({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const dialogRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const go = useCallback((n: number) => setStep((n + STEPS.length) % STEPS.length), []);
  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  function start() {
    setStep(0);
    setPlaying(!prefersReducedMotion());
    setOpen(true);
  }

  // Auto-advance while playing; stop on the last step.
  useEffect(() => {
    if (!open || !playing) return;
    if (step === STEPS.length - 1) {
      const t = setTimeout(() => setPlaying(false), STEP_MS);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => clearTimeout(t);
  }, [open, playing, step]);

  // Focus, scroll lock and keyboard handling while open.
  useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      } else if (e.key === "ArrowRight") {
        go(step + 1);
      } else if (e.key === "ArrowLeft") {
        go(step - 1);
      } else if (dialogRef.current) {
        keepTabInside(e, dialogRef.current);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, step, go, close]);

  const current = STEPS[step];

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={start}
        className={cn(
          "inline-flex h-14 items-center gap-3 rounded-xl border border-border bg-surface px-6 text-base font-semibold text-text shadow-[var(--shadow-1)] transition-colors hover:border-accent/40",
          className,
        )}
      >
        <PlayCircle className="h-6 w-6 text-accent" aria-hidden />
        Watch how it works
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(21,19,31,0.45)] p-4" onClick={close}>
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="hiw-title"
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
            className="relative flex w-full max-w-xl animate-rise flex-col gap-5 rounded-2xl bg-surface p-6 shadow-[var(--shadow-2)] outline-none"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex flex-col gap-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-accent">
                  Step {step + 1} of {STEPS.length}
                </p>
                <h2 id="hiw-title" className="font-display text-2xl text-text">
                  {current.title}
                </h2>
              </div>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="rounded-lg p-1.5 text-text-muted hover:bg-surface-sunk hover:text-text"
              >
                <X className="h-5 w-5" aria-hidden />
              </button>
            </div>

            <div
              key={step}
              className="relative flex min-h-48 items-center justify-center rounded-xl bg-[linear-gradient(135deg,var(--accent-soft),#fdf1e7)] p-6"
            >
              <Example />
              {current.visual}
            </div>
            <p aria-live="polite" className="text-sm leading-relaxed text-text-muted">
              {current.body}
            </p>

            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {STEPS.map((s, i) => (
                  <button
                    key={s.title}
                    type="button"
                    onClick={() => go(i)}
                    aria-label={`Step ${i + 1}: ${s.title}`}
                    aria-current={i === step ? "step" : undefined}
                    className="flex h-6 w-10 items-center"
                  >
                    <span className="relative h-1.5 w-full overflow-hidden rounded-full bg-surface-sunk">
                      <span
                        key={`${i}-${step}-${playing}`}
                        className={cn(
                          "absolute inset-y-0 left-0 rounded-full bg-accent",
                          i < step || (i === step && !playing)
                            ? "w-full"
                            : i === step
                              ? "hiw-progress"
                              : "w-0",
                        )}
                        style={i === step && playing ? { animationDuration: `${STEP_MS}ms` } : undefined}
                      />
                    </span>
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => go(step - 1)}
                  aria-label="Previous step"
                  className="rounded-lg p-2 text-text-muted hover:bg-surface-sunk hover:text-text"
                >
                  <ChevronLeft className="h-5 w-5" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={() => setPlaying((p) => !p)}
                  aria-label={playing ? "Pause" : "Play"}
                  className="rounded-lg p-2 text-text-muted hover:bg-surface-sunk hover:text-text"
                >
                  {playing ? <Pause className="h-5 w-5" aria-hidden /> : <Play className="h-5 w-5" aria-hidden />}
                </button>
                <button
                  type="button"
                  onClick={() => go(step + 1)}
                  aria-label="Next step"
                  className="rounded-lg p-2 text-text-muted hover:bg-surface-sunk hover:text-text"
                >
                  <ChevronRight className="h-5 w-5" aria-hidden />
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
