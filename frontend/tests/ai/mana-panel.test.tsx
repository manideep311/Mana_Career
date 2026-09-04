import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ManaPanelDock } from "@/components/ai/ManaPanelDock";
import { renderWithProviders } from "@/test/utils";

function streamOf(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      for (const f of frames) controller.enqueue(enc.encode(f));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

const job = {
  id: "j1", title: "Staff Engineer", company: "Acme", location: "Remote",
  work_mode: "remote", seniority: null, employment_type: null,
  salary_min: null, salary_max: null, salary_currency: null, salary_period: null,
  is_seed: false, status: "ready", posted_at: null, created_at: "2026-09-01T00:00:00Z",
  required_skills: [],
};

describe("ManaPanelDock", () => {
  it("streams a reply with a text block and a job card from the suggested prompt", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: open\ndata: {"event":"open","run_id":"r1"}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"text","markdown":"Here are 1 role."}}\n\n`,
        `event: block\ndata: {"event":"block","block":{"kind":"job_card","job_id":"j1","match_id":null}}\n\n`,
        `event: done\ndata: {"event":"done","status":"completed","totals":{}}\n\n`,
      ]),
    );
    renderWithProviders(<ManaPanelDock />, {
      authValue: { authedStream },
      api: {
        ai: { createSession: vi.fn(async () => ({ id: "s1", messages: [] })) },
        jobs: { get: vi.fn(async () => job) },
        matches: { get: vi.fn() },
      },
    });

    await userEvent.click(screen.getByRole("button", { name: /mana ai/i }));
    await userEvent.click(screen.getByRole("button", { name: /find jobs that match my experience/i }));

    expect(await screen.findByText("Here are 1 role.")).toBeInTheDocument();
    expect(await screen.findByText("Staff Engineer")).toBeInTheDocument();
  });

  it("is collapsed by default", () => {
    renderWithProviders(<ManaPanelDock />);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mana ai/i })).toBeInTheDocument();
  });
});
