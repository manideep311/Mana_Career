import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import JobsPage from "@/app/(app)/jobs/page";
import type { JobCard as JobCardT } from "@/lib/api/types";
import { renderWithProviders } from "@/test/utils";

const sampleJob: JobCardT = {
  id: "j1",
  title: "Senior ML Engineer",
  company: "Nimbus AI",
  location: "Remote",
  work_mode: "remote",
  seniority: "senior",
  employment_type: "Full-time",
  salary_min: 190000,
  salary_max: 240000,
  salary_currency: "USD",
  salary_period: "year",
  is_seed: true,
  status: "ready",
  posted_at: null,
  created_at: "2026-08-20T00:00:00Z",
  required_skills: [{ slug: "python", label: "Python", weight: 0.9 }],
  match_score: 88,
  match_band: "good",
  match_status: "ready",
};

describe("JobsPage", () => {
  it("renders the jobs grid and the result count", async () => {
    const list = vi.fn(async () => ({
      items: [sampleJob],
      total: 1,
      limit: 24,
      offset: 0,
    }));

    renderWithProviders(<JobsPage />, { api: { jobs: { list } } });

    expect(await screen.findByText("Senior ML Engineer")).toBeInTheDocument();
    expect(screen.getByText("1 role")).toBeInTheDocument();
    // Phase 5: the per-card match badge renders from the card's match_* fields…
    expect(screen.getByText("88")).toBeInTheDocument();
    // …and the header carries a "Match all" re-score control.
    expect(
      screen.getByRole("button", { name: /match all/i }),
    ).toBeInTheDocument();
  });

  it("shows the empty state when no jobs match", async () => {
    const list = vi.fn(async () => ({
      items: [],
      total: 0,
      limit: 24,
      offset: 0,
    }));

    renderWithProviders(<JobsPage />, { api: { jobs: { list } } });

    expect(await screen.findByText(/no jobs match/i)).toBeInTheDocument();
  });
});
