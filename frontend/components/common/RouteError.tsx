"use client";

import { useEffect } from "react";

import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";

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
    <div role="alert" className="mx-auto flex max-w-md flex-col items-start gap-4 py-16">
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
