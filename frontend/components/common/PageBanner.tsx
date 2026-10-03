import type { ReactNode } from "react";

import Image from "next/image";

import type { PageArt } from "@/lib/page-art";

/**
 * A page's header as an illustrated card: the scene across the top, then the
 * title, an optional badge beside it, one line of context and any actions.
 * The picture is decorative (empty alt); the words carry the meaning, and they
 * sit on the card rather than on the art so they always read cleanly.
 */
export function PageBanner({
  art,
  title,
  description,
  badge,
  actions,
}: {
  art: PageArt;
  title: string;
  description?: ReactNode;
  badge?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="overflow-hidden rounded-[24px] border border-border bg-surface shadow-[var(--shadow-2)]">
      <div className="relative aspect-[12/5] sm:aspect-[3/1]">
        <Image
          src={art.src}
          alt=""
          fill
          priority
          sizes="(min-width: 768px) 768px, 100vw"
          placeholder="blur"
          blurDataURL={art.blur}
          className="object-cover"
          style={{ objectPosition: `50% ${art.focusY}%` }}
        />
      </div>
      <div className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-7 sm:py-5">
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl text-text sm:text-3xl">{title}</h1>
            {badge}
          </div>
          {description ? <div className="text-sm leading-relaxed text-text-muted">{description}</div> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
