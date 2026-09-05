import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VersionDiff } from "@/components/resume/VersionDiff";
import type { ResumeDiff } from "@/lib/api/types";

describe("VersionDiff", () => {
  it("shows a no-changes message for an empty diff", () => {
    render(<VersionDiff diff={{ deltas: [] }} claimValidation={{}} />);
    expect(screen.getByText("No changes from the base résumé.")).toBeInTheDocument();
  });

  it("groups deltas by section and labels the op", () => {
    const diff: ResumeDiff = {
      deltas: [
        { path: "summary", op: "changed", before: "Old summary.", after: "New summary." },
        {
          path: "experiences[0].highlights",
          op: "added",
          before: null,
          after: ["Shipped the tailoring feature"],
        },
      ],
    };
    render(<VersionDiff diff={diff} claimValidation={{}} />);
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Experience")).toBeInTheDocument();
    expect(screen.getByText("Changed")).toBeInTheDocument();
    expect(screen.getByText("Added")).toBeInTheDocument();
    expect(screen.getByText("Old summary.")).toBeInTheDocument();
    expect(screen.getByText("New summary.")).toBeInTheDocument();
    expect(screen.getByText("Shipped the tailoring feature")).toBeInTheDocument();
  });

  it("shows a passed claim-validation banner", () => {
    render(
      <VersionDiff
        diff={{ deltas: [] }}
        claimValidation={{ checked: 4, unsupported: [], supported_ratio: 1, passed: true }}
      />,
    );
    expect(screen.getByText("All 4 claims are grounded in your résumé.")).toBeInTheDocument();
  });

  it("lists unsupported claims when validation failed", () => {
    render(
      <VersionDiff
        diff={{ deltas: [] }}
        claimValidation={{
          checked: 4,
          unsupported: ["Led a team of 12 engineers"],
          supported_ratio: 0.75,
          passed: false,
        }}
      />,
    );
    expect(screen.getByText(/1 of 4 claims couldn.t be grounded/)).toBeInTheDocument();
    expect(screen.getByText("Led a team of 12 engineers")).toBeInTheDocument();
  });

  it("renders nothing claim-related when claim_validation is empty", () => {
    render(<VersionDiff diff={{ deltas: [] }} claimValidation={{}} />);
    expect(screen.queryByText(/claims/)).not.toBeInTheDocument();
  });
});
