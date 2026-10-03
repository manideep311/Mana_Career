import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockPush, renderWithProviders } from "@/test/utils";
import { AccountDataSection, REVOKE_AFTER_MS } from "@/components/profile/AccountDataSection";
import { ProblemError } from "@/lib/api/fetcher";

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:export");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Download your data", () => {
  it("fetches the export and saves it under the server's file name", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const authedStream = vi.fn(async () =>
      new Response(new Blob(["zip"]), {
        status: 200,
        headers: { "content-disposition": 'attachment; filename="mana-career-export-2026-09-30.zip"' },
      }),
    );
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.download);
    });
    renderWithProviders(<AccountDataSection />, { authValue: { authedStream } });
    await userEvent.click(screen.getByRole("button", { name: /download your data/i }));
    await waitFor(() => expect(clicks).toEqual(["mana-career-export-2026-09-30.zip"]));
    expect(authedStream).toHaveBeenCalledWith("/api/v1/account/export");
    // The file is released only after the browser has had time to read it.
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(REVOKE_AFTER_MS);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:export");
  });

  it("says so when the export fails", async () => {
    const authedStream = vi.fn(async () => new Response(null, { status: 500 }));
    renderWithProviders(<AccountDataSection />, { authValue: { authedStream } });
    await userEvent.click(screen.getByRole("button", { name: /download your data/i }));
    expect(await screen.findByText(/Couldn't prepare your download/)).toBeInTheDocument();
  });
});

describe("Delete account", () => {
  async function openDialog() {
    await userEvent.click(screen.getByRole("button", { name: /delete account/i }));
    return screen.getByRole("dialog", { name: "Delete your account?" });
  }

  it("explains what goes and only enables the button with the password and the word", async () => {
    renderWithProviders(<AccountDataSection />, { api: { account: { remove: vi.fn() } } });
    const dialog = await openDialog();
    expect(dialog).toHaveTextContent("This can't be undone");
    expect(dialog).toHaveTextContent(/Every résumé you uploaded/);
    const submit = screen.getByRole("button", { name: "Delete my account" });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Your password"), "secret-passphrase");
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "delete");
    expect(submit).toBeDisabled(); // must be the exact word
    await userEvent.clear(screen.getByLabelText("Type DELETE to confirm"));
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    expect(submit).toBeEnabled();
  });

  it("a wrong password keeps you signed in and deletes nothing", async () => {
    const remove = vi.fn(async () => {
      throw new ProblemError("invalid_password", 403, { detail: "That password isn't right." });
    });
    const logout = vi.fn(async () => {});
    renderWithProviders(<AccountDataSection />, {
      api: { account: { remove } },
      authValue: { logout },
    });
    await openDialog();
    await userEvent.type(screen.getByLabelText("Your password"), "typo");
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));
    expect(await screen.findByText("That password isn't right.")).toBeInTheDocument();
    expect(logout).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("on success signs out, goes home and confirms", async () => {
    const remove = vi.fn(async () => undefined);
    const logout = vi.fn(async () => {});
    renderWithProviders(<AccountDataSection />, {
      api: { account: { remove } },
      authValue: { logout },
    });
    await openDialog();
    await userEvent.type(screen.getByLabelText("Your password"), "secret-passphrase");
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/"));
    expect(remove).toHaveBeenCalledWith({ password: "secret-passphrase", confirm: "DELETE" });
    expect(logout).toHaveBeenCalledOnce();
    expect(await screen.findByText("Your account has been deleted.")).toBeInTheDocument();
  });

  it("keeps keyboard focus inside the dialog", async () => {
    renderWithProviders(<AccountDataSection />, { api: { account: { remove: vi.fn() } } });
    await openDialog();
    const password = screen.getByLabelText("Your password");
    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(password).toHaveFocus();
    await userEvent.tab(); // the confirm word
    await userEvent.tab(); // Cancel (Delete is disabled until ready)
    expect(cancel).toHaveFocus();
    await userEvent.tab(); // wraps back instead of leaving the dialog
    expect(password).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(cancel).toHaveFocus();
  });

  it("Cancel and Escape close without deleting", async () => {
    const remove = vi.fn();
    renderWithProviders(<AccountDataSection />, { api: { account: { remove } } });
    await openDialog();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await openDialog();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(remove).not.toHaveBeenCalled();
  });
});
