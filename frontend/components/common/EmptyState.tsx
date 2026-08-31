import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <section
      role="status"
      className="mx-auto max-w-md rounded-[var(--radius)] border border-border bg-surface p-8 text-center shadow-[var(--shadow-1)]"
    >
      <h2 className="text-lg font-semibold text-text">{title}</h2>
      {description ? (
        <p className="mt-2 text-sm text-text-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </section>
  );
}
