import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExtractionReview } from "@/components/resume/ExtractionReview";
import type { ResumeExtraction } from "@/lib/api/types";

const extraction = {
  full_name: "Jane Doe",
  email: "jane@example.com",
  summary: "ML engineer.",
  skills: ["Python", "PyTorch"],
  experiences: [
    { company: "Acme", title: "ML Eng" },
    { company: "Globex", title: "Intern" },
  ],
  education: [],
  projects: [],
  certifications: [],
};

describe("ExtractionReview", () => {
  it("seeds fields from the extraction and confirms the edited payload", async () => {
    const onConfirm = vi.fn<(payload: unknown) => Promise<void>>(async () => {});
    render(<ExtractionReview extraction={extraction} onConfirm={onConfirm} />);

    expect(screen.getByLabelText(/full name/i)).toHaveValue("Jane Doe");
    expect(screen.getByLabelText(/summary/i)).toHaveValue("ML engineer.");

    // edit location
    await userEvent.type(screen.getByLabelText(/location/i), "Berlin");
    // drop the second experience row
    const rows = screen.getAllByTestId("experience-row");
    await userEvent.click(within(rows[1]).getByRole("button", { name: /remove/i }));

    await userEvent.click(screen.getByRole("button", { name: /confirm & build/i }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const payload = onConfirm.mock.calls[0][0] as ResumeExtraction &
      Required<Pick<ResumeExtraction, "experiences">>;
    expect(payload.location).toBe("Berlin");
    expect(payload.experiences).toHaveLength(1);
    expect(payload.experiences[0].company).toBe("Acme");
    expect(payload.skills).toEqual(["Python", "PyTorch"]);
  });
});
