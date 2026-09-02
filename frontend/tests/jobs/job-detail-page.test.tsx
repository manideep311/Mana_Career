import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders, mockPush } from "@/test/utils";
import JobDetailPage from "@/app/(app)/jobs/[id]/page";
import type { JobDetail } from "@/lib/api/types";

// The match panel has its own suite; here it's a stub so the detail-page tests
// stay off its data hooks.
vi.mock("@/components/jobs/WhyThisMatch", () => ({
  WhyThisMatch: () => <div>why-this-match</div>,
}));

/**
 * A `status: "ready"` job with every `JobDetail` field populated. Per RULING
 * R11 the test never touches `useParams` (it stays `() => ({})` from
 * `test/utils`, so `id === ""`); the `get` / `remove` mocks ignore their
 * argument and drive the whole render + remove flow regardless.
 */
function readyJob(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    id: "j1",
    title: "Senior ML Engineer",
    company: "Acme",
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
    company_domain: "acme.com",
    experience_min_years: 5,
    experience_max_years: 8,
    description: "Own the serving stack.",
    responsibilities: ["Ship models", "Mentor two engineers"],
    preferred_skills: [],
    raw_text: "Senior ML Engineer at Acme...",
    ...overrides,
  };
}

describe("JobDetailPage", () => {
  it("renders a ready seed job with no Remove button", async () => {
    renderWithProviders(<JobDetailPage />, {
      api: { jobs: { get: vi.fn(async () => readyJob()) } },
    });

    await screen.findByText("Senior ML Engineer");
    expect(screen.getByText("Mentor two engineers")).toBeInTheDocument();
    // Phase 5: the <WhyThisMatch> panel replaces the old placeholder copy.
    expect(screen.getByText("why-this-match")).toBeInTheDocument();
    expect(
      screen.queryByText(/lands in the next release/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).toBeNull();
  });

  it("removes a user job and routes back to /jobs", async () => {
    const remove = vi.fn(async () => undefined);

    renderWithProviders(<JobDetailPage />, {
      api: {
        jobs: {
          get: vi.fn(async () => readyJob({ is_seed: false })),
          remove,
        },
      },
    });

    await screen.findByText("Senior ML Engineer");
    await userEvent.click(screen.getByRole("button", { name: /remove/i }));

    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/jobs"));
  });
});
