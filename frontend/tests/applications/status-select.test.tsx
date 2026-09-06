import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StatusSelect } from "@/components/applications/StatusSelect";

describe("StatusSelect", () => {
  it("renders all six statuses and reports the picked value", async () => {
    const onChange = vi.fn();
    render(<StatusSelect value="saved" onChange={onChange} />);
    const select = screen.getByRole("combobox", { name: /application status/i });
    expect(screen.getAllByRole("option")).toHaveLength(6);
    await userEvent.selectOptions(select, "interview");
    expect(onChange).toHaveBeenCalledWith("interview");
  });
});
