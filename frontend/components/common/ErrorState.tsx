"use client";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";

/**
 * A small card for a failed data load. Pass `onRetry` to offer a "Try again"
 * button; omit it for a terminal message.
 */
export function ErrorState({
  title = "Something went wrong",
  onRetry,
}: {
  title?: string;
  onRetry?: () => void;
}) {
  return (
    <Card role="alert" className="mx-auto max-w-md text-center">
      <CardBody className="flex flex-col items-center gap-3">
        <p className="text-sm font-semibold text-text">{title}</p>
        <p className="text-sm text-text-muted">
          We could not load this right now. Please try again in a moment.
        </p>
        {onRetry ? (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
      </CardBody>
    </Card>
  );
}
