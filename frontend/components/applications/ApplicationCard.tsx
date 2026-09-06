"use client";

import Link from "next/link";

import { StatusSelect } from "@/components/applications/StatusSelect";
import { Card, CardBody } from "@/components/ui/card";
import type { Application, ApplicationStatus } from "@/lib/api/types";

export function ApplicationCard({
  application,
  jobTitle,
  company,
  onStatusChange,
  busy,
}: {
  application: Application;
  jobTitle?: string;
  company?: string;
  onStatusChange: (s: ApplicationStatus) => void;
  busy?: boolean;
}) {
  const title = jobTitle ?? `Job ${application.job_id.slice(0, 8)}`;
  return (
    <Card className="text-sm">
      <CardBody className="space-y-2 p-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-text">{title}</p>
          {company ? <p className="truncate text-xs text-text-muted">{company}</p> : null}
        </div>
        <div className="flex items-center justify-between gap-2">
          {application.match_score != null ? (
            <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
              {Math.round(Number(application.match_score))}% match
            </span>
          ) : (
            <span />
          )}
          <StatusSelect
            value={application.status as ApplicationStatus}
            onChange={onStatusChange}
            disabled={busy}
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-text-muted">
            {new Date(application.last_status_change_at).toLocaleDateString()}
          </span>
          <Link
            href={`/applications/${application.id}`}
            className="text-xs font-medium text-accent hover:underline"
          >
            Open
          </Link>
        </div>
      </CardBody>
    </Card>
  );
}
