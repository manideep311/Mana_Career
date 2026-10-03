import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/common/EmptyState";
import { PAGE_ART } from "@/lib/page-art";

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

  it("shows its scene as decoration, leaving the title to carry the meaning", () => {
    const { container } = render(
      <EmptyState art={PAGE_ART.emptyJobs} title="No jobs match" />,
    );
    const img = container.querySelector("img");
    expect(img).toHaveAttribute("alt", "");
    expect(screen.queryByRole("img")).toBeNull(); // empty alt keeps it out of the a11y tree
    expect(screen.getByRole("status")).toHaveTextContent("No jobs match");
  });
});
