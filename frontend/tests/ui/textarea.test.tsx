import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import { Textarea } from "@/components/ui/textarea";

describe("Textarea", () => {
  it("forwards ref and native props", () => {
    const ref = createRef<HTMLTextAreaElement>();
    render(<Textarea ref={ref} aria-invalid placeholder="Summary" defaultValue="hi" />);
    const el = screen.getByPlaceholderText("Summary");
    expect(ref.current).toBe(el);
    expect(el).toHaveAttribute("aria-invalid", "true");
    expect(el).toHaveValue("hi");
  });

  it("merges className", () => {
    render(<Textarea className="custom-x" data-testid="t" />);
    expect(screen.getByTestId("t").className).toContain("custom-x");
  });
});
