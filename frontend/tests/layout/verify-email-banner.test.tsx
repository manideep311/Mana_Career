import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import { VerifyEmailBanner } from "@/components/layout/VerifyEmailBanner";

function meta(email_delivery: "console" | "redirect" | "live") {
  return { get: vi.fn(async () => ({ demo_mode: false, ai_writing: true, web_research: false, email_delivery })) };
}

const unverified = { email: "me@example.com", email_verified: false };

describe("VerifyEmailBanner", () => {
  it("asks an unconfirmed user to confirm when real email is on, and resends", async () => {
    const resendVerification = vi.fn(async () => ({ detail: "We've sent a new link to me@example.com." }));
    renderWithProviders(<VerifyEmailBanner />, {
      authValue: { user: unverified },
      api: { meta: meta("redirect"), auth: { resendVerification } },
    });
    const banner = await screen.findByRole("region", { name: "Confirm your email" });
    expect(banner).toHaveTextContent("We sent a link to me@example.com");
    await userEvent.click(screen.getByRole("button", { name: /resend link/i }));
    expect(resendVerification).toHaveBeenCalledOnce();
    expect(await screen.findByText("We've sent a new link to me@example.com.")).toBeInTheDocument();
  });

  it("stays hidden when the server sends no real email", async () => {
    const get = meta("console").get;
    renderWithProviders(<VerifyEmailBanner />, {
      authValue: { user: unverified },
      api: { meta: { get } },
    });
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: "Confirm your email" })).toBeNull();
  });

  it("stays hidden once the address is confirmed", async () => {
    const get = meta("live").get;
    renderWithProviders(<VerifyEmailBanner />, {
      authValue: { user: { ...unverified, email_verified: true } },
      api: { meta: { get } },
    });
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: "Confirm your email" })).toBeNull();
  });
});
