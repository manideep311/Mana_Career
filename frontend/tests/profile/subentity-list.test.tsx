import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SubEntityList } from "@/components/profile/SubEntityList";
import { renderWithProviders } from "@/test/utils";

function api(over: Record<string, unknown> = {}) {
  return {
    profile: {
      items: {
        list: vi.fn().mockResolvedValue([
          { id: "a", order_index: 0, title: "Eng", company: "Acme" },
          { id: "b", order_index: 1, title: "Sr Eng", company: "Beta" },
        ]),
        add: vi.fn().mockResolvedValue({}),
        update: vi.fn().mockResolvedValue({}),
        remove: vi.fn().mockResolvedValue(undefined),
        reorder: vi.fn().mockResolvedValue([]),
        ...over,
      },
    },
  };
}

describe("SubEntityList", () => {
  it("lists items and reorders", async () => {
    const a = api();
    renderWithProviders(<SubEntityList section="experiences" />, { api: a });
    expect(await screen.findByText(/Eng · Acme/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: /move down/i })[0]);
    await waitFor(() =>
      expect(a.profile.items.reorder).toHaveBeenCalledWith("experiences", ["b", "a"]),
    );
  });

  it("deletes an item", async () => {
    const a = api();
    renderWithProviders(<SubEntityList section="experiences" />, { api: a });
    await screen.findByText(/Eng · Acme/);
    await userEvent.click(screen.getAllByRole("button", { name: /delete/i })[0]);
    await waitFor(() => expect(a.profile.items.remove).toHaveBeenCalledWith("experiences", "a"));
  });
});
