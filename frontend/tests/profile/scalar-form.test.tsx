import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProfileScalarForm } from "@/components/profile/ProfileScalarForm";
import { renderWithProviders } from "@/test/utils";

const base = { id: "p1", location: "Berlin", career_goals: "", github_url: null } as never;

describe("ProfileScalarForm", () => {
  it("prefills from the profile and saves only what changed", async () => {
    const update = vi.fn().mockResolvedValue({});
    renderWithProviders(<ProfileScalarForm profile={base} />, {
      api: { profile: { update } },
    });
    const goals = screen.getByLabelText(/career goals/i);
    expect(screen.getByLabelText(/location/i)).toHaveValue("Berlin");
    await userEvent.type(goals, "Ship models.");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith({ career_goals: "Ship models." }),
    );
  });

  it("rejects a non-URL github link", async () => {
    renderWithProviders(<ProfileScalarForm profile={base} />, { api: { profile: { update: vi.fn() } } });
    await userEvent.type(screen.getByLabelText(/github/i), "not a url");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/valid url/i)).toBeInTheDocument();
  });
});
