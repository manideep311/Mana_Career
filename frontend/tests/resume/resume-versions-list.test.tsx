import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResumeVersionsList } from "@/components/resume/ResumeVersionsList";
import { renderWithProviders } from "@/test/utils";

describe("ResumeVersionsList", () => {
  it("renders nothing when there are no ai_tailored versions", async () => {
    // Not `container.toBeEmptyDOMElement()`: `renderWithProviders` always mounts
    // `<Toaster>`, whose Radix `ToastPrimitive.Viewport` renders a "Notifications"
    // region regardless of pending toasts, so `container` is never literally
    // empty. Assert on the component's own output instead: the loading
    // `<Skeleton>` (`.animate-pulse`) disappears once the query settles, and no
    // "Tailored versions" heading or version link ever appears.
    const versions = vi.fn(async () => ({
      items: [
        {
          id: "v0", kind: "base_snapshot", label: null, job_id: null,
          parent_version_id: null, created_by: "user", created_at: "2026-09-01T00:00:00Z",
          claim_validation: {},
        },
      ],
    }));
    const { container } = renderWithProviders(<ResumeVersionsList resumeId="r1" />, {
      api: { resumes: { versions } },
    });
    await waitFor(() => expect(versions).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector(".animate-pulse")).toBeNull());
    expect(screen.queryByText("Tailored versions")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("lists tailored versions newest first, linking to the diff page", async () => {
    renderWithProviders(<ResumeVersionsList resumeId="r1" />, {
      api: {
        resumes: {
          versions: vi.fn(async () => ({
            items: [
              {
                id: "v1", kind: "ai_tailored", label: "Tailored for Acme", job_id: "j1",
                parent_version_id: "v0", created_by: "mana_ai", created_at: "2026-09-04T00:00:00Z",
                claim_validation: { checked: 3, unsupported: [], supported_ratio: 1, passed: true },
              },
            ],
          })),
        },
      },
    });
    expect(await screen.findByText("Tailored versions")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Tailored for Acme/ })).toHaveAttribute(
      "href",
      "/resume/versions/v1",
    );
  });
});
