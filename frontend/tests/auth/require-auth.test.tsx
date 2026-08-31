import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { renderWithProviders, mockReplace } from "@/test/utils";

describe("RequireAuth", () => {
  it("renders children when authed", () => {
    renderWithProviders(<RequireAuth>secret</RequireAuth>, { authValue: { status: "authed" } });
    expect(screen.getByText("secret")).toBeInTheDocument();
  });
  it("redirects to /login when anon", async () => {
    renderWithProviders(<RequireAuth>secret</RequireAuth>, { authValue: { status: "anon" } });
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });
});
