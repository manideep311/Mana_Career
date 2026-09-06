import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { KanbanBoard } from "@/components/applications/KanbanBoard";
import type { Application } from "@/lib/api/types";

function app(id: string, status: string, job_id = "j1"): Application {
  return {
    id, job_id, resume_version_id: null, cover_letter_id: null, application_email_id: null,
    status, match_score: null, source: "user", notes: null, ai_session_id: null,
    applied_at: null, last_status_change_at: "2026-09-06T10:00:00Z",
    created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
  };
}

describe("KanbanBoard", () => {
  it("buckets applications into columns with counts", () => {
    render(
      <KanbanBoard
        applications={[app("a", "saved"), app("b", "saved"), app("c", "applied")]}
        jobs={{ j1: { title: "Staff Eng", company: "Acme" } }}
        onMove={vi.fn()}
        movingId={null}
      />,
    );
    const saved = screen.getByRole("region", { name: "Saved" });
    expect(within(saved).getAllByText("Staff Eng")).toHaveLength(2);
    const applied = screen.getByRole("region", { name: "Applied" });
    expect(within(applied).getAllByText("Staff Eng")).toHaveLength(1);
  });

  it("calls onMove with the card id and picked status", async () => {
    const onMove = vi.fn();
    render(
      <KanbanBoard
        applications={[app("a", "saved")]}
        jobs={{ j1: { title: "Staff Eng", company: "Acme" } }}
        onMove={onMove}
        movingId={null}
      />,
    );
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /application status/i }),
      "interview",
    );
    expect(onMove).toHaveBeenCalledWith("a", "interview");
  });
});
