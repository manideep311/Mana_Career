import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PrepareApplicationBuilder } from "@/components/applications/PrepareApplicationBuilder";
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

const snapshot = {
  job: { title: "Staff Engineer", company: "Acme" },
  resume_version_id: "v1",
  cover_letter: { id: "cl1", content: "Dear Hiring Team," },
  email: { id: "em1", to_email: "jobs@acme.com", to_name: null, subject: "Application", body: "Hi." },
};

describe("PrepareApplicationBuilder", () => {
  it("start → stream → approval card → approve → sent", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: step\ndata: {"event":"step","node":"cover_letter","status":"ok","summary":"wrote letter"}\n\n`,
        `event: approval\ndata: {"event":"approval","approval_id":"ap-1"}\n\n`,
        `event: done\ndata: {"event":"done","status":"awaiting_approval","totals":{}}\n\n`,
      ]),
    );
    let appStatus = "awaiting_approval";
    renderWithProviders(<PrepareApplicationBuilder jobId="j1" />, {
      authValue: { authedStream },
      api: {
        applications: {
          create: vi.fn(async () => ({ run_id: "r1", session_id: "s1" })),
          get: vi.fn(async () => ({
            id: "a1", job_id: "j1", status: appStatus, applied_at:
              appStatus === "applied" ? "2026-09-06T10:42:00Z" : null,
          })),
        },
        approvals: {
          get: vi.fn(async () => ({
            id: "ap-1", application_id: "a1", action_type: "send_application_email",
            payload_snapshot: snapshot, status: "pending", decided_at: null,
            decision_note: null, created_at: "2026-09-06T10:00:00Z",
          })),
          decide: vi.fn(async () => {
            appStatus = "applied";
          }),
        },
      },
    });

    await userEvent.click(await screen.findByRole("button", { name: /prepare application/i }));
    expect(
      await screen.findByText("Review your application for Staff Engineer"),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /approve & send/i }));
    await waitFor(
      () => expect(screen.getByText(/Application sent/)).toBeInTheDocument(),
      { timeout: 4000 },
    );
  });

  it("reject → terminal 'not sent' state", async () => {
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: approval\ndata: {"event":"approval","approval_id":"ap-2"}\n\n`,
        `event: done\ndata: {"event":"done","status":"awaiting_approval","totals":{}}\n\n`,
      ]),
    );
    renderWithProviders(<PrepareApplicationBuilder jobId="j2" />, {
      authValue: { authedStream },
      api: {
        applications: { create: vi.fn(async () => ({ run_id: "r2", session_id: "s2" })), get: vi.fn() },
        approvals: {
          get: vi.fn(async () => ({
            id: "ap-2", application_id: "a2", action_type: "send_application_email",
            payload_snapshot: snapshot, status: "pending", decided_at: null,
            decision_note: null, created_at: "2026-09-06T10:00:00Z",
          })),
          decide: vi.fn(async () => {}),
        },
      },
    });
    await userEvent.click(await screen.findByRole("button", { name: /prepare application/i }));
    await userEvent.click(await screen.findByRole("button", { name: /don't send/i }));
    expect(await screen.findByText(/didn't approve this application/)).toBeInTheDocument();
  });
});
