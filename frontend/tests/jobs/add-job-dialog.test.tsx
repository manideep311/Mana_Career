import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useJobEvents", () => ({
  useJobEvents: () => ({
    status: "ready",
    done: true,
    message: null,
    error: null,
  }),
}));

import { AddJobDialog } from "@/components/jobs/AddJobDialog";
import { mockPush, renderWithProviders } from "@/test/utils";

const LONG_JD =
  "We are hiring a senior backend engineer to design, build and scale our " +
  "payments platform across multiple regions.";

describe("AddJobDialog", () => {
  it("rejects a too-short paste, ingests a valid one, then routes to the new job", async () => {
    const user = userEvent.setup();
    const create = vi.fn(async () => ({ id: "j99", status: "ingesting" }));

    renderWithProviders(<AddJobDialog />, { api: { jobs: { create } } });

    await user.click(screen.getByRole("button", { name: /add a job/i }));

    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "too short to be a job description");
    await user.click(screen.getByRole("button", { name: /ingest/i }));

    expect(
      await screen.findByText(/at least 40 characters/i),
    ).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();

    await user.clear(textarea);
    await user.type(textarea, LONG_JD);
    await user.click(screen.getByRole("button", { name: /ingest/i }));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledWith(LONG_JD);
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/jobs/j99"));
  });
});
