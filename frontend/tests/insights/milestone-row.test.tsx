import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MilestoneRow } from "@/components/insights/MilestoneRow";
import type { Milestone } from "@/lib/api/types";

const base: Milestone = {
  id: "m1",
  order_index: 0,
  skill_slug: "sql",
  skill_label: "SQL",
  title: "Window functions and CTEs",
  why_it_matters: "Analytics roles lean on these for reporting queries.",
  resource_ids: ["r1", "r2"],
  est_hours: 6,
  practice_project: "Rebuild a churn dashboard from raw event tables.",
  checkpoint: "Explain a running total query out loud.",
  status: "in_progress",
  completed_at: null,
};

describe("MilestoneRow", () => {
  it("renders the title, why-it-matters, and the practice project", () => {
    render(<MilestoneRow milestone={base} onStatusChange={vi.fn()} />);
    expect(screen.getByText("Window functions and CTEs")).toBeInTheDocument();
    expect(
      screen.getByText("Analytics roles lean on these for reporting queries."),
    ).toBeInTheDocument();
    expect(screen.getByText("Build:")).toBeInTheDocument();
    expect(
      screen.getByText(/Rebuild a churn dashboard/),
    ).toBeInTheDocument();
  });

  it("shows the select at the milestone's current status", () => {
    render(<MilestoneRow milestone={base} onStatusChange={vi.fn()} />);
    const select = screen.getByRole("combobox", { name: "Milestone status" });
    expect(select).toHaveValue("in_progress");
  });

  it("reports the picked status", async () => {
    const onStatusChange = vi.fn();
    render(<MilestoneRow milestone={base} onStatusChange={onStatusChange} />);
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Milestone status" }),
      "done",
    );
    expect(onStatusChange).toHaveBeenCalledWith("done");
  });

  it("disables the select while busy", () => {
    render(
      <MilestoneRow milestone={base} onStatusChange={vi.fn()} busy />,
    );
    expect(
      screen.getByRole("combobox", { name: "Milestone status" }),
    ).toBeDisabled();
  });
});
