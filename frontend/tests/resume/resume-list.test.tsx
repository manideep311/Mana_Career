import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ResumeList } from "@/components/resume/ResumeList";
import type { ResumeOut } from "@/lib/api/types";

const base: ResumeOut = {
  id: "r1", title: "Senior CV", original_filename: "cv.pdf", content_type: "application/pdf",
  size_bytes: 1000, page_count: 2, status: "extracted", parse_error: null, is_primary: true,
  confirmed_at: "2026-09-01T00:00:00Z", created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z",
};

describe("ResumeList", () => {
  it("shows Review for an extracted-but-unconfirmed résumé and Try again for a failed one", async () => {
    const onReview = vi.fn();
    const onRetry = vi.fn();
    const rows: ResumeOut[] = [
      { ...base, id: "r2", title: "Draft", is_primary: false, confirmed_at: null },
      { ...base, id: "r3", title: "Broken", is_primary: false, status: "failed", parse_error: "scanned", confirmed_at: null },
    ];
    render(
      <ResumeList
        resumes={rows}
        onSetPrimary={vi.fn()} onReview={onReview} onRetry={onRetry}
        onDelete={vi.fn()} onUploadAnother={vi.fn()} busyId={null}
      />,
    );
    await userEvent.click(within(screen.getByText("Draft").closest("li")!).getByRole("button", { name: /re-review draft/i }));
    await userEvent.click(within(screen.getByText("Broken").closest("li")!).getByRole("button", { name: /retry broken/i }));
    expect(onReview).toHaveBeenCalledWith("r2");
    expect(onRetry).toHaveBeenCalledWith("r3");
  });

  it("confirms before delete", async () => {
    const onDelete = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <ResumeList
        resumes={[base]} onSetPrimary={vi.fn()} onReview={vi.fn()} onRetry={vi.fn()}
        onDelete={onDelete} onUploadAnother={vi.fn()} busyId={null}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    expect(onDelete).toHaveBeenCalledWith("r1");
  });
});
