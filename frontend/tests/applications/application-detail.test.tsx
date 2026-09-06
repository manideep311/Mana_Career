import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import ApplicationDetailPage from "@/app/(app)/applications/[id]/page";
import type { Application } from "@/lib/api/types";

const appRow: Application = {
  id: "a1", job_id: "j1", resume_version_id: "rv1", cover_letter_id: null,
  application_email_id: null, status: "applied", match_score: null, source: "mana_ai",
  notes: null, ai_session_id: null, applied_at: "2026-09-06T10:00:00Z",
  last_status_change_at: "2026-09-06T10:00:00Z", created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-06T10:00:00Z",
};

function api(over: Record<string, unknown> = {}) {
  return {
    applications: {
      get: vi.fn().mockResolvedValue(appRow),
      timeline: vi.fn().mockResolvedValue({
        items: [
          { kind: "status_change", at: "2026-09-06T10:00:00Z", title: "Moved to applied", detail: { to: "applied" } },
        ],
      }),
      patch: vi.fn().mockResolvedValue(appRow),
      addNote: vi.fn().mockResolvedValue({ kind: "note", at: "2026-09-06T11:00:00Z", title: "Note added", detail: { body: "x" } }),
      ...over,
    },
    jobs: { get: vi.fn().mockResolvedValue({ title: "Staff Eng", company: "Acme" }) },
  };
}

describe("ApplicationDetailPage", () => {
  it("renders the timeline and the job header", async () => {
    renderWithProviders(<ApplicationDetailPage />, { api: api() as never });
    expect(await screen.findByText("Staff Eng")).toBeInTheDocument();
    expect(screen.getByText("Moved to applied")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /tailored résumé/i })).toHaveAttribute(
      "href", "/resume/versions/rv1",
    );
  });

  it("optimistically prepends a note on submit", async () => {
    // Freeze the POST in-flight so the assertion lands on the optimistic frame,
    // before the page's finally-block `invalidateQueries` refetches the (static)
    // mock timeline and drops the not-yet-persisted note.
    renderWithProviders(<ApplicationDetailPage />, {
      api: api({ addNote: vi.fn(() => new Promise<never>(() => {})) }) as never,
    });
    await screen.findByText("Staff Eng");
    await userEvent.type(screen.getByRole("textbox", { name: /new note/i }), "Rang the recruiter");
    await userEvent.click(screen.getByRole("button", { name: /add note/i }));
    await waitFor(() => expect(screen.getByText("Rang the recruiter")).toBeInTheDocument());
  });
});
