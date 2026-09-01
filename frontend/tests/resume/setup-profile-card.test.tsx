import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SetupProfileCard } from "@/components/resume/SetupProfileCard";

describe("SetupProfileCard", () => {
  it("links to /resume", () => {
    render(<SetupProfileCard />);
    expect(
      screen.getByRole("link", { name: /upload your résumé/i }),
    ).toHaveAttribute("href", "/resume");
  });

  it("is headed with the setup prompt", () => {
    render(<SetupProfileCard />);
    expect(
      screen.getByText(/finish setting up your profile/i),
    ).toBeInTheDocument();
  });
});
