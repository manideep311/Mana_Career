import { describe, expect, it, vi } from "vitest";

import { ProblemError } from "@/lib/api/fetcher";
import { applyProblemToForm } from "@/lib/api/form-errors";

describe("applyProblemToForm", () => {
  it("maps a validation_error onto each field by the tail of its loc path", () => {
    const setError = vi.fn();
    const err = new ProblemError("validation_error", 422, {
      errors: [
        { loc: ["body", "email"], msg: "Not a valid email." },
        { loc: ["body", "password"], msg: "Too short." },
      ],
    });

    const handled = applyProblemToForm(err, setError);

    expect(handled).toBe(true);
    expect(setError).toHaveBeenCalledTimes(2);
    expect(setError).toHaveBeenCalledWith("email", { message: "Not a valid email." });
    expect(setError).toHaveBeenCalledWith("password", { message: "Too short." });
  });

  it("sets a root error from problem.detail for any other ProblemError", () => {
    const setError = vi.fn();
    const err = new ProblemError("invalid_credentials", 401, {
      detail: "That email or password is not right.",
    });

    const handled = applyProblemToForm(err, setError);

    expect(handled).toBe(true);
    expect(setError).toHaveBeenCalledTimes(1);
    expect(setError).toHaveBeenCalledWith("root", {
      message: "That email or password is not right.",
    });
  });

  it("falls back to a generic root message when a ProblemError carries no detail", () => {
    const setError = vi.fn();

    const handled = applyProblemToForm(new ProblemError("teapot", 418, {}), setError);

    expect(handled).toBe(true);
    expect(setError).toHaveBeenCalledWith("root", {
      message: "Something went wrong. Try again.",
    });
  });

  it("returns false and touches nothing for a plain Error", () => {
    const setError = vi.fn();

    const handled = applyProblemToForm(new Error("network down"), setError);

    expect(handled).toBe(false);
    expect(setError).not.toHaveBeenCalled();
  });

  it("returns false for a validation_error-shaped plain object that is not a ProblemError", () => {
    const setError = vi.fn();

    const handled = applyProblemToForm(
      { code: "validation_error", problem: { errors: [{ loc: ["x"], msg: "no" }] } },
      setError,
    );

    expect(handled).toBe(false);
    expect(setError).not.toHaveBeenCalled();
  });
});
