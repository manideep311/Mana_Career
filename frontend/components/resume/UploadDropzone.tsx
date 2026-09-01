"use client";

import { useRef, useState, type DragEvent, type KeyboardEvent } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/cn";

/** Mirrors the backend's `resume_max_bytes` (10 MB). */
const MAX_BYTES = 10 * 1024 * 1024;

/**
 * A keyboard-operable, drag-and-drop PDF picker.
 *
 * The card is a `role="button"` that opens a visually-hidden file input on
 * click, Enter or Space. Both the input's `onChange` and the drop handler run
 * the same `pick` check — PDF type and a 10 MB ceiling, mirroring the backend —
 * before handing a good file up via `onFile`. A bad file shows an inline
 * `role="alert"` message and is not passed on.
 */
export function UploadDropzone({
  onFile,
  disabled = false,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function pick(file: File | undefined) {
    if (!file) return;
    if (file.type !== "application/pdf") {
      setError("That file isn't a PDF. Please choose a PDF résumé.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("That PDF is over 10 MB. Please choose a smaller file.");
      return;
    }
    setError(null);
    onFile(file);
  }

  function openPicker() {
    if (disabled) return;
    inputRef.current?.click();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  function onDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (!disabled) setDragging(true);
  }

  function onDragLeave() {
    setDragging(false);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    pick(event.dataTransfer.files?.[0]);
  }

  return (
    <div className="flex flex-col gap-2">
      <Card
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled || undefined}
        onClick={openPicker}
        onKeyDown={onKeyDown}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center gap-2 border-dashed p-10 text-center outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
          !disabled && "cursor-pointer hover:bg-surface-sunk",
          dragging && !disabled && "border-accent bg-accent-soft",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        <p className="text-sm font-medium text-text">
          Drop your résumé here, or click to choose
        </p>
        <p className="text-sm text-text-muted">PDF, up to 10 MB</p>
        {/*
         * `accept` hints the OS picker (greys out non-PDFs on desktop, hints
         * capture on mobile) but is only a hint — the browser never applies it
         * to drag-and-drop or an "All Files" override, so `pick` stays the
         * single source of truth and a non-PDF gets the inline alert.
         */}
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          data-testid="resume-file-input"
          // Hidden from the a11y tree + tab order: this input is a descendant
          // of the Card's role="button", and an interactive descendant there
          // trips axe `nested-interactive`. Keyboard activation goes through the
          // Card's Enter/Space handler, which calls `.click()` on this input.
          aria-hidden="true"
          tabIndex={-1}
          className="sr-only"
          disabled={disabled}
          onChange={(event) => {
            pick(event.target.files?.[0]);
            // Let the user re-pick the same file after fixing an error.
            event.target.value = "";
          }}
        />
      </Card>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
