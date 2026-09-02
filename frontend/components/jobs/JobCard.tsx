import Link from "next/link";

import { MatchBadge } from "@/components/jobs/MatchBadge";
import type { JobCard as JobCardT } from "@/lib/api/types";

/** Currency code → symbol; unknown codes fall back to `"<CODE> "`. */
const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  CAD: "$",
  AUD: "$",
  NZD: "$",
  SGD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CNY: "¥",
  INR: "₹",
};

/** Pay-period → short suffix; unknown periods fall back to `"/<period>"`. */
const PERIOD_SUFFIX: Record<string, string> = {
  year: "/yr",
  yearly: "/yr",
  annual: "/yr",
  annum: "/yr",
  month: "/mo",
  monthly: "/mo",
  week: "/wk",
  weekly: "/wk",
  day: "/day",
  daily: "/day",
  hour: "/hr",
  hourly: "/hr",
};

/** `1000 → "1k"`, `1500 → "1.5k"`, `190000 → "190k"`, `90 → "90"`. */
function abbrevAmount(value: number): string {
  if (Math.abs(value) < 1000) return `${value}`;
  const thousands = Math.round((value / 1000) * 10) / 10;
  return `${Number.isInteger(thousands) ? thousands : thousands.toFixed(1)}k`;
}

/**
 * A compact salary string for a posting — `"$190k–$240k/yr"` style.
 * Returns `null` when the posting carries no salary at all.
 */
export function fmtSalary(job: JobCardT): string | null {
  const { salary_min, salary_max, salary_currency, salary_period } = job;
  if (salary_min == null && salary_max == null) return null;

  const prefix = salary_currency
    ? (CURRENCY_SYMBOLS[salary_currency.toUpperCase()] ?? `${salary_currency} `)
    : "";
  const suffix = salary_period
    ? (PERIOD_SUFFIX[salary_period.toLowerCase()] ?? `/${salary_period}`)
    : "";

  const low = salary_min != null ? `${prefix}${abbrevAmount(salary_min)}` : null;
  const high = salary_max != null ? `${prefix}${abbrevAmount(salary_max)}` : null;
  const range =
    low != null && high != null ? `${low}–${high}` : (low ?? high ?? "");

  return `${range}${suffix}`;
}

const MAX_SKILL_CHIPS = 5;

/** One job posting as it appears in the discovery grid. Links to `/jobs/:id`. */
export function JobCard({ job }: { job: JobCardT }) {
  const title = job.title || "Untitled role";
  const metaLine = [job.company, job.location].filter(Boolean).join(" · ");
  const tags: { key: string; value: string }[] = [];
  if (job.work_mode) tags.push({ key: "work_mode", value: job.work_mode });
  if (job.seniority) tags.push({ key: "seniority", value: job.seniority });
  if (job.employment_type)
    tags.push({ key: "employment_type", value: job.employment_type });
  const salary = fmtSalary(job);
  const skills = job.required_skills.slice(0, MAX_SKILL_CHIPS);
  const overflow = job.required_skills.length - skills.length;

  return (
    <Link
      href={`/jobs/${job.id}`}
      className="flex flex-col gap-3 rounded-[var(--radius)] border border-border bg-surface p-4 transition-colors hover:bg-surface-sunk"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-semibold text-text">{title}</span>
          {metaLine ? (
            <span className="text-xs text-text-muted">{metaLine}</span>
          ) : null}
        </div>
        {job.is_seed ? (
          <span className="shrink-0 rounded-full bg-surface-sunk px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-text-muted">
            Sample
          </span>
        ) : null}
        {/* match score: Phase 5 */}
        <MatchBadge
          score={job.match_score}
          band={job.match_band}
          status={job.match_status}
        />
      </div>

      {tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag.key}
              className="rounded-full border border-border px-2 py-0.5 text-xs capitalize text-text-muted"
            >
              {tag.value}
            </span>
          ))}
        </div>
      ) : null}

      {salary ? (
        <span className="text-xs font-medium text-text">{salary}</span>
      ) : null}

      {skills.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {skills.map((skill) => (
            <span
              key={skill.slug}
              className="rounded-full bg-surface-sunk px-2 py-0.5 text-xs text-text-muted"
            >
              {skill.label}
            </span>
          ))}
          {overflow > 0 ? (
            <span className="rounded-full bg-surface-sunk px-2 py-0.5 text-xs text-text-muted">
              +{overflow}
            </span>
          ) : null}
        </div>
      ) : null}
    </Link>
  );
}
