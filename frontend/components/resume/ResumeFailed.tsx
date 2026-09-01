"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";

/** What went wrong — pipeline failure vs. a dropped connection. */
export type ResumeFailedKind = "pipeline" | "connection";

const COPY: Record<ResumeFailedKind, { heading: string; fallback: string }> = {
  pipeline: {
    heading: "We couldn't process that résumé",
    fallback:
      "We hit a snag reading that résumé. It might be a scanned or image-only PDF. You can try again, or upload a different file.",
  },
  connection: {
    heading: "We lost the connection while processing your résumé.",
    fallback:
      "Your file is fine — this is a network hiccup. Try again in a moment.",
  },
};

/**
 * A terminal card for a failed résumé flow. `kind` picks the heading + fallback
 * body copy: `"pipeline"` (default) for a real parse failure, `"connection"`
 * for a dropped SSE stream (the file is probably fine). `message` is the
 * backend's `parse_error` / the stream error string, shown in place of the
 * fallback when present. "Try again" re-runs the pipeline via `onRetry` and
 * shows a disabled "Retrying…" state; "Upload a different file" resets the flow
 * via `onReupload`.
 *
 * Focus moves to the heading on mount so a keyboard user gets a cue the card
 * appeared (the card also carries `role="alert"`).
 */
export function ResumeFailed({
  message,
  kind = "pipeline",
  onRetry,
  onReupload,
  retrying = false,
}: {
  message: string | null;
  kind?: ResumeFailedKind;
  onRetry: () => void;
  onReupload: () => void;
  retrying?: boolean;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  const { heading, fallback } = COPY[kind];

  return (
    <Card role="alert" className="mx-auto max-w-md text-center">
      <CardBody className="flex flex-col items-center gap-3">
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="text-sm font-semibold text-text outline-none"
        >
          {heading}
        </h2>
        <p className="text-sm text-text-muted">{message ?? fallback}</p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Button onClick={onRetry} disabled={retrying}>
            {retrying ? "Retrying…" : "Try again"}
          </Button>
          <Button variant="ghost" onClick={onReupload}>
            Upload a different file
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
