"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { ApprovalPayloadSnapshot, EmailDeliveryMode } from "@/lib/api/types";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export interface Recipient {
  to_email: string;
  to_name?: string;
}

/** One sentence on where approving actually sends the email, per server mode. */
function deliveryNote(
  mode: EmailDeliveryMode | null | undefined,
  applicantEmail: string | null | undefined,
): string | null {
  if (mode === "redirect") {
    const inbox = applicantEmail ? ` (${applicantEmail})` : "";
    return `Demo delivery: the email goes to your own inbox${inbox} with a note naming this address, so you see exactly what the employer would receive.`;
  }
  if (mode === "live") {
    return "The email goes to this address with a copy to you. Replies come straight to your inbox.";
  }
  if (mode === "console") {
    return "This server doesn't send real email: approving records the application as sent without emailing anyone.";
  }
  return null;
}

export function ApprovalCard({
  snapshot,
  submitting,
  onApprove,
  onReject,
  delivery,
  applicantEmail,
  emailConfirmed = true,
}: {
  snapshot: ApprovalPayloadSnapshot;
  submitting: boolean;
  onApprove: (recipient: Recipient) => void;
  onReject: () => void;
  delivery?: EmailDeliveryMode | null;
  applicantEmail?: string | null;
  /** Real email is only sent from confirmed addresses. */
  emailConfirmed?: boolean;
}) {
  const { job, cover_letter, email } = snapshot;
  const [toEmail, setToEmail] = useState(email.to_email ?? "");
  const [toName, setToName] = useState(email.to_name ?? "");
  const [error, setError] = useState<string | undefined>();
  const note = deliveryNote(delivery, applicantEmail);
  const locked = !emailConfirmed && (delivery === "redirect" || delivery === "live");

  function approve(e: FormEvent) {
    e.preventDefault();
    const address = toEmail.trim();
    if (!EMAIL_RE.test(address)) {
      setError("Enter the hiring contact's email address.");
      return;
    }
    setError(undefined);
    const name = toName.trim();
    onApprove(name ? { to_email: address, to_name: name } : { to_email: address });
  }

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

        <form onSubmit={approve} noValidate className="flex flex-col gap-5">
          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold text-text">Email</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field id="approval-to-email" label="Send to" error={error}>
                <Input
                  id="approval-to-email"
                  type="email"
                  autoComplete="off"
                  placeholder="hiring@company.com"
                  value={toEmail}
                  onChange={(e) => setToEmail(e.target.value)}
                  aria-invalid={error ? true : undefined}
                  required
                />
              </Field>
              <Field id="approval-to-name" label="Contact name (optional)">
                <Input
                  id="approval-to-name"
                  autoComplete="off"
                  placeholder="Hiring Team"
                  value={toName}
                  onChange={(e) => setToName(e.target.value)}
                  maxLength={200}
                />
              </Field>
            </div>
            {note ? <p className="text-xs text-text-muted">{note}</p> : null}
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
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
          {locked ? (
            <p role="note" className="rounded-[var(--radius)] bg-warning-soft px-3 py-2 text-sm text-warning">
              Confirm your email address before sending: use the link we emailed you, or
              &ldquo;Resend link&rdquo; at the top of the page.
            </p>
          ) : null}

          <div className="flex items-center gap-3">
            <Button type="submit" loading={submitting} disabled={locked}>
              Approve &amp; send
            </Button>
            <Button type="button" variant="outline" disabled={submitting} onClick={onReject}>
              Don&apos;t send
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
