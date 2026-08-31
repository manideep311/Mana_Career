import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

describe("Field", () => {
  it("labels the control and shows an alerting error", () => {
    render(
      <Field id="email" label="Email" error="That email is not right.">
        <Input id="email" />
      </Field>,
    );
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("That email is not right.");
  });
});
