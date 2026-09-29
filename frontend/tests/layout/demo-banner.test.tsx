import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import { DemoBanner } from "@/components/layout/DemoBanner";

describe("DemoBanner", () => {
  it("says plainly what demo mode changes", async () => {
    renderWithProviders(<DemoBanner />, {
      api: { meta: { get: vi.fn(async () => ({ demo_mode: true, ai_writing: false, web_research: false })) } },
    });
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("Demo mode.");
    expect(note).toHaveTextContent("use simple templates");
    expect(note).toHaveTextContent("web research is off");
  });

  it("stays silent outside demo mode", async () => {
    const get = vi.fn(async () => ({ demo_mode: false, ai_writing: true, web_research: true }));
    renderWithProviders(<DemoBanner />, { api: { meta: { get } } });
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole("note")).toBeNull();
  });
});
