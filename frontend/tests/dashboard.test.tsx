import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DashboardPage from "@/app/(app)/dashboard/page";
import { renderWithProviders } from "@/test/utils";

describe("DashboardPage", () => {
  it("greets the user and shows their strength with a link to finish the profile", async () => {
    renderWithProviders(<DashboardPage />, {
      authValue: { user: { full_name: "Ada Lovelace" } },
      api: {
        profile: {
          strength: async () => ({
            score: 20,
            completeness: {},
            missing: ["Add a project"],
          }),
        },
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
});
