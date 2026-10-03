import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import Page from "@/app/page";

vi.mock("next/font/google", () => ({
  Dancing_Script: () => ({ variable: "font-hand-script" }),
}));

const STATS = { career_paths: 11, roles: 41, skills: 198, learning_resources: 58 };

function renderLanding(stats: () => Promise<typeof STATS> = async () => STATS) {
  return renderWithProviders(<Page />, { api: { catalog: { stats: vi.fn(stats) } } });
}

describe("landing", () => {
  it("leads with the promise and one primary call to action", () => {
    renderLanding();
    expect(
      screen.getByRole("heading", { level: 1, name: /build the career you actually want/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start my career journey/i })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute("href", "/register");
    expect(screen.getAllByRole("button", { name: /watch how it works/i }).length).toBeGreaterThan(0);
  });

  it("shows the journey artwork once, as a decorative image", () => {
    renderLanding();
    const art = [...document.querySelectorAll("img")].filter((i) =>
      decodeURIComponent(i.getAttribute("src") ?? "").includes("hero-journey"),
    );
    expect(art).toHaveLength(1);
    expect(art[0]).toHaveAttribute("alt", "");
  });

  it("links only to sections that exist on the page", () => {
    renderLanding();
    const nav = screen.getByRole("navigation", { name: "Sections" });
    for (const link of within(nav).getAllByRole("link")) {
      const id = link.getAttribute("href")!.slice(1);
      expect(document.getElementById(id), `#${id}`).not.toBeNull();
    }
    expect(within(nav).queryByText(/pricing|reviews/i)).toBeNull();
  });

  it("shows live catalogue counts, never invented user numbers or ratings", async () => {
    renderLanding();
    expect(await screen.findByText("198")).toBeInTheDocument();
    expect(screen.getByText("Skills we can recognise in a résumé")).toBeInTheDocument();
    expect(screen.getByText("11")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d\s?%/);
    expect(text).not.toMatch(/\d(\.\d)?\s?\/\s?5/);
    expect(text).not.toMatch(/\d+\s?[kK]\+/);
    expect(text).not.toMatch(/trusted by/i);
    expect(text).toMatch(/Nothing is sent without your approval/);
  });

  it("keeps the promise visible when the counts can't load", async () => {
    renderLanding(async () => {
      throw new Error("offline");
    });
    expect(await screen.findByText("You decide")).toBeInTheDocument();
    expect(screen.queryByText("Skills we can recognise in a résumé")).toBeNull();
  });
});
