import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import type { NextStep } from "@/lib/api/types";

export function NextStepCard({ step }: { step: NextStep | null }) {
  if (step === null) {
    return (
      <Card>
        <CardBody className="p-4">
          <p className="text-sm text-text-muted">You&apos;re all caught up.</p>
        </CardBody>
      </Card>
    );
  }
  return (
    <Card>
      <CardBody className="flex flex-col gap-2 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-text-subtle">
          Recommended next step
        </p>
        <p className="text-base font-semibold text-text">{step.title}</p>
        <p className="text-sm text-text-muted">{step.reason}</p>
        {step.entity_type === "application" && step.entity_id ? (
          <Link
            href={`/applications/${step.entity_id}`}
            className={buttonVariants({ variant: "default" })}
          >
            Open the application
          </Link>
        ) : null}
      </CardBody>
    </Card>
  );
}
