import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ApplicationsPage from "@/app/(app)/applications/page";
import { renderWithProviders } from "@/test/utils";
import type { Application } from "@/lib/api/types";

function app(id: string, status: string): Application {
  return {
    id, job_id: "j1", resume_version_id: null, cover_letter_id: null, application_email_id: null,
    status, match_score: null, source: "user", notes: null, ai_session_id: null,
    applied_at: null, last_status_change_at: "2026-09-06T10:00:00Z",
    created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
  };
}

function api(over: Record<string, unknown> = {}) {
  return {
    applications: {
      list: vi.fn().mockResolvedValue({ items: [app("a", "saved")], total: 1, limit: 100, offset: 0 }),
      patch: vi.fn().mockResolvedValue(app("a", "applied")),
      ...over,
    },
    jobs: { get: vi.fn().mockResolvedValue({ title: "Staff Eng", company: "Acme" }) },
  };
}

describe("ApplicationsPage", () => {
  it("optimistically moves a card and keeps it when the patch resolves", async () => {
    renderWithProviders(<ApplicationsPage />, { api: api() as never });
    await screen.findByText("Staff Eng");
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /application status/i }),
      "applied",
    );
    await waitFor(() => {
      const applied = screen.getByRole("region", { name: "Applied" });
      expect(within(applied).getByText("Staff Eng")).toBeInTheDocument();
    });
  });

  it("rolls the card back and toasts when the patch fails", async () => {
    renderWithProviders(
      <ApplicationsPage />,
      { api: api({ patch: vi.fn().mockRejectedValue(new Error("nope")) }) as never },
    );
    await screen.findByText("Staff Eng");
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /application status/i }),
      "applied",
    );
    await waitFor(() => {
      const saved = screen.getByRole("region", { name: "Saved" });
      expect(within(saved).getByText("Staff Eng")).toBeInTheDocument();
    });
  });

  it("shows the empty state with a jobs link", async () => {
    renderWithProviders(
      <ApplicationsPage />,
      { api: api({ list: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 }) }) as never },
    );
    expect(await screen.findByText(/no applications yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /browse jobs/i })).toHaveAttribute("href", "/jobs");
  });
});
