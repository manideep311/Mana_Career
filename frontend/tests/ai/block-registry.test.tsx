import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BlockView } from "@/components/ai/blocks/block-registry";
import { renderWithProviders } from "@/test/utils";

const job = {
  id: "j1", title: "Staff Engineer", company: "Acme", location: "Remote",
  work_mode: "remote", seniority: "staff", employment_type: "full_time",
  salary_min: null, salary_max: null, salary_currency: null, salary_period: null,
  is_seed: false, status: "ready", posted_at: null, created_at: "2026-09-01T00:00:00Z",
  required_skills: [],
};

describe("BlockView", () => {
  it("renders a text block as paragraphs", () => {
    renderWithProviders(<BlockView block={{ kind: "text", markdown: "Line one.\n\nLine two." }} />);
    expect(screen.getByText("Line one.")).toBeInTheDocument();
    expect(screen.getByText("Line two.")).toBeInTheDocument();
  });

  it("renders a job_card block by fetching the job", async () => {
    renderWithProviders(
      <BlockView block={{ kind: "job_card", job_id: "j1", match_id: null }} />,
      { api: { jobs: { get: vi.fn(async () => job) }, matches: { get: vi.fn() } } },
    );
    expect(await screen.findByText("Staff Engineer")).toBeInTheDocument();
  });

  it("renders insufficient_info with the missing list", () => {
    renderWithProviders(
      <BlockView block={{ kind: "insufficient_info", topic: "job_match", missing: ["a job in your corpus", "a fuller profile"] }} />,
    );
    expect(screen.getByText(/a job in your corpus/)).toBeInTheDocument();
    expect(screen.getByText(/a fuller profile/)).toBeInTheDocument();
  });

  it("shows a muted fallback for an unknown kind", () => {
    renderWithProviders(<BlockView block={{ kind: "approval_action", approval_id: "a1" } as never} />);
    expect(screen.getByText(/not available yet/i)).toBeInTheDocument();
  });
});
