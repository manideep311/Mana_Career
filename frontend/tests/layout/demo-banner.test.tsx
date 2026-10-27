import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";
import { DemoBanner } from "@/components/layout/DemoBanner";
import type { AppMeta } from "@/lib/api/types";

const META: AppMeta = {
  demo_mode: false, ai_writing: true, web_research: true, email_delivery: "redirect",
  ai_paused: false, retention_days: 0,
};

function render(over: Partial<AppMeta>) {
  const get = vi.fn(async () => ({ ...META, ...over }));
  renderWithProviders(<DemoBanner />, { api: { meta: { get } } });
  return get;
}

describe("DemoBanner", () => {
  it("says plainly what demo mode changes", async () => {
    render({ demo_mode: true, ai_writing: false, web_research: false });
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("Demo mode.");
    expect(note).toHaveTextContent("use simple templates");
    expect(note).toHaveTextContent("web research is off");
  });

  it("with a real model, a demo only mentions what still differs", async () => {
    render({ demo_mode: true, web_research: false, retention_days: 7 });
    const note = await screen.findByRole("note");
    expect(note).not.toHaveTextContent("templates");
    expect(note).toHaveTextContent("web research is off");
    expect(note).toHaveTextContent("accounts are deleted 7 days after sign-up");
  });

  it("says when the day's AI quota is used up, demo or not", async () => {
    render({ ai_paused: true });
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("AI features are paused for today");
    expect(note).toHaveTextContent("Matching, career paths and skill plans still work");
  });

  it("stays silent outside demo mode", async () => {
    const get = render({});
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole("note")).toBeNull();
  });
});
