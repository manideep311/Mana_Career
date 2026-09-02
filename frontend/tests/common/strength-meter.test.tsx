import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StrengthMeter } from "@/components/common/StrengthMeter";

describe("StrengthMeter", () => {
  it("exposes the score to assistive tech and lists gaps", () => {
    render(<StrengthMeter score={38} missing={["Add your work experience"]} />);
    const bar = screen.getByRole("progressbar", { name: /profile strength/i });
    expect(bar).toHaveAttribute("aria-valuenow", "38");
    expect(screen.getByText(/Add your work experience/)).toBeInTheDocument();
  });
  it("celebrates a complete profile", () => {
    render(<StrengthMeter score={100} missing={[]} />);
    expect(screen.getByText(/complete/i)).toBeInTheDocument();
  });
  it("renders a per-dimension breakdown when dimensions are given", () => {
    render(
      <StrengthMeter
        score={22}
        missing={["x"]}
        dimensions={[
          { key: "experience", label: "Work experience", earned: 16, max: 16, hint: "h", met: true },
          { key: "skills_mapped", label: "Skills mapped", earned: 0, max: 8, hint: "Upload a résumé", met: false },
        ]}
      />,
    );
    expect(screen.getByText("Work experience")).toBeInTheDocument();
    expect(screen.getByText("Skills mapped")).toBeInTheDocument();
    expect(screen.getByText(/upload a résumé/i)).toBeInTheDocument();
  });
});
