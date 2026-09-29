import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center gap-4 px-6">
      <p className="text-sm font-medium text-text-muted">Page not found</p>
      <h1 className="font-display text-3xl text-text">This page isn&apos;t here</h1>
      <p className="text-sm text-text-muted">
        The link may be old, or the page may have moved. Your dashboard has everything
        you&apos;re working on.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link href="/dashboard" className={buttonVariants()}>
          Go to your dashboard
        </Link>
        <Link href="/" className={buttonVariants({ variant: "ghost" })}>
          Home
        </Link>
      </div>
    </main>
  );
}
