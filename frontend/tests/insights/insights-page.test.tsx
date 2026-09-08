// Import the shared helper first for its side-effect `vi.mock("next/navigation")`
// (RULING R11: the page pulls the router in through `RequireAuth`, so the mock
// must register before `@/app/(app)/insights/page` is evaluated).
import { renderWithProviders } from "@/test/utils";

import InsightsPage from "@/app/(app)/insights/page";

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Insights, SkillGap } from "@/lib/api/types";

function gap(over: Partial<SkillGap> = {}): SkillGap {
  return {
    id: "g1",
    scope: "aggregate",
    job_match_id: null,
    skill_slug: "kubernetes",
    skill_label: "Kubernetes",
    severity: "critical",
    frequency: 3,
    rationale: "Shows up in 3 of your saved roles",
    status: "open",
    ...over,
  };
}

function insightsPayload(over: Partial<Insights> = {}): Insights {
  return {
    strengths: [{ skill_slug: "go", skill_label: "Go", detail: "Strong across 2" }],
    skills_to_develop: [
      gap(),
      gap({
        id: "g2",
        skill_slug: "graphql",
        skill_label: "GraphQL",
        severity: "important",
        frequency: 2,
        rationale: null,
      }),
    ],
    recommended_next_step: {
      kind: "add_job",
      title: "Add a job",
      reason: "Track a few roles",
      entity_type: null,
      entity_id: null,
    },
    trending_skills: [{ skill_slug: "rust", skill_label: "Rust", detail: "in 3 roles" }],
    suggested_projects: ["Build a CLI"],
    roadmap_summary: null,
    ...over,
  };
}

function api(over: Record<string, unknown> = {}) {
  return {
    insights: { get: vi.fn().mockResolvedValue(insightsPayload()) },
    skillGaps: { aggregate: vi.fn().mockResolvedValue([]) },
    roadmaps: {
      get: vi.fn().mockResolvedValue({
        id: "",
        scope: "aggregate",
        job_id: null,
        title: "",
        summary: null,
        next_step: null,
        status: "active",
        created_at: "",
        updated_at: "",
        milestones: [],
      }),
      create: vi.fn().mockResolvedValue({ id: "r1" }),
    },
    ...over,
  };
}

// `RoadmapTimeline` mounts `live` after "Build my roadmap", so `useRoadmapEvents`
// opens a stream — hand it a clean, immediately-closed one.
const authValue = {
  authedStream: vi.fn(
    async () =>
      new Response(
        new ReadableStream({
          start(c) {
            c.close();
          },
        }),
        { status: 200 },
      ),
  ),
};

describe("InsightsPage", () => {
  it("renders every section from one insights payload", async () => {
    renderWithProviders(<InsightsPage />, { api: api() as never, authValue });

    expect(await screen.findByText("Add a job")).toBeInTheDocument();
    expect(screen.getByText("Go")).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
    expect(screen.getByText("Rust")).toBeInTheDocument();
    expect(screen.getByText("Build a CLI")).toBeInTheDocument();
  });

  it("starts a roadmap build from the empty state", async () => {
    const client = api();
    renderWithProviders(<InsightsPage />, { api: client as never, authValue });

    const build = await screen.findByRole("button", { name: /build my roadmap/i });
    await userEvent.click(build);

    await waitFor(() => {
      expect(client.roadmaps.create).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(client.roadmaps.get).toHaveBeenCalledWith("r1");
    });
  });

  it("re-runs the skill-gap roll-up from the Refresh button", async () => {
    const client = api();
    renderWithProviders(<InsightsPage />, { api: client as never, authValue });

    const refresh = await screen.findByRole("button", { name: /refresh/i });
    await userEvent.click(refresh);

    await waitFor(() => {
      expect(client.skillGaps.aggregate).toHaveBeenCalled();
    });
  });
});
