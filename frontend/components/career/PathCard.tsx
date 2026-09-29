import Link from "next/link";

import { ArrowRight } from "lucide-react";

import { FitChip } from "@/components/career/FitChip";
import type { CareerPath } from "@/lib/api/types";

/** One suggested direction in the list: what it is, how far, and why. */
export function PathCard({ path }: { path: CareerPath }) {
  const core = path.have.length + path.missing.length;
  return (
    <li>
      <Link
        href={`/career/${path.slug}`}
        className="group flex flex-col gap-2 rounded-[var(--radius)] border border-border bg-surface p-5 shadow-[var(--shadow-1)] transition-colors hover:border-accent/40 animate-rise"
      >
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-display text-xl text-text">{path.title}</span>
          <FitChip fit={path.fit} label={path.fit_label} />
          {path.stated_target ? (
            <span className="text-xs font-medium text-accent">Your stated goal</span>
          ) : null}
        </span>
        <span className="text-sm text-text-muted">{path.why}</span>
        <span className="flex items-center justify-between gap-3 text-xs text-text-muted">
          <span>
            {path.have.length} of {core} core skills · {path.job_count} role
            {path.job_count === 1 ? "" : "s"} looked at
          </span>
          <ArrowRight
            aria-hidden
            className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
          />
        </span>
      </Link>
    </li>
  );
}
