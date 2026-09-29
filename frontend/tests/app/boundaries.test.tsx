import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/test/utils";
import ErrorPage from "@/app/error";
import NotFound from "@/app/not-found";
import Loading from "@/app/(app)/loading";

describe("route boundaries", () => {
  it("error boundary offers a retry and a way home without leaking the message", async () => {
    const reset = vi.fn();
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const err = Object.assign(new Error("SELECT * FROM secrets failed"), { digest: "abc123" });
    render(<ErrorPage error={err} reset={reset} />);
    expect(screen.getByRole("alert")).not.toHaveTextContent("SELECT");
    expect(screen.getByText("Reference: abc123")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/dashboard");
    spy.mockRestore();
  });

  it("not-found says what happened and where to go", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("This page isn't here");
    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/dashboard");
  });

  it("loading placeholder is marked busy for assistive tech", () => {
    render(<Loading />);
    expect(screen.getByLabelText("Loading")).toHaveAttribute("aria-busy", "true");
  });
});
