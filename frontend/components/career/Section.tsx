import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * A titled block of a guidance page. Quiet by design: a small serif heading,
 * an optional one-line intro, and the content. `id` makes it linkable.
 */
export function Section({
  id,
  title,
  intro,
  action,
  children,
  className,
}: {
  id?: string;
  title: string;
  intro?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={cn("flex scroll-mt-24 flex-col gap-3", className)}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={headingId} className="font-display text-xl text-text">
          {title}
        </h2>
        {action}
      </div>
      {intro ? <p className="-mt-1 text-sm text-text-muted">{intro}</p> : null}
      {children}
    </section>
  );
}
