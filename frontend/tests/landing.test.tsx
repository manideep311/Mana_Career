import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Page from "@/app/page";

describe("landing", () => {
  it("shows the hero headline", () => {
    render(<Page />);
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /your next opportunity starts here/i,
      }),
    ).toBeInTheDocument();
  });

  it("links to get started", () => {
    render(<Page />);
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute(
      "href",
      "/register",
    );
  });
});
