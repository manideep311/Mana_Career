import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { UseMatchResult } from "@/hooks/useMatch";
import type { JobMatch, MatchComponent, SkillGap } from "@/lib/api/types";
import { renderWithProviders } from "@/test/utils";

/**
 * `useMatch` is the panel's data source; mock it and swap what it returns per
 * test through a `vi.hoisted` holder (the factory below is hoisted above the
 * imports, so it can only close over hoisted state).
 */
const h = vi.hoisted(() => ({
  result: {
    match: null,
    isLoading: false,
    refetch: vi.fn(),
  } as UseMatchResult,
}));

vi.mock("@/hooks/useMatch", () => ({
  useMatch: () => h.result,
}));

import { WhyThisMatch } from "@/components/jobs/WhyThisMatch";

const readyMatch: JobMatch = {
  id: "m1",
  job_id: "j1",
  status: "ready",
  score: 82,
  band: "good",
  dimension_scores: { skill: 0.8, semantic: 0.55 },
  strengths: [{ dimension: "skill", raw_score: 0.8, contribution: 17 }],
  gaps: [],
  explanation: "Solid overlap on core skills.",
  computed_at: null,
};

const skillComponent: MatchComponent = {
  dimension: "skill",
  raw_score: 0.8,
  weight: 0.22,
  contribution: 17.6,
  detail: {},
  evidence: [],
};

const rustGap: SkillGap = {
  id: "g1",
  scope: "job",
  job_match_id: "m1",
  skill_slug: "rust",
  skill_label: "Rust",
  severity: "critical",
  frequency: 1,
  rationale: "Core to the role.",
  status: "open",
};

describe("WhyThisMatch", () => {
  it("renders the ready panel: band word, a dimension label, a skill gap, and the AI explanation", async () => {
    h.result = { match: readyMatch, isLoading: false, refetch: vi.fn() };

    renderWithProviders(<WhyThisMatch jobId="j1" />, {
      api: {
        matches: { components: vi.fn(async () => [skillComponent]) },
        skillGaps: { list: vi.fn(async () => [rustGap]) },
      },
    });

    expect(await screen.findByText(/good/i)).toBeInTheDocument();
    expect(await screen.findByText("Skill")).toBeInTheDocument();
    expect(await screen.findByText("Rust")).toBeInTheDocument();
    expect(
      await screen.findByText(/solid overlap on core skills/i),
    ).toBeInTheDocument();
  });

  it("offers a 'Score this job' button when there is no match yet", () => {
    h.result = { match: null, isLoading: false, refetch: vi.fn() };

    renderWithProviders(<WhyThisMatch jobId="j1" />);

    expect(
      screen.getByRole("button", { name: /score this job/i }),
    ).toBeInTheDocument();
  });
});
