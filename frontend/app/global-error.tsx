"use client";

import "./globals.css";

/**
 * Last-resort boundary for errors in the root layout itself. It replaces the
 * whole document, so it renders its own <html> and <body> and depends on
 * nothing but the stylesheet.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <main
          role="alert"
          className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-6"
        >
          <h1 className="text-3xl font-semibold text-text">Mana Career hit a problem</h1>
          <p className="text-sm text-text-muted">
            Please try again. If it keeps happening, reload the page in a minute.
          </p>
          <div>
            <button
              type="button"
              onClick={reset}
              className="rounded-[var(--radius)] bg-accent px-4 py-2 text-sm font-medium text-accent-fg"
            >
              Try again
            </button>
          </div>
          {error.digest ? (
            <p className="text-xs text-text-muted">Reference: {error.digest}</p>
          ) : null}
        </main>
      </body>
    </html>
  );
}
