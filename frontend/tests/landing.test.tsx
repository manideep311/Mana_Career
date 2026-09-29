import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Page from "@/app/page";

describe("landing", () => {
  it("leads with the promise, not the tech", () => {
    render(<Page />);
    expect(
      screen.getByRole("heading", { level: 1, name: /build the career you actually want/i }),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bAI\b/);
  });

  it("has one primary call to action and a way to learn more first", () => {
    render(<Page />);
    expect(screen.getByRole("link", { name: /build my career path/i })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(screen.getByRole("link", { name: /explore how it works/i })).toHaveAttribute(
      "href",
      "#how-it-works",
    );
    expect(document.getElementById("how-it-works")).not.toBeNull();
  });

  it("makes no invented claims: no stats, percentages or user counts", () => {
    render(<Page />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d\s?%/);
    expect(text).not.toMatch(/\d[\d,.]*\s?(k|\+)?\s+(users|people|hires|placements|jobs landed)/i);
    expect(text).toMatch(/Nothing is sent without your approval/);
  });
});
