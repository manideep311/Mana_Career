import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DashboardPage from "@/app/(app)/dashboard/page";
import type { ResumeOut } from "@/lib/api/types";
import { renderWithProviders } from "@/test/utils";

const strengthStub = {
  strength: async () => ({
    score: 20,
    completeness: {},
    missing: ["Add a project"],
  }),
};

const confirmedResume: ResumeOut = {
  id: "r1",
  title: "CV",
  original_filename: "cv.pdf",
  content_type: "application/pdf",
  size_bytes: 1000,
  page_count: 2,
  status: "extracted",
  parse_error: null,
  is_primary: true,
  confirmed_at: "2026-09-01T00:00:00Z",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

describe("DashboardPage", () => {
  it("greets the user and shows their strength with a link to finish the profile", async () => {
    renderWithProviders(<DashboardPage />, {
      authValue: { user: { full_name: "Ada Lovelace" } },
      api: {
        profile: strengthStub,
        resumes: { list: vi.fn(async () => []) },
      },
    });

    // Greeting renders immediately from the auth context.
    expect(screen.getByText(/Good .*, Ada/)).toBeInTheDocument();

    // The meter appears once the strength query resolves.
    const bar = await screen.findByRole("progressbar", {
      name: /profile strength/i,
    });
    expect(bar).toHaveAttribute("aria-valuenow", "20");

    // Score < 100 -> a nudge to the profile page.
    expect(
      screen.getByRole("link", { name: /complete your profile/i }),
    ).toHaveAttribute("href", "/profile");
  });

  it("nudges the user to upload a résumé when none is confirmed", async () => {
    renderWithProviders(<DashboardPage />, {
      authValue: { user: { full_name: "Ada Lovelace" } },
      api: {
        profile: strengthStub,
        resumes: { list: vi.fn(async () => []) },
      },
    });

    expect(
      await screen.findByText(/finish setting up your profile/i),
    ).toBeInTheDocument();
  });

  it("hides the résumé nudge once a résumé is confirmed", async () => {
    renderWithProviders(<DashboardPage />, {
      authValue: { user: { full_name: "Ada Lovelace" } },
      api: {
        profile: strengthStub,
        resumes: { list: vi.fn(async () => [confirmedResume]) },
      },
    });

    // Wait for the strength query so the page has fully settled.
    await screen.findByRole("progressbar", { name: /profile strength/i });

    // Tie the assertion to the *résumés* query resolving: the nudge is also
    // absent before that query settles (data is `undefined`), so a bare
    // `queryByText` could pass for the wrong reason.
    await waitFor(() =>
      expect(
        screen.queryByText(/finish setting up your profile/i),
      ).toBeNull(),
    );
  });
});
