import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";
import { VerifyEmail } from "@/components/auth/VerifyEmail";
import { LoginForm } from "@/components/auth/LoginForm";
import { ProblemError } from "@/lib/api/fetcher";

function openLink(path: string) {
  window.history.replaceState(null, "", path);
}

afterEach(() => openLink("/"));

describe("forgot password", () => {
  it("is linked from sign in", () => {
    renderWithProviders(<LoginForm />);
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("shows the server's neutral confirmation, whoever asks", async () => {
    const forgotPassword = vi.fn(async () => ({
      detail: "If an account exists for that address, we've sent a link to reset the password.",
    }));
    renderWithProviders(<ForgotPasswordForm />, { api: { auth: { forgotPassword } } });
    await userEvent.type(screen.getByLabelText("Email"), "me@example.com");
    await userEvent.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/If an account exists/);
    expect(forgotPassword).toHaveBeenCalledWith("me@example.com");
  });
});

describe("reset password", () => {
  it("without a token in the link, offers a new one", async () => {
    openLink("/reset-password");
    renderWithProviders(<ResetPasswordForm />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid or has expired/);
    expect(screen.getByRole("link", { name: /request a new link/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("uses the token from the link, then clears it from the address bar", async () => {
    openLink("/reset-password#token=tok-123");
    const resetPassword = vi.fn(async () => undefined);
    renderWithProviders(<ResetPasswordForm />, { api: { auth: { resetPassword } } });
    await waitFor(() => expect(window.location.hash).toBe(""));

    await userEvent.type(await screen.findByLabelText("New password"), "brand-new-passphrase");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "different-passphrase");
    await userEvent.click(screen.getByRole("button", { name: /set new password/i }));
    expect(await screen.findByText("The passwords don't match.")).toBeInTheDocument();
    expect(resetPassword).not.toHaveBeenCalled();

    await userEvent.clear(screen.getByLabelText("Confirm new password"));
    await userEvent.type(screen.getByLabelText("Confirm new password"), "brand-new-passphrase");
    await userEvent.click(screen.getByRole("button", { name: /set new password/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/signed out everywhere/);
    expect(resetPassword).toHaveBeenCalledWith({
      token: "tok-123",
      new_password: "brand-new-passphrase",
    });
  });

  it("an expired link switches to the request-a-new-link view", async () => {
    openLink("/reset-password#token=old");
    const resetPassword = vi.fn(async () => {
      throw new ProblemError("invalid_link", 400, { detail: "expired" });
    });
    renderWithProviders(<ResetPasswordForm />, { api: { auth: { resetPassword } } });
    await userEvent.type(await screen.findByLabelText("New password"), "brand-new-passphrase");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "brand-new-passphrase");
    await userEvent.click(screen.getByRole("button", { name: /set new password/i }));
    expect(await screen.findByRole("link", { name: /request a new link/i })).toBeInTheDocument();
  });
});

describe("verify email", () => {
  it("confirms once on open and refreshes the signed-in user", async () => {
    openLink("/verify-email#token=v-1");
    const verifyEmail = vi.fn(async () => undefined);
    const reloadUser = vi.fn(async () => undefined);
    renderWithProviders(<VerifyEmail />, {
      api: { auth: { verifyEmail } },
      authValue: { status: "authed", reloadUser },
    });
    expect(await screen.findByText(/Your email address is confirmed/)).toBeInTheDocument();
    expect(verifyEmail).toHaveBeenCalledTimes(1);
    expect(verifyEmail).toHaveBeenCalledWith("v-1");
    await waitFor(() => expect(reloadUser).toHaveBeenCalled());
    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/dashboard");
  });

  it("explains an invalid link and points signed-out people to sign in", async () => {
    openLink("/verify-email#token=bad");
    const verifyEmail = vi.fn(async () => {
      throw new ProblemError("invalid_link", 400, null);
    });
    renderWithProviders(<VerifyEmail />, {
      api: { auth: { verifyEmail } },
      authValue: { status: "anon" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid or has expired/);
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });
});
