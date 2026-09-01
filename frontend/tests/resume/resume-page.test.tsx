import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders, mockPush } from "@/test/utils";
import ResumePage from "@/app/(app)/resume/page";

function stubApi(over: Record<string, unknown> = {}) {
  return {
    resumes: {
      list: vi.fn(async () => [] as unknown[]),
      get: vi.fn(),
      upload: vi.fn(async () => ({ id: "r1", status: "uploaded" })),
      extraction: vi.fn(async () => ({
        full_name: "Jane",
        experiences: [],
        education: [],
        projects: [],
        certifications: [],
      })),
      patch: vi.fn(),
      reprocess: vi.fn(),
      remove: vi.fn(),
      confirmProfile: vi.fn(async () => undefined),
      ...over,
    },
  };
}

describe("ResumePage", () => {
  it("shows the dropzone when the user has no résumés", async () => {
    renderWithProviders(<ResumePage />, {
      api: stubApi(),
      authValue: { status: "authed", user: { id: "u1" } as never },
    });
    expect(await screen.findByTestId("resume-file-input")).toBeInTheDocument();
  });

  it("uploads, walks the stepper to extracted, confirms, and routes to /dashboard", async () => {
    const api = stubApi();
    // authedStream yields a completed pipeline for r1 so the stepper never hangs
    // while the résumé list catches up to `status: "extracted"`.
    const authedStream = vi.fn(
      async () =>
        new Response(
          `event: status\ndata: {"status":"extracted","message":"Ready to review"}\n\n` +
            `event: done\ndata: {"status":"extracted","totals":{}}\n\n`,
          { status: 200 },
        ),
    );

    renderWithProviders(<ResumePage />, {
      api,
      authValue: { status: "authed", user: { id: "u1" } as never, authedStream },
    });

    await userEvent.upload(
      await screen.findByTestId("resume-file-input"),
      new File([new Uint8Array(10)], "cv.pdf", { type: "application/pdf" }),
    );

    // The list is re-fetched after upload — make every subsequent list() return
    // the uploaded résumé as already extracted so the flow lands on review.
    api.resumes.list.mockResolvedValue([
      {
        id: "r1",
        title: "cv.pdf",
        original_filename: "cv.pdf",
        content_type: "application/pdf",
        size_bytes: 10,
        page_count: 1,
        status: "extracted",
        parse_error: null,
        is_primary: true,
        confirmed_at: null,
        created_at: "",
        updated_at: "",
      },
    ] as never);

    await screen.findByLabelText(/full name/i, undefined, { timeout: 3000 });

    await userEvent.click(
      screen.getByRole("button", { name: /confirm & build/i }),
    );

    await waitFor(() =>
      expect(api.resumes.confirmProfile).toHaveBeenCalledWith(
        "r1",
        expect.any(Object),
      ),
    );
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
  });

  it("reports a dropped stream as a connection failure and lets the user re-upload without bouncing back to the stepper", async () => {
    const api = stubApi();
    // The SSE stream dies (proxy / Redis blip) — an `event: error` frame, no
    // `done`. The résumé's DB row is still mid-pipeline.
    const authedStream = vi.fn(
      async () =>
        new Response(
          `event: error\ndata: {"code":"stream.closed","message":"Connection lost"}\n\n`,
          { status: 200 },
        ),
    );

    renderWithProviders(<ResumePage />, {
      api,
      authValue: { status: "authed", user: { id: "u1" } as never, authedStream },
    });

    await userEvent.upload(
      await screen.findByTestId("resume-file-input"),
      new File([new Uint8Array(10)], "cv.pdf", { type: "application/pdf" }),
    );

    api.resumes.list.mockResolvedValue([
      {
        id: "r1",
        title: "cv.pdf",
        original_filename: "cv.pdf",
        content_type: "application/pdf",
        size_bytes: 10,
        page_count: 1,
        status: "extracting",
        parse_error: null,
        is_primary: true,
        confirmed_at: null,
        created_at: "",
        updated_at: "",
      },
    ] as never);

    // Connection-variant copy — NOT the misleading "scanned or image-only PDF"
    // pipeline-failure fallback.
    expect(
      await screen.findByText(/lost the connection/i, undefined, {
        timeout: 3000,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/scanned or image-only/i)).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: /upload a different file/i }),
    );

    // Lands on the dropzone and stays there — the still-"extracting" résumé is
    // NOT re-adopted back into the stepper.
    expect(await screen.findByTestId("resume-file-input")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /confirm & build/i }),
    ).not.toBeInTheDocument();
  });
});
