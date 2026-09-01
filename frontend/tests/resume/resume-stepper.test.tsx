import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResumeStepper } from "@/components/resume/ResumeStepper";

describe("ResumeStepper", () => {
  it("marks step 1 active while parsing and shows the message", () => {
    render(<ResumeStepper status="parsing" message="Reading your résumé…" />);
    expect(screen.getByText("Reading your résumé…")).toBeInTheDocument();
    expect(screen.getByText("Understanding the details")).toBeInTheDocument();
  });

  it("marks all steps complete at extracted", () => {
    const { container } = render(
      <ResumeStepper status="extracted" message={null} />,
    );
    expect(container.querySelectorAll('[data-testid="step-done"]')).toHaveLength(
      3,
    );
  });
});
