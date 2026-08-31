import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/LoginForm";
import { ProblemError } from "@/lib/api/fetcher";
import { renderWithProviders, mockPush } from "@/test/utils";

describe("LoginForm", () => {
  it("submits and redirects on success", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<LoginForm />, { authValue: { login } });
    await userEvent.type(screen.getByLabelText("Email"), "a@b.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-passphrase");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(login).toHaveBeenCalledWith({ email: "a@b.com", password: "correct-passphrase" }));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("shows the server message on bad credentials", async () => {
    const login = vi.fn().mockRejectedValue(
      new ProblemError("invalid_credentials", 401, { detail: "That email or password is not right." }),
    );
    renderWithProviders(<LoginForm />, { authValue: { login } });
    await userEvent.type(screen.getByLabelText("Email"), "a@b.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/not right/i)).toBeInTheDocument();
  });
});
