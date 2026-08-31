import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { renderWithProviders } from "@/test/utils";

describe("AppShell", () => {
  it("renders the primary nav and marks the active route", () => {
    renderWithProviders(<AppShell>hi</AppShell>, {
      route: "/profile",
      authValue: { user: { email: "me@x.com" } },
    });
    expect(screen.getAllByRole("link", { name: /profile/i }).length).toBeGreaterThan(0);
    const active = screen.getAllByRole("link", { name: /profile/i })[0];
    expect(active).toHaveAttribute("aria-current", "page");
  });
});
