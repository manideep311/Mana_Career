import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import CareerPathPage from "@/app/(app)/career/[slug]/page";
import CareerPathsPage from "@/app/(app)/career/page";
import { ProblemError } from "@/lib/api/fetcher";
import type { CareerPath, SkillPlan } from "@/lib/api/types";

const PATH: CareerPath = {
  slug: "data-analyst",
  title: "Data Analyst",
  summary: "Turn data into reports, dashboards and recommendations people act on.",
  job_count: 4,
  stated_target: true,
  fit: "close",
  fit_label: "Close fit",
  fit_explanation: "You already cover most of what these roles ask for.",
  why: "You already have 3 of the 5 skills Data Analyst roles ask for most, including SQL, Excel and Tableau.",
  have: [
    { slug: "sql", label: "SQL", demand: 1, required: true, have: true, evidence: ["Wrote SQL reports for finance"] },
    { slug: "excel", label: "Excel", demand: 0.5, required: false, have: true, evidence: [] },
  ],
  missing: [{ slug: "python", label: "Python", demand: 0.75, required: true, have: false, evidence: [] }],
  relevant_experience: ["Reporting Analyst"],
  seniority_note: null,
  next_actions: [
    { kind: "apply", title: "Apply to the Data Analyst roles that match you best", detail: "Tailor your résumé to each one." },
  ],
  related: [{ slug: "data-scientist", title: "Data Scientist" }],
  roles: [{ id: "j1", title: "Data Analyst", company: "Acme" }],
  evidence_is_thin: false,
};

const PLAN: SkillPlan = {
  path_slug: "data-analyst",
  path_title: "Data Analyst",
  steps: [
    {
      slug: "python", label: "Python", category: "language",
      why_it_matters: "Python appears in 3 of the 4 Data Analyst roles we looked at.",
      requirement: "Usually a requirement.",
      current_evidence: "You already use SQL, a related skill, so this builds on what you know.",
      resource: { id: "r1", title: "Python for Everybody", provider: "UMich", url: "https://example.com/py", type: "course", level: "beginner", est_hours: 30, cost: "free" },
      practice_project: "Rewrite a small tool you already rely on in Python.",
      roadmap_position: 2,
    },
  ],
};

describe("/career", () => {
  it("lists paths as suggestions with the evidence count, not a probability", async () => {
    renderWithProviders(<CareerPathsPage />, {
      api: { career: { paths: vi.fn(async () => ({ paths: [PATH], notes: ["We know only a few of your skills."] })) } },
    });
    const link = await screen.findByRole("link", { name: /Data Analyst/ });
    expect(link).toHaveAttribute("href", "/career/data-analyst");
    expect(within(link).getByText("Close fit")).toBeInTheDocument();
    expect(within(link).getByText(/2 of 3 core skills · 4 roles looked at/)).toBeInTheDocument();
    expect(screen.getByText(/appear relevant/)).toBeInTheDocument();
    expect(screen.getByText("We know only a few of your skills.")).toBeInTheDocument();
  });

  it("says what to do when there is nothing to suggest", async () => {
    renderWithProviders(<CareerPathsPage />, {
      api: { career: { paths: vi.fn(async () => ({ paths: [], notes: [] })) } },
    });
    expect(await screen.findByText("No paths to suggest yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /upload your résumé/i })).toHaveAttribute("href", "/resume");
  });
});

describe("/career/[slug]", () => {
  function renderPath(path = vi.fn(async () => PATH)) {
    return renderWithProviders(<CareerPathPage />, {
      api: { career: { path, skills: vi.fn(async () => PLAN) } },
    });
  }

  it("explains why, what you have (with evidence), what's missing and the difficulty", async () => {
    renderPath();
    expect(await screen.findByRole("heading", { level: 1, name: "Data Analyst" })).toBeInTheDocument();
    expect(screen.getByText(/including SQL, Excel and Tableau/)).toBeInTheDocument();
    expect(screen.getByText("Wrote SQL reports for finance")).toBeInTheDocument();
    expect(screen.getByText(/no résumé line shows it in use yet/)).toBeInTheDocument();
    const missing = screen.getByRole("region", { name: "What's missing" });
    expect(within(missing).getByText("Python")).toBeInTheDocument();
    expect(within(missing).getByText(/usually required/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "How big a move this is" })).toHaveTextContent(
      "Close fit. You already cover most",
    );
  });

  it("shows the skill plan with a project, a resource and its roadmap position", async () => {
    renderPath();
    const skills = await screen.findByRole("region", { name: "Skills to build first" });
    expect(await within(skills).findByText("Rewrite a small tool you already rely on in Python.")).toBeInTheDocument();
    expect(within(skills).getByRole("link", { name: /Python for Everybody/ })).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(skills).getByText("Step 2 on your roadmap")).toBeInTheDocument();
  });

  it("links the apply action to the roles behind the path and offers alternatives", async () => {
    renderPath();
    expect(await screen.findByRole("link", { name: /Apply to the Data Analyst roles/ })).toHaveAttribute("href", "#roles");
    const roles = screen.getByRole("region", { name: "Roles behind this path" });
    expect(within(roles).getByRole("link", { name: "Data Analyst" })).toHaveAttribute("href", "/jobs/j1");
    expect(screen.getByRole("link", { name: "Data Scientist" })).toHaveAttribute("href", "/career/data-scientist");
  });

  it("handles an unknown path with a way back", async () => {
    renderPath(vi.fn(async () => { throw new ProblemError("career.path_not_found", 404, null); }));
    expect(await screen.findByText("We couldn't find that path")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See your paths" })).toHaveAttribute("href", "/career");
  });
});
