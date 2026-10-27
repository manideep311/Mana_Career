import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NoAiReaderNote, UploadPrivacyNote } from "@/components/resume/ResumeNotes";
import type { AppMeta } from "@/lib/api/types";
import { renderWithProviders } from "@/test/utils";

const META: AppMeta = {
  demo_mode: false, ai_writing: true, web_research: false, email_delivery: "redirect",
  ai_paused: false, retention_days: 0,
};

function api(over: Partial<AppMeta>) {
  const get = vi.fn(async () => ({ ...META, ...over }));
  return { get, api: { meta: { get } } };
}

describe("UploadPrivacyNote", () => {
  it("warns before a résumé goes into a public demo, with the retention", async () => {
    renderWithProviders(<UploadPrivacyNote />, api({ demo_mode: true, retention_days: 7 }));
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(
      "Demo: don't upload a résumé with details you want kept private.",
    );
    expect(note).toHaveTextContent("deleted 7 days after sign-up");
  });

  it("is silent on a private deployment", async () => {
    const { get, api: a } = api({});
    renderWithProviders(<UploadPrivacyNote />, { api: a });
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole("note")).toBeNull();
  });
});

describe("NoAiReaderNote", () => {
  it("explains the empty sections when no model reads résumés", async () => {
    renderWithProviders(<NoAiReaderNote />, api({ demo_mode: true, ai_writing: false }));
    expect(await screen.findByRole("note")).toHaveTextContent("No AI reader runs here");
  });

  it("is silent when a model reads them", async () => {
    const { get, api: a } = api({});
    renderWithProviders(<NoAiReaderNote />, { api: a });
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole("note")).toBeNull();
  });
});
