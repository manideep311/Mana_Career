import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ResumeFailed } from "@/components/resume/ResumeFailed";

describe("ResumeFailed", () => {
  it("shows the message and wires both actions", async () => {
    const onRetry = vi.fn();
    const onReupload = vi.fn();
    render(
      <ResumeFailed
        message="This looks like a scanned PDF — text extraction isn't available yet."
        onRetry={onRetry}
        onReupload={onReupload}
      />,
    );
    expect(screen.getByText(/scanned PDF/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await userEvent.click(screen.getByRole("button", { name: /different file/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onReupload).toHaveBeenCalledTimes(1);
  });

  it("disables Try again while retrying", () => {
    render(
      <ResumeFailed
        message={null}
        onRetry={vi.fn()}
        onReupload={vi.fn()}
        retrying
      />,
    );
    expect(screen.getByRole("button", { name: /retrying/i })).toBeDisabled();
  });
});
