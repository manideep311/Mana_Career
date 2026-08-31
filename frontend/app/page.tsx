import Link from "next/link";

import { EmptyState } from "@/components/common/EmptyState";

export default function Page() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-8 px-6 py-16">
      <div>
        <p className="text-sm font-medium uppercase tracking-wide text-accent">
          Mana Career
        </p>
        <h1 className="mt-3 text-4xl font-semibold leading-tight text-text">
          Your next opportunity starts here.
        </h1>
        <p className="mt-4 text-base text-text-muted">
          Mana Career helps you discover better opportunities, understand your
          career gaps, and prepare stronger applications — with you always in
          control.
        </p>
        <Link
          href="/register"
          className="mt-6 inline-block rounded-[var(--radius)] bg-accent px-5 py-2.5 text-sm font-medium text-accent-fg shadow-[var(--shadow-1)]"
        >
          Get started
        </Link>
      </div>
      <EmptyState
        title="Your career workspace is ready."
        description="Sign in to upload a résumé and see where you stand."
      />
    </main>
  );
}
