import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApprovalCard } from "@/components/applications/ApprovalCard";
import type { ApprovalPayloadSnapshot } from "@/lib/api/types";

const snapshot: ApprovalPayloadSnapshot = {
  job: { title: "Staff Engineer", company: "Acme" },
  resume_version_id: "v1",
  cover_letter: { id: "cl1", content: "Dear Hiring Team,\n\nI'm excited to apply." },
  email: {
    id: "em1", to_email: null, to_name: null,
    subject: "Application: Staff Engineer", body: "Please find my materials attached.",
  },
};

function renderCard(over: Partial<Parameters<typeof ApprovalCard>[0]> = {}) {
  const props = {
    snapshot, submitting: false, onApprove: vi.fn(), onReject: vi.fn(), ...over,
  };
  render(<ApprovalCard {...props} />);
  return props;
}

describe("ApprovalCard", () => {
  it("renders the job, cover letter, email, and the safety line", () => {
    renderCard();
    expect(screen.getByText("Review your application for Staff Engineer")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText(/I'm excited to apply/)).toBeInTheDocument();
    expect(screen.getByText("Application: Staff Engineer")).toBeInTheDocument();
    expect(screen.getByLabelText("Send to")).toHaveValue("");
    expect(screen.getByText("Nothing will be sent until you approve it.")).toBeInTheDocument();
  });

  it("won't approve without a valid recipient, then sends the one typed", async () => {
    const { onApprove } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: /approve & send/i }));
    expect(onApprove).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Enter the hiring contact's email address.");
    expect(screen.getByLabelText("Send to")).toHaveAttribute("aria-invalid", "true");

    await userEvent.type(screen.getByLabelText("Send to"), "  jobs@acme.com ");
    await userEvent.type(screen.getByLabelText("Contact name (optional)"), "Priya");
    await userEvent.click(screen.getByRole("button", { name: /approve & send/i }));
    expect(onApprove).toHaveBeenCalledWith({ to_email: "jobs@acme.com", to_name: "Priya" });
  });

  it("prefills a recipient the draft already has", () => {
    renderCard({
      snapshot: { ...snapshot, email: { ...snapshot.email, to_email: "hr@acme.com", to_name: "HR" } },
    });
    expect(screen.getByLabelText("Send to")).toHaveValue("hr@acme.com");
    expect(screen.getByLabelText("Contact name (optional)")).toHaveValue("HR");
  });

  it("says where the email really goes on this server", () => {
    renderCard({ delivery: "redirect", applicantEmail: "me@example.com" });
    expect(screen.getByText(/goes to your own inbox \(me@example.com\)/)).toBeInTheDocument();
  });

  it("is honest when the server sends nothing, and when it sends for real", () => {
    const { unmount } = render(
      <ApprovalCard snapshot={snapshot} submitting={false} onApprove={vi.fn()} onReject={vi.fn()} delivery="console" />,
    );
    expect(screen.getByText(/doesn't send real email/)).toBeInTheDocument();
    unmount();
    renderCard({ delivery: "live" });
    expect(screen.getByText(/with a copy to you/)).toBeInTheDocument();
  });

  it("rejects without a recipient and disables while submitting", async () => {
    const { onReject } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: /don't send/i }));
    expect(onReject).toHaveBeenCalledOnce();
  });

  it("disables the decline button while a decision is in flight", () => {
    renderCard({ submitting: true });
    expect(screen.getByRole("button", { name: /don't send/i })).toBeDisabled();
  });
});

describe("ApprovalCard email confirmation", () => {
  it("locks sending until the address is confirmed when real email is on", () => {
    renderCard({ delivery: "redirect", emailConfirmed: false });
    expect(screen.getByRole("button", { name: /approve & send/i })).toBeDisabled();
    expect(screen.getByRole("note")).toHaveTextContent(/Confirm your email address before sending/);
  });

  it("doesn't lock anything when the server sends no real email", () => {
    renderCard({ delivery: "console", emailConfirmed: false });
    expect(screen.getByRole("button", { name: /approve & send/i })).toBeEnabled();
    expect(screen.queryByRole("note")).toBeNull();
  });
});
