import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HowItWorksPlayer, STEP_MS } from "@/components/landing/HowItWorksPlayer";

function mockReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: reduce, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("HowItWorksPlayer", () => {
  it("opens a labelled dialog that plays through the steps on its own", () => {
    vi.useFakeTimers();
    mockReducedMotion(false);
    render(<HowItWorksPlayer />);
    fireEvent.click(screen.getByRole("button", { name: /watch how it works/i }));
    const dialog = screen.getByRole("dialog", { name: "Share your résumé" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    act(() => vi.advanceTimersByTime(STEP_MS));
    expect(screen.getByRole("dialog", { name: "See where it can take you" })).toBeInTheDocument();
    expect(screen.getAllByText("Example").length).toBeGreaterThan(0);
  });

  it("stays still under reduced motion until you step through it", () => {
    vi.useFakeTimers();
    mockReducedMotion(true);
    render(<HowItWorksPlayer />);
    fireEvent.click(screen.getByRole("button", { name: /watch how it works/i }));
    act(() => vi.advanceTimersByTime(STEP_MS * 3));
    expect(screen.getByRole("dialog", { name: "Share your résumé" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "ArrowRight" });
    expect(screen.getByRole("dialog", { name: "See where it can take you" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("closes with Escape and returns focus to the trigger", async () => {
    mockReducedMotion(true);
    render(<HowItWorksPlayer />);
    const trigger = screen.getByRole("button", { name: /watch how it works/i });
    await userEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("the last step promises the approval gate", async () => {
    mockReducedMotion(true);
    render(<HowItWorksPlayer />);
    await userEvent.click(screen.getByRole("button", { name: /watch how it works/i }));
    await userEvent.click(screen.getByRole("button", { name: "Step 4: Take the next step" }));
    expect(screen.getByRole("dialog", { name: "Take the next step" })).toHaveTextContent(
      "Nothing will be sent until you approve it.",
    );
  });
});
