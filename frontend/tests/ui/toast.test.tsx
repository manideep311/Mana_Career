import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Toaster, useToast } from "@/components/ui/toaster";

function Trigger() {
  const { toast } = useToast();
  return <button onClick={() => toast({ title: "Profile saved" })}>go</button>;
}

describe("toast", () => {
  it("shows a toast when triggered", async () => {
    render(
      <Toaster>
        <Trigger />
      </Toaster>,
    );
    await userEvent.click(screen.getByRole("button", { name: "go" }));
    expect(await screen.findByText("Profile saved")).toBeInTheDocument();
  });
});
