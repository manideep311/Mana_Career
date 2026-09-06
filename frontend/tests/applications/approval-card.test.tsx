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
    id: "em1", to_email: "jobs@acme.com", to_name: null,
    subject: "Application: Staff Engineer", body: "Please find my materials attached.",
  },
};

describe("ApprovalCard", () => {
  it("renders the job, cover letter, email, and the safety line", () => {
    render(
      <ApprovalCard snapshot={snapshot} submitting={false} onApprove={vi.fn()} onReject={vi.fn()} />,
    );
    expect(screen.getByText("Review your application for Staff Engineer")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText(/I'm excited to apply/)).toBeInTheDocument();
    expect(screen.getByText("jobs@acme.com")).toBeInTheDocument();
    expect(screen.getByText("Application: Staff Engineer")).toBeInTheDocument();
    expect(
      screen.getByText("Nothing will be sent until you approve it."),
    ).toBeInTheDocument();
  });

  it("fires the callbacks and disables while submitting", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const { rerender } = render(
      <ApprovalCard snapshot={snapshot} submitting={false} onApprove={onApprove} onReject={onReject} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /approve & send/i }));
    expect(onApprove).toHaveBeenCalledOnce();

    rerender(
      <ApprovalCard snapshot={snapshot} submitting onApprove={onApprove} onReject={onReject} />,
    );
    expect(screen.getByRole("button", { name: /don't send/i })).toBeDisabled();
  });
});
