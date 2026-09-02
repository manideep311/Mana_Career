import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JobCard } from "@/components/jobs/JobCard";
import type { JobCard as JobCardT } from "@/lib/api/types";

const base: JobCardT = {
  id: "j1", title: "Senior ML Engineer", company: "Nimbus AI", location: "Remote",
  work_mode: "remote", seniority: "senior", employment_type: "Full-time",
  salary_min: 190000, salary_max: 240000, salary_currency: "USD", salary_period: "year",
  is_seed: true, status: "ready", posted_at: null, created_at: "2026-08-20T00:00:00Z",
  required_skills: [
    { slug: "python", label: "Python", weight: 0.9 },
    { slug: "pytorch", label: "PyTorch", weight: 0.8 },
  ],
};

describe("JobCard", () => {
  it("renders title, company, salary and skill chips, links to detail", () => {
    render(<JobCard job={base} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/jobs/j1");
    expect(screen.getByText("Senior ML Engineer")).toBeInTheDocument();
    expect(screen.getByText(/Nimbus AI/)).toBeInTheDocument();
    expect(screen.getByText(/190k/)).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText(/sample/i)).toBeInTheDocument();
  });

  it("falls back gracefully when fields are null", () => {
    render(<JobCard job={{ ...base, title: null, company: null, salary_min: null, salary_max: null, is_seed: false }} />);
    expect(screen.getByText(/untitled role/i)).toBeInTheDocument();
    expect(screen.queryByText(/sample/i)).not.toBeInTheDocument();
  });
});
