import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResumeStepper } from "@/components/resume/ResumeStepper";

describe("ResumeStepper", () => {
  it("announces the real stage while parsing, with the rocket beside it", () => {
    render(<ResumeStepper status="parsing" message="Reading your résumé…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Reading your résumé…");
    expect(screen.getByTestId("paper-rocket")).toHaveAttribute("aria-hidden", "true");
    // The server message duplicates the stage label, so it isn't repeated.
    expect(screen.getAllByText(/Reading your résumé/)).toHaveLength(2);
  });

  it("moves to mapping once the text is read and shows extra server detail", () => {
    render(<ResumeStepper status="extracting" message="Almost there" />);
    expect(screen.getByRole("status")).toHaveTextContent("Mapping your experience…");
    expect(screen.getByRole("status")).toHaveTextContent("Almost there");
    expect(screen.getByText(/Mapping your experience/, { selector: "li" })).toHaveAttribute(
      "aria-current",
      "step",
    );
  });

  it("marks all steps complete at extracted and never shows a percentage", () => {
    const { container } = render(<ResumeStepper status="extracted" message={null} />);
    expect(container.querySelectorAll('[data-testid="step-done"]')).toHaveLength(3);
    expect(container.textContent).not.toMatch(/%/);
  });
});
