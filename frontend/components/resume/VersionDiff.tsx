import type { ClaimValidation, FieldDelta, ResumeDiff } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const OP_LABEL: Record<FieldDelta["op"], string> = {
  added: "Added",
  removed: "Removed",
  changed: "Changed",
  reordered: "Reordered",
};

const OP_CLASS: Record<FieldDelta["op"], string> = {
  added: "bg-positive-soft text-positive",
  removed: "bg-danger-soft text-danger",
  changed: "bg-accent-soft text-accent",
  reordered: "bg-surface-sunk text-text-muted",
};

/** The text before the first `[` or `.` in a delta path — the section it groups under. */
function sectionOf(path: string): string {
  const m = /^[^[.]+/.exec(path);
  return m ? m[0] : path;
}

const SECTION_TITLE: Record<string, string> = {
  summary: "Summary",
  full_name: "Name",
  email: "Email",
  location: "Location",
  github_url: "GitHub",
  linkedin_url: "LinkedIn",
  portfolio_url: "Portfolio",
  skills: "Skills",
  experiences: "Experience",
  projects: "Projects",
  education: "Education",
  certifications: "Certifications",
};

function displayValue(v: unknown): string {
  if (v == null) return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function DeltaRow({ delta }: { delta: FieldDelta }) {
  return (
    <div className="flex flex-col gap-1 border-t border-border py-2 first:border-t-0 first:pt-0">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold",
            OP_CLASS[delta.op],
          )}
        >
          {OP_LABEL[delta.op]}
        </span>
        <span className="text-xs text-text-muted">{delta.path}</span>
      </div>
      {delta.op === "changed" ? (
        <div className="flex flex-col gap-1 text-sm">
          <p className="text-text-muted line-through decoration-danger/50">
            {displayValue(delta.before)}
          </p>
          <p className="text-text">{displayValue(delta.after)}</p>
        </div>
      ) : (
        <p className="text-sm text-text">
          {displayValue(delta.op === "removed" ? delta.before : delta.after)}
        </p>
      )}
    </div>
  );
}

/**
 * Renders a `ResumeDiff` grouped by top-level section (the text before the
 * first `[` or `.` in each delta's `path`), plus a claim-validation banner
 * when `claimValidation` actually carries fields (it's `{}` for
 * `base_snapshot`/`manual_edit` versions — only `ai_tailored` ones validate
 * claims).
 */
export function VersionDiff({
  diff,
  claimValidation,
}: {
  diff: ResumeDiff;
  claimValidation: Partial<ClaimValidation>;
}) {
  const groups = new Map<string, FieldDelta[]>();
  for (const d of diff.deltas) {
    const key = sectionOf(d.path);
    const list = groups.get(key) ?? [];
    list.push(d);
    groups.set(key, list);
  }

  return (
    <div className="flex flex-col gap-4">
      {claimValidation.checked != null ? (
        <div
          className={cn(
            "rounded-[var(--radius)] border border-border p-3 text-sm",
            claimValidation.passed ? "bg-positive-soft text-positive" : "bg-warning-soft text-warning",
          )}
        >
          {claimValidation.passed
            ? `All ${claimValidation.checked} claims are grounded in your résumé.`
            : `${claimValidation.unsupported?.length ?? 0} of ${claimValidation.checked} claims couldn’t be grounded in your résumé:`}
          {!claimValidation.passed && claimValidation.unsupported?.length ? (
            <ul className="mt-1 list-disc pl-5">
              {claimValidation.unsupported.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {diff.deltas.length === 0 ? (
        <p className="text-sm text-text-muted">No changes from the base résumé.</p>
      ) : (
        [...groups.entries()].map(([section, deltas]) => (
          <div key={section} className="rounded-[var(--radius)] border border-border bg-surface p-3">
            <h3 className="text-sm font-semibold text-text">
              {SECTION_TITLE[section] ?? section}
            </h3>
            <div>
              {deltas.map((d, i) => (
                <DeltaRow key={`${d.path}-${i}`} delta={d} />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
