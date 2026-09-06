"use client";

import { ApplicationCard } from "@/components/applications/ApplicationCard";
import type { Application, ApplicationStatus } from "@/lib/api/types";

const COLUMNS: { status: ApplicationStatus; label: string; muted?: boolean }[] = [
  { status: "saved", label: "Saved" },
  { status: "applied", label: "Applied" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "rejected", label: "Rejected", muted: true },
  { status: "withdrawn", label: "Withdrawn", muted: true },
];

export function KanbanBoard({
  applications,
  jobs,
  onMove,
  movingId,
}: {
  applications: Application[];
  jobs: Record<string, { title: string; company: string }>;
  onMove: (id: string, status: ApplicationStatus) => void;
  movingId: string | null;
}) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-2">
      {COLUMNS.map((col) => {
        const cards = applications.filter((a) => a.status === col.status);
        return (
          <section
            key={col.status}
            aria-label={col.label}
            className="flex w-72 shrink-0 flex-col gap-2"
          >
            <header
              className={`flex items-center justify-between text-sm font-semibold ${
                col.muted ? "text-text-muted" : "text-text"
              }`}
            >
              <span>{col.label}</span>
              <span className="text-xs text-text-muted">{cards.length}</span>
            </header>
            {cards.length === 0 ? (
              <p className="rounded-[var(--radius)] border border-dashed border-border p-3 text-xs text-text-muted">
                Nothing here yet.
              </p>
            ) : (
              cards.map((a) => (
                <ApplicationCard
                  key={a.id}
                  application={a}
                  jobTitle={jobs[a.job_id]?.title}
                  company={jobs[a.job_id]?.company}
                  busy={movingId === a.id}
                  onStatusChange={(s) => onMove(a.id, s)}
                />
              ))
            )}
          </section>
        );
      })}
    </div>
  );
}
