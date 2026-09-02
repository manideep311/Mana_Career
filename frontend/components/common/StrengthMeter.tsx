import type { CSSProperties } from "react";

import type { StrengthDimension } from "@/lib/api/types";

/**
 * A labelled profile-strength bar.
 *
 * The band colour comes from a semantic token — `--positive` (>=75),
 * `--warning` (>=40) or `--danger` (<40) — handed to the fill via a
 * `--meter` custom property so no raw hex ever lands in the markup.
 */
function bandColour(score: number): string {
  if (score >= 75) return "var(--positive)";
  if (score >= 40) return "var(--warning)";
  return "var(--danger)";
}

export function StrengthMeter({
  score,
  missing,
  dimensions,
}: {
  score: number;
  missing: string[];
  dimensions?: StrengthDimension[];
}) {
  const pct = Math.max(0, Math.min(100, Math.round(score)));
  const hasBreakdown = dimensions != null && dimensions.length > 0;

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-medium text-text-muted">Profile strength</h2>
        <span className="font-[var(--font-inter)] text-2xl font-semibold tabular-nums text-text">
          {pct}
          <span className="ml-0.5 text-base font-normal text-text-muted">
            /100
          </span>
        </span>
      </div>

      <div
        role="progressbar"
        aria-label="Profile strength"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2.5 w-full overflow-hidden rounded-full bg-surface-sunk"
        style={{ ["--meter" as string]: bandColour(score) } as CSSProperties}
      >
        <div
          className="h-full rounded-full bg-[var(--meter)] transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      <details className="text-sm text-text-muted">
        <summary className="cursor-pointer select-none font-medium text-text">
          How this is calculated
        </summary>
        <p className="mt-2">
          Your score reflects how many key sections of your profile are filled
          in — each section you finish adds points toward 100.
        </p>
      </details>

      {hasBreakdown ? (
        // When the backend hands us a per-dimension breakdown, show which
        // parts of the score are earned and which are still open.
        <div className="flex flex-col gap-2">
          {score >= 100 || dimensions.every((d) => d.met) ? (
            <p className="text-sm font-medium text-positive">
              Your profile is complete. Nice work.
            </p>
          ) : null}
          <p className="text-sm font-medium text-text">
            Where your score comes from
          </p>
          <ul className="flex flex-col gap-3">
            {dimensions.map((dim) => {
              const share =
                dim.max > 0
                  ? Math.max(
                      0,
                      Math.min(100, Math.round((dim.earned / dim.max) * 100)),
                    )
                  : 0;
              return (
                <li key={dim.key} className="flex flex-col gap-1.5">
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="text-text">{dim.label}</span>
                    <span className="tabular-nums text-text-muted">
                      {dim.earned}/{dim.max}
                    </span>
                  </div>
                  <div
                    className="h-1.5 w-full overflow-hidden rounded-full bg-surface-sunk"
                    style={
                      {
                        ["--meter" as string]: dim.met
                          ? "var(--positive)"
                          : "var(--warning)",
                      } as CSSProperties
                    }
                  >
                    <div
                      className="h-full rounded-full bg-[var(--meter)]"
                      style={{ width: `${share}%` }}
                    />
                  </div>
                  {!dim.met ? (
                    <p className="text-sm text-text-muted">
                      <span aria-hidden="true" className="text-warning">
                        △
                      </span>{" "}
                      {dim.hint}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : missing.length > 0 ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-text">To raise your score</p>
          <ul className="flex flex-col gap-1.5">
            {missing.map((item) => (
              <li key={item} className="text-sm text-text-muted">
                <span aria-hidden="true" className="text-warning">
                  △
                </span>{" "}
                {item}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm font-medium text-positive">
          Your profile is complete. Nice work.
        </p>
      )}
    </section>
  );
}
