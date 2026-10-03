import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PrepareApplicationBuilder } from "@/components/applications/PrepareApplicationBuilder";
import type { ApplicationDelivery } from "@/lib/api/types";
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
  email: { id: "em1", to_email: null, to_name: null, subject: "Application", body: "Hi." },
};

const PAUSED = [
  `event: step\ndata: {"event":"step","node":"cover_letter","status":"ok","summary":"wrote letter"}\n\n`,
  `event: approval\ndata: {"event":"approval","approval_id":"ap-1"}\n\n`,
  `event: done\ndata: {"event":"done","status":"awaiting_approval","totals":{}}\n\n`,
];

function delivery(over: Partial<ApplicationDelivery>): ApplicationDelivery {
  return {
    status: "sending", intended_to: "jobs@acme.com", delivered_to: null, redirected: false,
    sent_at: null, error: null, ...over,
  };
}

function setup(deliveries: ApplicationDelivery[], send = vi.fn()) {
  const decide = vi.fn(async () => {});
  let i = 0;
  const api = {
    meta: {
      get: vi.fn(async () => ({
        demo_mode: true, ai_writing: false, web_research: false, email_delivery: "redirect",
      })),
    },
    applications: {
      create: vi.fn(async () => ({ run_id: "r1", session_id: "s1" })),
      delivery: vi.fn(async () => deliveries[Math.min(i++, deliveries.length - 1)]),
      send,
    },
    approvals: {
      get: vi.fn(async () => ({
        id: "ap-1", application_id: "a1", action_type: "send_application_email",
        payload_snapshot: snapshot, status: "pending", decided_at: null,
        decision_note: null, created_at: "2026-09-06T10:00:00Z",
      })),
      decide,
    },
  };
  renderWithProviders(<PrepareApplicationBuilder jobId="j1" />, {
    authValue: {
      authedStream: vi.fn(async () => streamOf(PAUSED)),
      user: { email: "me@example.com" },
    },
    api,
  });
  return { api, decide };
}

async function approve(to: string) {
  await userEvent.click(await screen.findByRole("button", { name: /prepare application/i }));
  expect(await screen.findByText("Review your application for Staff Engineer")).toBeInTheDocument();
  expect(await screen.findByText(/goes to your own inbox \(me@example.com\)/)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Send to"), to);
  await userEvent.click(screen.getByRole("button", { name: /approve & send/i }));
}

describe("PrepareApplicationBuilder", () => {
  it("approve with a recipient → demo delivery to your own inbox", async () => {
    const { decide } = setup([
      delivery({ status: "sending" }),
      delivery({
        status: "sent", delivered_to: "me@example.com", redirected: true,
        sent_at: "2026-09-30T10:42:00Z",
      }),
    ]);
    await approve("jobs@acme.com");
    expect(decide).toHaveBeenCalledWith("ap-1", { decision: "approve", to_email: "jobs@acme.com" });
    await waitFor(
      () =>
        expect(screen.getByRole("status")).toHaveTextContent(
          /Delivered to your inbox \(me@example.com\).*as a demo\. In the live product it goes to jobs@acme.com/,
        ),
      { timeout: 6000 },
    );
  });

  it("a failed send shows why and can be sent again", async () => {
    const send = vi.fn(async () =>
      delivery({ status: "sent", delivered_to: "jobs@acme.com", sent_at: "2026-09-30T10:45:00Z" }),
    );
    setup([delivery({ status: "failed", error: "The mail server didn't respond." })], send);
    await approve("jobs@acme.com");
    expect(await screen.findByRole("alert")).toHaveTextContent("Your application wasn't sent.");
    expect(screen.getByText("The mail server didn't respond.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try sending again/i }));
    expect(send).toHaveBeenCalledWith("a1");
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Application sent to jobs@acme.com.*A copy is in your inbox/,
    );
  });

  it("reject → terminal 'not sent' state", async () => {
    setup([]);
    await userEvent.click(await screen.findByRole("button", { name: /prepare application/i }));
    await userEvent.click(await screen.findByRole("button", { name: /don't send/i }));
    expect(await screen.findByText(/didn't approve this application/)).toBeInTheDocument();
  });
});
