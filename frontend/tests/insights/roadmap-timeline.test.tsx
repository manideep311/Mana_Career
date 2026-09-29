// Import the shared helper first for its side-effect `vi.mock("next/navigation")`
// (RULING R11: `useParams` is mocked to `{}`; `RoadmapTimeline` takes
// `recommendationId` as a prop, so the tests pass `""` and the mock
// `api.roadmaps.get` ignores its argument).
import { renderWithProviders } from "@/test/utils";

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RoadmapTimeline } from "@/components/insights/RoadmapTimeline";
import type { Milestone, RoadmapDetail } from "@/lib/api/types";

function milestone(over: Partial<Milestone> = {}): Milestone {
  return {
    id: "m1",
    order_index: 0,
    skill_slug: "sql",
    skill_label: "SQL",
    title: "Window functions",
    why_it_matters: "Reporting queries lean on these.",
    resource_ids: [],
    est_hours: null,
    practice_project: null,
    checkpoint: null,
    status: "not_started",
    completed_at: null,
    ...over,
  };
}

function detail(over: Partial<RoadmapDetail> = {}): RoadmapDetail {
  return {
    id: "r1",
    scope: "profile",
    job_id: null,
    title: "Close your top skill gaps",
    summary: null,
    next_step: null,
    status: "active",
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    milestones: [],
    hours_per_week: 5,
    ...over,
  };
}

function api(over: Record<string, unknown> = {}) {
  return {
    roadmaps: {
      get: vi.fn().mockResolvedValue(detail()),
      create: vi.fn().mockResolvedValue({ id: "r1" }),
      patchMilestone: vi.fn().mockResolvedValue(milestone({ status: "done" })),
      ...over,
    },
  };
}

// `useRoadmapEvents` stays idle here (status "active", no `live` → `streaming`
// is false), but hand it a clean finite stream in case it ever fires.
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

describe("RoadmapTimeline", () => {
  it("renders a MilestoneRow per milestone and patches on a status change", async () => {
    const client = api({
      get: vi.fn().mockResolvedValue(
        detail({
          milestones: [
            milestone({ id: "m1", title: "Window functions", status: "not_started" }),
            milestone({
              id: "m2",
              order_index: 1,
              title: "Query planning",
              status: "in_progress",
            }),
          ],
        }),
      ),
    });

    renderWithProviders(<RoadmapTimeline recommendationId="" />, {
      api: client as never,
      authValue,
    });

    expect(await screen.findByText("Window functions")).toBeInTheDocument();
    expect(screen.getByText("Query planning")).toBeInTheDocument();

    const selects = screen.getAllByRole("combobox", { name: "Milestone status" });
    await userEvent.selectOptions(selects[0], "done");

    await waitFor(() => {
      expect(client.roadmaps.patchMilestone).toHaveBeenCalledWith("", "m1", "done");
    });
  });

  it("shows the no-milestones copy for a roadmap with none", async () => {
    renderWithProviders(<RoadmapTimeline recommendationId="" />, {
      api: api({ get: vi.fn().mockResolvedValue(detail({ milestones: [] })) }) as never,
      authValue,
    });

    expect(await screen.findByText(/No milestones yet/)).toBeInTheDocument();
  });
});

describe("RoadmapTimeline phases", () => {
  it("groups milestones into now, the next 30 days and 30 to 90 days, then the target", async () => {
    const roadmap = detail({
      title: "Roadmap for Data Analyst",
      milestones: [
        milestone({ id: "a", title: "Window functions", phase: "current" }),
        milestone({ id: "b", order_index: 1, title: "Dashboards", phase: "next_30" }),
        milestone({ id: "c", order_index: 2, title: "Python basics", phase: "next_60_90" }),
      ],
    });
    renderWithProviders(<RoadmapTimeline recommendationId="" />, {
      api: api({ get: vi.fn().mockResolvedValue(roadmap) }),
    });
    const now = await screen.findByRole("region", { name: "Now" });
    expect(now).toHaveTextContent("Window functions");
    expect(screen.getByRole("region", { name: "Next 30 days" })).toHaveTextContent("Dashboards");
    expect(screen.getByRole("region", { name: "Days 30 to 90" })).toHaveTextContent("Python basics");
    expect(screen.getByText("Target").parentElement).toHaveTextContent("Data Analyst");
    expect(screen.getByText(/about 5 hours a week/)).toBeInTheDocument();
  });
});
