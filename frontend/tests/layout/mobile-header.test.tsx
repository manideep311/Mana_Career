import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { mockPush, renderWithProviders } from "@/test/utils";
import { MobileHeader } from "@/components/layout/MobileHeader";

const user = { full_name: "Asha Rao", email: "asha@example.com" };

describe("MobileHeader", () => {
  it("shows the account menu with who's signed in and the pages the bottom bar leaves out", async () => {
    renderWithProviders(<MobileHeader />, { authValue: { user }, route: "/dashboard" });
    const button = screen.getByRole("button", { name: "Account menu" });
    expect(button).toHaveTextContent("AR");
    expect(button).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("menu", { name: "Account" });
    expect(menu).toHaveTextContent("Asha Rao");
    expect(menu).toHaveTextContent("asha@example.com");
    expect(screen.getByRole("menuitem", { name: "Growth" })).toHaveAttribute("href", "/insights");
    expect(screen.getByRole("menuitem", { name: "Activity" })).toHaveAttribute("href", "/activity");
    expect(screen.getByRole("menuitem", { name: "Profile" })).toHaveAttribute("href", "/profile");
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Growth" })).toHaveFocus());
  });

  it("signs out and returns to sign-in", async () => {
    const logout = vi.fn(async () => {});
    renderWithProviders(<MobileHeader />, { authValue: { user, logout } });
    await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(logout).toHaveBeenCalledOnce();
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes with Escape and gives focus back to the button", async () => {
    renderWithProviders(<MobileHeader />, { authValue: { user } });
    const button = screen.getByRole("button", { name: "Account menu" });
    await userEvent.click(button);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(button).toHaveFocus();
  });

  it("closes when tapping outside", async () => {
    renderWithProviders(
      <div>
        <MobileHeader />
        <p>elsewhere</p>
      </div>,
      { authValue: { user } },
    );
    await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
    await userEvent.click(screen.getByText("elsewhere"));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("falls back to the email initial when there's no name", () => {
    renderWithProviders(<MobileHeader />, {
      authValue: { user: { full_name: "", email: "zed@example.com" } },
    });
    expect(screen.getByRole("button", { name: "Account menu" })).toHaveTextContent("Z");
  });
});
