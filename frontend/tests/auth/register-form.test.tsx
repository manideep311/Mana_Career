import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RegisterForm } from "@/components/auth/RegisterForm";
import { ProblemError } from "@/lib/api/fetcher";
import { renderWithProviders, mockPush } from "@/test/utils";

describe("RegisterForm", () => {
  it("submits and redirects on success", async () => {
    const register = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<RegisterForm />, { authValue: { register } });
    await userEvent.type(screen.getByLabelText("Full name"), "Ada Lovelace");
    await userEvent.type(screen.getByLabelText("Email"), "ada@calc.dev");
    await userEvent.type(screen.getByLabelText("Password"), "correct-passphrase");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(register).toHaveBeenCalledWith({
        full_name: "Ada Lovelace",
        email: "ada@calc.dev",
        password: "correct-passphrase",
      }),
    );
    expect(mockPush).toHaveBeenCalledWith("/resume");
  });

  it("shows an email error when the address is already registered", async () => {
    const register = vi.fn().mockRejectedValue(
      new ProblemError("email_taken", 409, { detail: "Email already in use." }),
    );
    renderWithProviders(<RegisterForm />, { authValue: { register } });
    await userEvent.type(screen.getByLabelText("Full name"), "Ada Lovelace");
    await userEvent.type(screen.getByLabelText("Email"), "taken@calc.dev");
    await userEvent.type(screen.getByLabelText("Password"), "correct-passphrase");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/already registered/i)).toBeInTheDocument();
  });
});
