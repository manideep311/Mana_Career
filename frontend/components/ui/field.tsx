import { cloneElement, type ReactElement } from "react";

import { Label } from "@/components/ui/label";

/**
 * A labelled form control. `children` must be a single control element; its
 * `aria-describedby` is wired to whichever of the `-hint` / `-error` nodes are
 * rendered, so screen readers announce them. `aria-invalid` stays the caller's
 * responsibility.
 */
export function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: ReactElement<{ "aria-describedby"?: string }>;
}) {
  const describedBy = [
    hint ? `${id}-hint` : "",
    error ? `${id}-error` : "",
  ].filter(Boolean);

  const control =
    describedBy.length > 0
      ? cloneElement(children, { "aria-describedby": describedBy.join(" ") })
      : children;

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {control}
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-text-subtle">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
