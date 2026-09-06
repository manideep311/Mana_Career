import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { mockPush, renderWithProviders } from "@/test/utils";
import JobDetailPage from "@/app/(app)/jobs/[id]/page";

function api(over: Record<string, unknown> = {}) {
  return {
    jobs: {
      get: vi.fn().mockResolvedValue({
        id: "",
        title: "Staff Eng",
        company: "Acme",
        status: "ready",
        required_skills: [],
        responsibilities: [],
        preferred_skills: [],
      }),
    },
    resumes: { list: vi.fn().mockResolvedValue([]) },
    matches: { list: vi.fn().mockResolvedValue({ items: [] }) },
    applications: {
      save: vi.fn().mockResolvedValue({ id: "a1", status: "saved" }),
      ...over,
    },
  };
}

describe("Job Detail — Save to tracker", () => {
  it("saves and routes to the board", async () => {
    const a = api();
    renderWithProviders(<JobDetailPage />, { api: a as never });
    const btn = await screen.findByRole("button", { name: /save to tracker/i });
    await userEvent.click(btn);
    await waitFor(() => expect(a.applications.save).toHaveBeenCalled());
    expect(mockPush).toHaveBeenCalledWith("/applications");
  });
});
