import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import type { ApprovalPayloadSnapshot } from "@/lib/api/types";

export function ApprovalCard({
  snapshot,
  submitting,
  onApprove,
  onReject,
}: {
  snapshot: ApprovalPayloadSnapshot;
  submitting: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const { job, cover_letter, email } = snapshot;
  return (
    <Card>
      <CardBody className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold text-text">
            Review your application for {job.title}
          </h2>
          {job.company ? (
            <p className="text-sm text-text-muted">{job.company}</p>
          ) : null}
        </div>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Cover letter</h3>
          <p className="whitespace-pre-line rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-sm text-text">
            {cover_letter.content || "—"}
          </p>
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Email</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-text-muted">To</dt>
            <dd className="text-text">{email.to_email || "—"}</dd>
            <dt className="text-text-muted">Subject</dt>
            <dd className="text-text">{email.subject || "—"}</dd>
          </dl>
          <p className="whitespace-pre-line rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-sm text-text">
            {email.body || "—"}
          </p>
        </section>

        <p className="text-sm font-medium text-text-muted">
          Nothing will be sent until you approve it.
        </p>

        <div className="flex items-center gap-3">
          <Button loading={submitting} onClick={onApprove}>
            Approve &amp; send
          </Button>
          <Button variant="outline" disabled={submitting} onClick={onReject}>
            Don&apos;t send
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
