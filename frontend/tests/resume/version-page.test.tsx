import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import ResumeVersionPage from "@/app/(app)/resume/versions/[id]/page";

/**
 * Per the established RULING R11 (`tests/jobs/job-detail-page.test.tsx`):
 * never touch `useParams` — `test/utils` already mocks it to `() => ({})`,
 * so `id === ""` for the page under test. The mocked `api` methods below
 * ignore their argument and drive the render regardless, exactly like that
 * file's `get`/`remove` mocks do.
 */
const version = {
  id: "v1", kind: "ai_tailored" as const, label: "Tailored for Acme", job_id: "j1",
  parent_version_id: null, created_by: "mana_ai" as const, created_at: "2026-09-04T00:00:00Z",
  claim_validation: { checked: 2, unsupported: [], supported_ratio: 1, passed: true },
  content: {},
};

describe("ResumeVersionPage", () => {
  it("renders the header and the diff once both queries settle", async () => {
    renderWithProviders(<ResumeVersionPage />, {
      api: {
        resumes: {
          version: vi.fn(async () => version),
          diff: vi.fn(async () => ({
            deltas: [{ path: "summary", op: "changed", before: "Old.", after: "New." }],
          })),
        },
      },
    });
    expect(await screen.findByText("Tailored for Acme")).toBeInTheDocument();
    expect(await screen.findByText("New.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Markdown" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeInTheDocument();
  });
});
