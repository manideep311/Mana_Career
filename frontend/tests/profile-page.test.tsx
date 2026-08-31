import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProfilePage from "@/app/(app)/profile/page";
import { renderWithProviders } from "@/test/utils";

/**
 * A profile with every sub-entity list empty. `SubEntityList` renders its own
 * empty-state `<h2>` ("No experiences yet." etc.) in that case, so the section
 * headings below are asserted with EXACT name strings — a `/Experience/i` regex
 * would match both the section `<h2>` and the empty-state `<h2>` and make
 * `getByRole` throw on multiple matches.
 */
const profile = {
  id: "p1",
  user_id: "u1",
  location: "Berlin",
  profile_strength: { score: 20, completeness: {}, missing: [] },
  completeness: 20,
  experiences: [],
  education: [],
  projects: [],
  certifications: [],
} as never;

function makeApi() {
  return {
    profile: {
      get: vi.fn().mockResolvedValue(profile),
      strength: vi.fn().mockResolvedValue({
        score: 20,
        completeness: {},
        missing: ["Add a project"],
      }),
      update: vi.fn().mockResolvedValue({}),
      items: { list: vi.fn().mockResolvedValue([]) },
    },
  };
}

describe("ProfilePage", () => {
  it("renders the title, every section heading, and the strength meter", async () => {
    renderWithProviders(<ProfilePage />, { api: makeApi() });

    // The page body (title + section headings) renders once the profile query
    // resolves — wait on one section heading, then assert the rest in sync.
    expect(
      await screen.findByRole("heading", { name: "Work experience" }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("heading", { level: 1, name: "Your profile" }),
    ).toBeInTheDocument();

    for (const name of ["Education", "Projects", "Certifications"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }

    // Strength meter loads independently of the profile query.
    expect(
      await screen.findByRole("progressbar", { name: /profile strength/i }),
    ).toBeInTheDocument();
  });

  it("offers a retry when the profile fails to load", async () => {
    const api = makeApi();
    api.profile.get = vi.fn().mockRejectedValue(new Error("boom"));

    renderWithProviders(<ProfilePage />, { api });

    expect(
      await screen.findByRole("button", { name: /try again/i }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { level: 1, name: "Your profile" }),
    ).not.toBeInTheDocument();
  });
});
