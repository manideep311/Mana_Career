import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/common/EmptyState";

describe("EmptyState", () => {
  it("renders title and description with a status role", () => {
    render(
      <EmptyState
        title="Your career workspace is ready."
        description="Add a résumé to begin."
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Your career workspace is ready.",
    );
    expect(screen.getByText("Add a résumé to begin.")).toBeInTheDocument();
  });
});
