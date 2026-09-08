// Import the shared helper first for its side-effect `vi.mock("next/navigation")`
// so `next/link` renders without a real App Router in the tree.
import "@/test/utils";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NextStepCard } from "@/components/insights/NextStepCard";
import type { NextStep } from "@/lib/api/types";

const base: NextStep = {
  kind: "open_application",
  title: "Follow up on your Nimbus application",
  reason: "It has sat in applied for nine days.",
  entity_type: "application",
  entity_id: "a1",
};

describe("NextStepCard", () => {
  it("renders the step title and reason", () => {
    render(<NextStepCard step={base} />);
    expect(
      screen.getByText("Follow up on your Nimbus application"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("It has sat in applied for nine days."),
    ).toBeInTheDocument();
  });

  it("links to the application when entity_type is application", () => {
    render(<NextStepCard step={base} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/applications/a1");
  });

  it("shows no link for a step with no entity", () => {
    render(
      <NextStepCard
        step={{ ...base, kind: "add_job", entity_type: null, entity_id: null }}
      />,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows the caught-up copy when step is null", () => {
    render(<NextStepCard step={null} />);
    expect(screen.getByText("You're all caught up.")).toBeInTheDocument();
  });
});
