import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import { ProfileSkills } from "@/components/profile/ProfileSkills";

function api(over = {}) {
  return {
    profile: {
      skills: vi.fn(async () => [
        { slug: "pytorch", label: "PyTorch", category: "ml_framework",
          proficiency: null, years: null, source: "resume_extraction",
          evidence: [{ kind: "experience", ref_id: "e1" }, { kind: "project", ref_id: "p1" }] },
        { slug: "fastapi", label: "FastAPI", category: "backend",
          proficiency: "advanced", years: 3, source: "user", evidence: [] },
      ]),
      rebuild: vi.fn(async () => undefined),
      ...over,
    },
  };
}

describe("ProfileSkills", () => {
  it("groups skills and shows evidence counts", async () => {
    renderWithProviders(<ProfileSkills />, { api: api() });
    expect(await screen.findByText("PyTorch")).toBeInTheDocument();
    expect(screen.getByText("FastAPI")).toBeInTheDocument();
    expect(screen.getByText(/2 mentions/i)).toBeInTheDocument();
  });

  it("Rebuild from résumé calls the endpoint", async () => {
    const a = api();
    renderWithProviders(<ProfileSkills />, { api: a });
    await screen.findByText("PyTorch");
    await userEvent.click(screen.getByRole("button", { name: /rebuild from résumé/i }));
    await waitFor(() => expect(a.profile.rebuild).toHaveBeenCalledTimes(1));
  });

  it("empty state prompts a résumé upload", async () => {
    renderWithProviders(<ProfileSkills />, { api: api({ skills: vi.fn(async () => []) }) });
    expect(await screen.findByText(/no skills mapped yet/i)).toBeInTheDocument();
  });
});
