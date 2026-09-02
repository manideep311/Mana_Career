import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MatchBadge } from "@/components/jobs/MatchBadge";

describe("MatchBadge", () => {
  it("renders the rounded score as a band-colored pill when ready", () => {
    render(<MatchBadge score={92} band="strong" status="ready" />);
    expect(screen.getByText("92")).toBeInTheDocument();
  });

  it("shows a scoring affordance while the worker runs", () => {
    render(<MatchBadge score={null} band={null} status="scoring" />);
    expect(screen.getByText(/scoring/i)).toBeInTheDocument();
  });

  it("offers a Score button when there is no match yet and calls onScore", () => {
    const onScore = vi.fn();
    render(
      <MatchBadge score={null} band={null} status={null} onScore={onScore} />,
    );
    const button = screen.getByRole("button", { name: /score/i });
    fireEvent.click(button);
    expect(onScore).toHaveBeenCalledTimes(1);
  });

  it("renders nothing for a null status with no onScore handler", () => {
    const { container } = render(
      <MatchBadge score={null} band={null} status={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a Retry affordance when scoring failed", () => {
    const onScore = vi.fn();
    render(
      <MatchBadge
        score={null}
        band={null}
        status="failed"
        onScore={onScore}
      />,
    );
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onScore).toHaveBeenCalledTimes(1);
  });
});
