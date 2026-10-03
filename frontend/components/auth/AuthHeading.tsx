import type { ReactNode } from "react";

import Link from "next/link";

import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/cn";

/** The account pages' header: optional illustration, title, one line. */
export function AuthHeading({
  title,
  description,
  illustration,
  role,
  align = "center",
}: {
  title: string;
  description?: ReactNode;
  illustration?: ReactNode;
  /** "status" / "alert" when the description reports an outcome. */
  role?: "status" | "alert";
  /** Forms read top-down from the left; outcome pages sit centred. */
  align?: "center" | "start";
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3",
        align === "center" ? "items-center text-center" : "items-start text-left",
      )}
    >
      {illustration}
      <h1 className="font-display text-3xl text-text sm:text-[2.1rem]">{title}</h1>
      {description ? (
        <p role={role} className="max-w-md text-base leading-relaxed text-text-muted">
          {description}
        </p>
      ) : null}
    </div>
  );
}

export const authPrimaryClass =
  "inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-accent to-accent-2 px-6 text-base font-semibold text-accent-fg shadow-[0_10px_24px_rgba(90,74,227,0.28)] transition hover:brightness-110";

export const authSecondaryClass =
  "inline-flex h-12 items-center justify-center rounded-xl border border-accent/30 bg-surface px-6 text-base font-semibold text-accent transition hover:bg-accent-soft";

/**
 * The primary next step (with an arrow) and a quieter way out: side by side
 * when both labels fit on one line, otherwise stacked full width.
 */
export function AuthActions({
  primary,
  secondary,
  className,
}: {
  primary: { href: string; label: string };
  secondary?: { href: string; label: string };
  className?: string;
}) {
  return (
    <div className={cn("mt-8 flex flex-wrap gap-3", className)}>
      <Link href={primary.href} className={cn(authPrimaryClass, "grow-[1.25] whitespace-nowrap")}>
        {primary.label}
        <ArrowRight className="h-5 w-5" aria-hidden />
      </Link>
      {secondary ? (
        <Link href={secondary.href} className={cn(authSecondaryClass, "grow whitespace-nowrap")}>
          {secondary.label}
        </Link>
      ) : null}
    </div>
  );
}
