"use client";

import { useEffect } from "react";

import Image from "next/image";
import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { PAGE_ART } from "@/lib/page-art";

/**
 * What a route shows when rendering throws. Calm, no stack traces or raw
 * messages (they can carry internals); the digest lets support find the
 * server log line.
 */
export function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col items-start gap-4 py-12">
      <div className="relative aspect-[16/9] w-full overflow-hidden rounded-2xl shadow-[var(--shadow-2)]">
        <Image
          src={PAGE_ART.error.src}
          alt=""
          fill
          sizes="(min-width: 768px) 448px, 100vw"
          placeholder="blur"
          blurDataURL={PAGE_ART.error.blur}
          className="object-cover"
        />
      </div>
      <h1 className="font-display text-3xl text-text">Something went wrong on this page</h1>
      <p className="text-sm text-text-muted">
        Your work is saved. Try again, and if it keeps happening, head back to your
        dashboard and come back to this later.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button onClick={reset}>Try again</Button>
        <Link href="/dashboard" className={buttonVariants({ variant: "outline" })}>
          Go to your dashboard
        </Link>
      </div>
      {error.digest ? (
        <p className="text-xs text-text-muted">Reference: {error.digest}</p>
      ) : null}
    </div>
  );
}
