import type { UseFormSetError } from "react-hook-form";

import { ProblemError } from "@/lib/api/fetcher";

/** The subset of an RFC 9457 problem body the forms read. */
interface ProblemBody {
  detail?: string;
  errors?: { loc?: (string | number)[]; msg?: string }[];
}

/**
 * Maps a thrown API error onto react-hook-form and reports whether it did.
 *
 * - `ProblemError` with `code === "validation_error"` and a `problem.errors`
 *   array: calls `setError` for each entry, keyed by the dotted `loc` path
 *   below `body` (`["body", "email"] -> "email"`;
 *   `["body", "experiences", 0, "company"] -> "experiences.0.company"`).
 *   Returns `true`.
 * - Any other `ProblemError`: sets a `root` error from `problem.detail`, or a
 *   generic fallback when there is none. Returns `true`.
 * - Anything else (a plain `Error`, a network failure, ...): touches nothing
 *   and returns `false` so the caller can apply its own generic message.
 *
 * Callers that need form-specific handling (e.g. a dedicated `email_taken`
 * message) should run that check first and only fall through to this helper.
 */
export function applyProblemToForm(
  err: unknown,
  setError: UseFormSetError<any>,
): boolean {
  if (!(err instanceof ProblemError)) return false;

  const problem = (err.problem ?? {}) as ProblemBody;

  if (err.code === "validation_error" && Array.isArray(problem.errors)) {
    for (const item of problem.errors) {
      const loc = Array.isArray(item.loc) ? item.loc : [];
      // Key on the full dotted path below `body` (e.g.
      // `["body","experiences",0,"company"] -> "experiences.0.company"`) so a
      // nested/row validation error reaches the matching rhf field, not just a
      // bare tail segment. Falls through to "" (skipped) for an empty `loc`.
      const field =
        loc[0] === "body" ? loc.slice(1).join(".") : loc.join(".");
      if (field) {
        setError(field, { message: item.msg ?? "This value is not valid." });
      }
    }
    return true;
  }

  setError("root", {
    message: problem.detail ?? "Something went wrong. Try again.",
  });
  return true;
}
