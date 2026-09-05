import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TailorButton } from "@/components/resume/TailorButton";
import { renderWithProviders } from "@/test/utils";

const confirmedPrimary = {
  id: "r-primary", title: null, original_filename: "cv.pdf", content_type: "application/pdf",
  size_bytes: 100, page_count: 1, status: "extracted" as const, parse_error: null,
  is_primary: true, confirmed_at: "2026-09-01T00:00:00Z", created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};
const confirmedOther = { ...confirmedPrimary, id: "r-other", is_primary: false };
const unconfirmed = { ...confirmedPrimary, id: "r-draft", is_primary: false, confirmed_at: null };

describe("TailorButton", () => {
  it("is disabled with no confirmed résumé", async () => {
    renderWithProviders(<TailorButton jobId="j1" />, {
      api: { resumes: { list: vi.fn(async () => [unconfirmed]) } },
    });
    expect(await screen.findByRole("button", { name: /tailor résumé for this job/i })).toBeDisabled();
  });

  it("tailors the primary confirmed résumé, not a non-primary one", async () => {
    const tailor = vi.fn(async () => ({ run_id: "run1", session_id: "sess1" }));
    renderWithProviders(<TailorButton jobId="j1" />, {
      api: {
        resumes: { list: vi.fn(async () => [confirmedOther, confirmedPrimary]), tailor },
      },
    });
    // The button exists (disabled, spinner) even while `resumes.list()` is
    // still pending, so `findByRole` alone can resolve against that first
    // paint before the query settles. Poll until it flips to enabled.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /tailor résumé for this job/i })).toBeEnabled(),
    );
    const btn = screen.getByRole("button", { name: /tailor résumé for this job/i });
    await userEvent.click(btn);
    await waitFor(() => expect(tailor).toHaveBeenCalledWith("r-primary", { job_id: "j1" }));
  });

  it("shows the resume_suggestion block once the run streams it", async () => {
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
    const authedStream = vi.fn(async () =>
      streamOf([
        `event: block\ndata: {"event":"block","block":{"kind":"resume_suggestion","suggestion_id":"v1"}}\n\n`,
        `event: done\ndata: {"event":"done"}\n\n`,
      ]),
    );
    renderWithProviders(<TailorButton jobId="j1" />, {
      api: {
        resumes: {
          list: vi.fn(async () => [confirmedPrimary]),
          tailor: vi.fn(async () => ({ run_id: "run1", session_id: "sess1" })),
          version: vi.fn(async () => ({
            id: "v1", kind: "ai_tailored", label: null, job_id: "j1", parent_version_id: null,
            created_by: "mana_ai", created_at: "2026-09-04T00:00:00Z",
            claim_validation: { checked: 2, unsupported: [], supported_ratio: 1, passed: true },
            content: {},
          })),
        },
      },
      authValue: { authedStream },
    });
    const btn = await screen.findByRole("button", { name: /tailor résumé for this job/i });
    await userEvent.click(btn);
    expect(await screen.findByText("Your résumé was tailored for this role")).toBeInTheDocument();
  });
});
