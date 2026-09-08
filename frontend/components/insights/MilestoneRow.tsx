"use client";

import type { Milestone, RoadmapMilestoneStatus } from "@/lib/api/types";

const STATUS_OPTIONS: { value: RoadmapMilestoneStatus; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
];

export function MilestoneRow({
  milestone,
  onStatusChange,
  busy,
}: {
  milestone: Milestone;
  onStatusChange: (s: RoadmapMilestoneStatus) => void;
  busy?: boolean;
}) {
  const meta = [
    milestone.est_hours != null ? `~${milestone.est_hours}h` : null,
    `${milestone.resource_ids.length} resource${milestone.resource_ids.length === 1 ? "" : "s"}`,
  ].filter(Boolean);
  return (
    <li className="flex flex-col gap-2 rounded-[var(--radius)] border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-text-subtle">
            {milestone.order_index + 1} · {milestone.skill_label}
          </p>
          <p className="text-sm font-medium text-text">{milestone.title}</p>
        </div>
        <select
          aria-label="Milestone status"
          className="rounded-full border border-border bg-surface px-2 py-1 text-xs text-text disabled:opacity-60"
          value={milestone.status}
          disabled={busy}
          onChange={(e) => onStatusChange(e.target.value as RoadmapMilestoneStatus)}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <p className="text-xs text-text-muted">{milestone.why_it_matters}</p>
      {meta.length > 0 ? (
        <p className="text-xs text-text-subtle">{meta.join(" · ")}</p>
      ) : null}
      {milestone.practice_project ? (
        <p className="rounded-[var(--radius)] bg-surface-sunk p-2 text-xs text-text-muted">
          <span className="font-medium text-text">Build:</span> {milestone.practice_project}
        </p>
      ) : null}
      {milestone.checkpoint ? (
        <p className="text-xs text-text-subtle">
          <span className="font-medium">Checkpoint:</span> {milestone.checkpoint}
        </p>
      ) : null}
      {milestone.status === "done" && milestone.completed_at ? (
        <p className="text-xs text-positive">
          Done · {new Date(milestone.completed_at).toLocaleDateString()}
        </p>
      ) : null}
    </li>
  );
}
