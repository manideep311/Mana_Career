import Link from "next/link";

import { ArrowRight } from "lucide-react";

import type { CareerNextAction } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/**
 * The few things worth doing next, most useful first. The first is marked as
 * the place to start; each links straight to where it gets done.
 */
export function NextActions({ actions }: { actions: CareerNextAction[] }) {
  return (
    <ol className="flex flex-col gap-2">
      {actions.map((action, i) => {
        const body = (
          <>
            <span
              aria-hidden
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums",
                i === 0 ? "bg-accent text-accent-fg" : "bg-surface-sunk text-text-muted",
              )}
            >
              {i + 1}
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-sm font-semibold text-text">{action.title}</span>
              <span className="text-sm text-text-muted">{action.detail}</span>
            </span>
            {action.href ? (
              <ArrowRight
                aria-hidden
                className="mt-1 h-4 w-4 shrink-0 text-text-muted transition-transform group-hover:translate-x-0.5"
              />
            ) : null}
          </>
        );
        const cls =
          "group flex items-start gap-3 rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-1)] animate-rise";
        return (
          <li key={`${action.kind}-${action.title}`}>
            {action.href ? (
              <Link href={action.href} className={cn(cls, "transition-colors hover:border-accent/40")}>
                {body}
              </Link>
            ) : (
              <div className={cls}>{body}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
