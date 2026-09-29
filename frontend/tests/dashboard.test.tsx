import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DashboardPage from "@/app/(app)/dashboard/page";
import type { CareerOverview, CareerPath } from "@/lib/api/types";
import { renderWithProviders } from "@/test/utils";

const JOURNEY: CareerOverview["journey"] = [
  { key: "profile", label: "Your profile", status: "done", detail: "Résumé read and skills mapped" },
  { key: "skills", label: "Skills", status: "current", detail: "4 of 10 core skills for Backend Engineer" },
  { key: "proof", label: "Proof of work", status: "upcoming", detail: "1 project on your profile" },
  { key: "applications", label: "Applications", status: "upcoming", detail: "None sent yet" },
  { key: "target", label: "Target role", status: "upcoming", detail: "A Backend Engineer role" },
];

const PATH: CareerPath = {
  slug: "backend-engineer",
  title: "Backend Engineer",
  summary: "Build the APIs, services and data models products run on.",
  job_count: 6,
  stated_target: false,
  fit: "stretch",
  fit_label: "Reachable stretch",
  fit_explanation: "A few focused skills stand between you and these roles.",
  why: "You already have 4 of the 10 skills Backend Engineer roles ask for most.",
  have: [],
  missing: [],
  relevant_experience: [],
  seniority_note: null,
  next_actions: [],
  related: [],
  roles: [],
  evidence_is_thin: false,
};

function overview(partial: Partial<CareerOverview> = {}): CareerOverview {
  return {
    direction: PATH,
    direction_summary: "Based on your experience, Backend Engineer roles look like a relevant path.",
    next_actions: [
      { kind: "project", title: "Build a small project that uses Kubernetes", detail: "It appears in 5 of 6 roles.", href: "/career/backend-engineer" },
      { kind: "roadmap", title: "Turn the Backend Engineer gaps into a roadmap", detail: "A short, ordered plan.", href: "/insights#roadmap" },
    ],
    journey: JOURNEY,
    roadmap: null,
    opportunities: [
      { job_id: "j1", title: "Backend Engineer", company: "Acme", band: "strong", reason: "Strong skill overlap", gap: "Missing: Kubernetes" },
    ],
    skills: [
      {
        slug: "kubernetes", label: "Kubernetes", category: "devops",
        why_it_matters: "Kubernetes appears in 5 of the 6 Backend Engineer roles we looked at.",
        requirement: "Usually a requirement.", current_evidence: "You already use Docker.",
        resource: null, practice_project: "Deploy one of your projects.", roadmap_position: null,
      },
    ],
    notes: ["You haven't set a target role, so directions are inferred from your skills."],
    has_resume: true,
    ...partial,
  };
}

function renderDashboard(data: CareerOverview) {
  return renderWithProviders(<DashboardPage />, {
    authValue: { user: { full_name: "Ada Lovelace" } },
    api: { career: { overview: vi.fn(async () => data) } },
  });
}

describe("DashboardPage", () => {
  it("leads with the greeting, then the direction in words, not a percentage", async () => {
    renderDashboard(overview());
    expect(screen.getByRole("heading", { level: 1, name: /Good .*, Ada/ })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Backend Engineer", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("Reachable stretch")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /why this path/i })).toHaveAttribute(
      "href",
      "/career/backend-engineer",
    );
    expect(document.body.textContent).not.toMatch(/\d+\s?%/);
  });

  it("orders sections as direction, next actions, journey, roadmap, roles, skills", async () => {
    renderDashboard(overview());
    await screen.findByText("What to do next");
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Backend Engineer",
      "What to do next",
      "Your journey",
      "Your roadmap",
      "Roles that fit",
      "Skills to build",
    ]);
  });

  it("links each next action to where it gets done and marks the current journey stop", async () => {
    renderDashboard(overview());
    const next = await screen.findByRole("region", { name: "What to do next" });
    const links = within(next).getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/career/backend-engineer");
    const journey = screen.getByRole("list", { name: "Your journey" });
    expect(within(journey).getByText(/Skills/).closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("explains roles by reason and band instead of a score", async () => {
    renderDashboard(overview());
    const roles = await screen.findByRole("region", { name: "Roles that fit" });
    expect(within(roles).getByText("Strong match")).toBeInTheDocument();
    expect(within(roles).getByText(/Strong skill overlap · Missing: Kubernetes/)).toBeInTheDocument();
  });

  it("tells a new user what to do now when there is nothing to show yet", async () => {
    renderDashboard(
      overview({
        direction: null,
        direction_summary: "Upload your résumé and we'll map the roles your experience points to.",
        has_resume: false,
        next_actions: [{ kind: "upload_resume", title: "Upload your résumé", detail: "It's the quickest way.", href: "/resume" }],
        opportunities: [],
        skills: [],
        notes: [],
      }),
    );
    expect(await screen.findByText(/Upload your résumé and we'll map/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /upload your résumé/i })[0]).toHaveAttribute("href", "/resume");
    expect(screen.getByText(/No close matches scored yet/)).toBeInTheDocument();
    expect(screen.queryByText("Skills to build")).toBeNull();
  });

  it("offers a retry when the overview can't load", async () => {
    renderWithProviders(<DashboardPage />, {
      authValue: { user: { full_name: "Ada Lovelace" } },
      api: { career: { overview: vi.fn(async () => { throw new Error("down"); }) } },
    });
    expect(await screen.findByRole("button", { name: /try again/i }, { timeout: 4000 })).toBeInTheDocument();
  });
});
