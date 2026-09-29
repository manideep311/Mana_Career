import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import { ResumeAnalysisPanel } from "@/components/resume/ResumeAnalysisPanel";
import type { ResumeAnalysis } from "@/lib/api/types";

const ANALYSIS: ResumeAnalysis = {
  resume_id: "r1",
  enough_text: true,
  sections: { experience: true, skills: true },
  word_count: 420,
  page_count: 1,
  bullet_count: 8,
  bullets_with_results: 2,
  strengths: ["2 of your bullet points show a measurable result."],
  issues: [
    {
      id: "weak_openings", severity: "medium", area: "bullets",
      problem: "3 bullet points start with a weak phrase.",
      why_it_matters: "Reviewers skim the first words of each line.",
      suggestion: "Lead with what you did: Built, Cut, Led.",
      examples: ["Responsible for code reviews"],
    },
    {
      id: "few_results", severity: "high", area: "impact",
      problem: "Most bullet points don't show a result.",
      why_it_matters: "Results are what separate you from other candidates.",
      suggestion: "Add the outcome you know: time saved, errors cut, users served.",
      examples: [],
    },
  ],
  skills: [
    { slug: "python", label: "Python", category: "language", applied: true, lines: ["Built Python services"] },
    { slug: "docker", label: "Docker", category: "devops", applied: false, lines: [] },
  ],
  alignment: { target: "Backend Engineer", evidenced: ["Python"], missing: ["Kubernetes"] },
  target_path: { slug: "backend-engineer", title: "Backend Engineer" },
};

describe("ResumeAnalysisPanel", () => {
  it("frames each issue as problem, why it matters and a suggestion, most important first", async () => {
    renderWithProviders(<ResumeAnalysisPanel resumeId="r1" />, {
      api: { resumes: { analysis: vi.fn(async () => ANALYSIS) } },
    });
    const region = await screen.findByRole("region", { name: "How your résumé reads" });
    const items = await within(region).findAllByRole("listitem");
    const issues = items.filter((li) => li.textContent?.includes("Why it matters"));
    expect(issues[0]).toHaveTextContent("Most bullet points don't show a result.");
    expect(issues[0]).toHaveTextContent("Fix first");
    expect(issues[1]).toHaveTextContent("Suggestion");
    expect(within(issues[1]).getByText("Responsible for code reviews")).toBeInTheDocument();
  });

  it("separates skills shown in work from skills only listed, and names the target", async () => {
    renderWithProviders(<ResumeAnalysisPanel resumeId="r1" />, {
      api: { resumes: { analysis: vi.fn(async () => ANALYSIS) } },
    });
    expect((await screen.findByText(/Shown in your work:/)).parentElement).toHaveTextContent("Python");
    expect(screen.getByText(/Only listed, not shown in use:/).parentElement).toHaveTextContent("Docker");
    expect(screen.getByRole("link", { name: "Backend Engineer" })).toHaveAttribute("href", "/career/backend-engineer");
    expect(screen.getByText(/8 bullet points · 2 with a measurable result · 1 page/)).toBeInTheDocument();
  });
});
