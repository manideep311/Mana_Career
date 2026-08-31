import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, CardBody, CardTitle } from "@/components/ui/card";

describe("Card", () => {
  it("renders a titled card", () => {
    render(
      <Card>
        <CardTitle>Profile strength</CardTitle>
        <CardBody>62 / 100</CardBody>
      </Card>,
    );
    expect(screen.getByRole("heading", { name: "Profile strength" })).toBeInTheDocument();
    expect(screen.getByText("62 / 100")).toBeInTheDocument();
  });
});
