import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import EvalPage from "@/app/(app)/eval/page";
import { renderWithProviders } from "@/test/utils";

const run = {
  id: "r1", suite: "retrieval", dataset_version: "v1", git_sha: "abc1234567",
  provider: "fake", model_ids: {}, status: "passed",
  metrics: { recall_at_10: 0.82, mrr: 0.61, ndcg_at_10: 0.7 },
  started_at: "2026-09-02T10:00:00Z", ended_at: "2026-09-02T10:00:03Z",
};

describe("EvalPage", () => {
  it("renders the runs table with metrics and a run button", async () => {
    renderWithProviders(<EvalPage />, {
      api: { eval: { listRuns: vi.fn(async () => ({ items: [run], total: 1 })) } },
    });
    expect(await screen.findByText("0.820")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run retrieval suite/i })).toBeInTheDocument();
  });
});
