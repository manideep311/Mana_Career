"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";

const WORK_MODES = ["remote", "hybrid", "onsite"] as const;

const SENIORITY = [
  "intern",
  "junior",
  "mid",
  "senior",
  "staff",
  "principal",
  "lead",
  "manager",
] as const;

const SALARY_MINS = [
  { value: "100000", label: "$100k+" },
  { value: "150000", label: "$150k+" },
  { value: "200000", label: "$200k+" },
] as const;

/** URL keys this control owns — governs when "Clear filters" appears. */
const TRACKED = [
  "q",
  "work_mode",
  "seniority",
  "salary_min",
  "has_match",
  "sort",
] as const;

const DEBOUNCE_MS = 300;

const selectClass =
  "h-9 rounded-[var(--radius)] border border-border bg-surface px-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]";

const titleCase = (value: string): string =>
  value.charAt(0).toUpperCase() + value.slice(1);

/**
 * Search + filter controls for the jobs grid. Every value is read straight from
 * the URL query string and each change writes back through `router.replace`, so
 * the URL stays the single source of truth (shareable, back-button friendly).
 * The only local state is the debounce timer for the search box.
 */
export function JobFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const current = (key: string): string => searchParams.get(key) ?? "";

  const write = (mutate: (params: URLSearchParams) => void): void => {
    const next = new URLSearchParams(searchParams.toString());
    mutate(next);
    for (const [key, value] of [...next.entries()]) {
      if (!value) next.delete(key);
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  };

  const set = (key: string, value: string): void =>
    write((params) => {
      if (value) params.set(key, value);
      else params.delete(key);
    });

  const onSearch = (value: string): void => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => set("q", value.trim()), DEBOUNCE_MS);
  };

  const clearAll = (): void => {
    if (timer.current) clearTimeout(timer.current);
    write((params) => {
      for (const key of TRACKED) params.delete(key);
    });
  };

  const hasFilters = TRACKED.some((key) => current(key) !== "");

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex min-w-52 flex-1 flex-col gap-1">
        <label
          htmlFor="job-search"
          className="text-xs font-medium text-text-muted"
        >
          Search
        </label>
        <input
          id="job-search"
          type="search"
          key={current("q")}
          defaultValue={current("q")}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Title, company, keyword…"
          className="h-9 rounded-[var(--radius)] border border-border bg-surface px-3 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label
          htmlFor="job-work-mode"
          className="text-xs font-medium text-text-muted"
        >
          Work mode
        </label>
        <select
          id="job-work-mode"
          value={current("work_mode")}
          onChange={(event) => set("work_mode", event.target.value)}
          className={selectClass}
        >
          <option value="">Any</option>
          {WORK_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {titleCase(mode)}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label
          htmlFor="job-seniority"
          className="text-xs font-medium text-text-muted"
        >
          Seniority
        </label>
        <select
          id="job-seniority"
          value={current("seniority")}
          onChange={(event) => set("seniority", event.target.value)}
          className={selectClass}
        >
          <option value="">Any</option>
          {SENIORITY.map((level) => (
            <option key={level} value={level}>
              {titleCase(level)}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label
          htmlFor="job-salary-min"
          className="text-xs font-medium text-text-muted"
        >
          Min salary
        </label>
        <select
          id="job-salary-min"
          value={current("salary_min")}
          onChange={(event) => set("salary_min", event.target.value)}
          className={selectClass}
        >
          <option value="">Any</option>
          {SALARY_MINS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="job-sort" className="text-xs font-medium text-text-muted">
          Sort
        </label>
        <select
          id="job-sort"
          value={current("sort")}
          onChange={(event) => set("sort", event.target.value)}
          className={selectClass}
        >
          <option value="">Newest</option>
          <option value="match">Best match</option>
        </select>
      </div>

      <label
        htmlFor="job-has-match"
        className="flex h-9 items-center gap-2 text-sm text-text-muted"
      >
        <input
          id="job-has-match"
          type="checkbox"
          checked={current("has_match") === "true"}
          onChange={(event) =>
            set("has_match", event.target.checked ? "true" : "")
          }
        />
        Has match
      </label>

      {hasFilters ? (
        <Button type="button" variant="ghost" size="sm" onClick={clearAll}>
          Clear filters
        </Button>
      ) : null}
    </div>
  );
}
