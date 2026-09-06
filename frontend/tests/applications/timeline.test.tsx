import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Timeline } from "@/components/applications/Timeline";

describe("Timeline", () => {
  it("renders items in given order with detail entries", () => {
    render(
      <Timeline
        items={[
          { kind: "note", at: "2026-09-06T10:00:00Z", title: "Note added", detail: { body: "Rang HR" } },
          { kind: "status_change", at: "2026-09-05T10:00:00Z", title: "Moved to applied", detail: { from: "saved", to: "applied" } },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Note added");
    expect(items[0]).toHaveTextContent("Rang HR");
    expect(items[1]).toHaveTextContent("Moved to applied");
  });

  it("shows the empty copy", () => {
    render(<Timeline items={[]} />);
    expect(screen.getByText(/no history yet/i)).toBeInTheDocument();
  });
});
