import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ActivityPage from "@/app/(app)/activity/page";
import { renderWithProviders } from "@/test/utils";

const actions = [
  {
    id: "a1", ai_session_id: "s1", run_id: "r1", node: "job_retrieval",
    action_key: "searched_corpus", summary: "Searched your job corpus — 3 roles",
    status: "ok", entity_type: null, entity_id: null, occurred_at: "2026-09-04T10:00:00Z",
  },
  {
    id: "a2", ai_session_id: "s1", run_id: "r1", node: "respond",
    action_key: "responded", summary: "Answered with 2 block(s)",
    status: "warning", entity_type: null, entity_id: null, occurred_at: "2026-09-04T10:00:05Z",
  },
];

describe("ActivityPage", () => {
  it("lists actions with status pills", async () => {
    renderWithProviders(<ActivityPage />, {
      api: { ai: { listActions: vi.fn(async () => ({ items: actions, total: 2 })), startGoal: vi.fn() } },
    });
    expect(await screen.findByText(/Searched your job corpus/)).toBeInTheDocument();
    expect(screen.getByText(/Answered with 2 block/)).toBeInTheDocument();
  });

  it("re-runs the session goal from a warning row", async () => {
    const startGoal = vi.fn(async () => ({ run_id: "r2" }));
    renderWithProviders(<ActivityPage />, {
      api: { ai: { listActions: vi.fn(async () => ({ items: actions, total: 2 })), startGoal } },
    });
    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));
    expect(startGoal).toHaveBeenCalledWith("s1", { goal: "understand_job", inputs: {} });
  });
});
