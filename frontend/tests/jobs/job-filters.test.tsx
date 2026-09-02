import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockReplace, renderWithProviders } from "@/test/utils";
import { JobFilters } from "@/components/jobs/JobFilters";

describe("JobFilters", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders every control unset from an empty URLSearchParams", () => {
    renderWithProviders(<JobFilters />);
    expect(screen.getByLabelText(/search/i)).toHaveValue("");
    expect(screen.getByLabelText(/work mode/i)).toHaveValue("");
    expect(screen.getByLabelText(/seniority/i)).toHaveValue("");
    expect(screen.getByLabelText(/min salary/i)).toHaveValue("");
    expect(
      screen.queryByRole("button", { name: /clear filters/i }),
    ).not.toBeInTheDocument();
  });

  it("debounces the search box into a q= query param", () => {
    renderWithProviders(<JobFilters />);
    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: "react" },
    });
    expect(mockReplace).not.toHaveBeenCalled();
    vi.advanceTimersByTime(300);
    expect(mockReplace).toHaveBeenCalledWith(expect.stringContaining("q=react"));
  });

  it("writes work_mode=remote as soon as the mode is picked", () => {
    renderWithProviders(<JobFilters />);
    fireEvent.change(screen.getByLabelText(/work mode/i), {
      target: { value: "remote" },
    });
    expect(mockReplace).toHaveBeenCalledWith(
      expect.stringContaining("work_mode=remote"),
    );
  });
});
