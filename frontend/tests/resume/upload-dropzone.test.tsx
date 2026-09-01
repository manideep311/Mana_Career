import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UploadDropzone } from "@/components/resume/UploadDropzone";

const pdf = (name = "cv.pdf", bytes = 100) =>
  new File([new Uint8Array(bytes)], name, { type: "application/pdf" });

const txt = (name = "notes.txt") =>
  new File(["hi"], name, { type: "text/plain" });

describe("UploadDropzone", () => {
  it("calls onFile for a valid PDF", async () => {
    const onFile = vi.fn();
    render(<UploadDropzone onFile={onFile} />);
    await userEvent.upload(screen.getByTestId("resume-file-input"), pdf());
    expect(onFile).toHaveBeenCalledTimes(1);
    expect(onFile.mock.calls[0][0].name).toBe("cv.pdf");
  });

  it("rejects a non-PDF with an inline alert and does not call onFile", async () => {
    const onFile = vi.fn();
    render(<UploadDropzone onFile={onFile} />);
    // { applyAccept: false } bypasses the OS-picker `accept` filter so the test
    // exercises the component's own pick() type-guard — the path a real "All
    // Files" override or a drag-drop takes.
    await userEvent.upload(screen.getByTestId("resume-file-input"), txt(), {
      applyAccept: false,
    });
    expect(onFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/pdf/i);
  });

  it("rejects a file over 10 MB", async () => {
    const onFile = vi.fn();
    render(<UploadDropzone onFile={onFile} />);
    await userEvent.upload(
      screen.getByTestId("resume-file-input"),
      pdf("big.pdf", 10 * 1024 * 1024 + 1),
    );
    expect(onFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/10 MB/i);
  });

  it("runs the same pick() guard on the drop path", () => {
    const onFile = vi.fn();
    render(<UploadDropzone onFile={onFile} />);
    const zone = screen.getByRole("button");

    fireEvent.drop(zone, { dataTransfer: { files: [pdf("dropped.pdf")] } });
    expect(onFile).toHaveBeenCalledTimes(1);
    expect(onFile.mock.calls[0][0].name).toBe("dropped.pdf");

    fireEvent.drop(zone, { dataTransfer: { files: [txt()] } });
    expect(onFile).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent(/pdf/i);
  });

  it("is inert when disabled", async () => {
    const onFile = vi.fn();
    render(<UploadDropzone onFile={onFile} disabled />);
    const zone = screen.getByRole("button");
    expect(zone).toHaveAttribute("aria-disabled", "true");
    expect(zone).toHaveAttribute("tabindex", "-1");

    const openDialog = vi.spyOn(
      screen.getByTestId("resume-file-input"),
      "click",
    );
    await userEvent.click(zone);
    fireEvent.drop(zone, { dataTransfer: { files: [pdf()] } });
    expect(openDialog).not.toHaveBeenCalled();
    expect(onFile).not.toHaveBeenCalled();
  });
});
