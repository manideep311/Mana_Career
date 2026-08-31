/**
 * Small form-serialization helpers shared by the profile forms.
 *
 * Both take `unknown` so callers can pass a raw form value, a nullable API
 * field, or `undefined` without pre-coercing.
 */

/** Split a comma-separated string into trimmed, non-empty parts. */
export function csvToList(value: unknown): string[] {
  return (typeof value === "string" ? value : "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

/** Join a list into a `", "`-separated string; anything not an array yields `""`. */
export function listToCsv(value: unknown): string {
  return Array.isArray(value) ? value.map(String).join(", ") : "";
}
