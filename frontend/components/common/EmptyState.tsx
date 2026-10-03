import type { ReactNode } from "react";

import Image from "next/image";

import type { PageArt } from "@/lib/page-art";

/**
 * A calm "nothing here yet" box. With `art`, a small scene sits on top (or, in
 * the `compact` form used for repeated profile sections, a thumbnail beside
 * the words). The picture is decorative; the title carries the meaning.
 */
export function EmptyState({
  title,
  description,
  action,
  art,
  compact = false,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  art?: PageArt;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <section
        role="status"
        className="flex items-center gap-4 rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-1)]"
      >
        {art ? (
          <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-xl">
            <Image
              src={art.src}
              alt=""
              fill
              sizes="96px"
              placeholder="blur"
              blurDataURL={art.blur}
              className="object-cover"
            />
          </div>
        ) : null}
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="text-base font-semibold text-text">{title}</h2>
          {description ? <p className="text-sm text-text-muted">{description}</p> : null}
          {action ? <div className="mt-2">{action}</div> : null}
        </div>
      </section>
    );
  }

  return (
    <section
      role="status"
      className="mx-auto max-w-md overflow-hidden rounded-[var(--radius)] border border-border bg-surface text-center shadow-[var(--shadow-1)]"
    >
      {art ? (
        <div className="relative aspect-[16/9]">
          <Image
            src={art.src}
            alt=""
            fill
            sizes="(min-width: 768px) 448px, 100vw"
            placeholder="blur"
            blurDataURL={art.blur}
            className="object-cover"
          />
        </div>
      ) : null}
      <div className="p-8">
        <h2 className="text-lg font-semibold text-text">{title}</h2>
        {description ? <p className="mt-2 text-pretty text-sm text-text-muted">{description}</p> : null}
        {action ? <div className="mt-4">{action}</div> : null}
      </div>
    </section>
  );
}
