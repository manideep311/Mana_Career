/**
 * The shared root-level form error banner. Renders nothing unless `message` is
 * a non-empty string, so callers can pass `errors.root?.message` directly.
 */
export function FormError({ message }: { message?: unknown }) {
  if (typeof message !== "string" || message === "") return null;

  return (
    <p
      role="alert"
      className="rounded-[var(--radius)] border border-border bg-danger-soft px-3 py-2 text-sm text-danger"
    >
      {message}
    </p>
  );
}
