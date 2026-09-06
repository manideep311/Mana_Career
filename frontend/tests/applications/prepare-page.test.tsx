import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import PrepareApplicationPage from "@/app/(app)/applications/new/[jobId]/page";

describe("PrepareApplicationPage", () => {
  it("renders the header and the builder's start button", async () => {
    renderWithProviders(<PrepareApplicationPage />, {
      api: { applications: { create: vi.fn(), get: vi.fn() }, approvals: { get: vi.fn(), decide: vi.fn() } },
    });
    expect(screen.getByRole("heading", { name: "Prepare application" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /prepare application/i }),
    ).toBeInTheDocument();
  });
});
