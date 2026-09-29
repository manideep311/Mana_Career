import { LaunchProgress } from "@/components/motion/LaunchProgress";
import type { ResumeStatus } from "@/lib/api/types";

/**
 * The visible stages of résumé processing, each mapped to the pipeline
 * statuses that make it the *active* stage. Copy says what is really happening
 * at that point in the pipeline; nothing advances on a timer.
 */
const STEPS: { label: string; statuses: readonly ResumeStatus[] }[] = [
  { label: "Reading your résumé…", statuses: ["uploaded", "parsing"] },
  { label: "Mapping your experience…", statuses: ["parsed", "extracting"] },
  { label: "Ready for you to check", statuses: ["extracted"] },
];

const LABELS = STEPS.map((s) => s.label);

/**
 * Maps a résumé status to its 0-based step index: `0` for `null`, `"failed"`
 * or an unrecognised status; `STEPS.length` once extracted (all done).
 */
function stageIndex(status: ResumeStatus | null): number {
  if (status === "extracted") return STEPS.length;
  if (status === null || status === "failed") return 0;
  const i = STEPS.findIndex((step) => step.statuses.includes(status));
  return i === -1 ? 0 : i;
}

/**
 * Résumé processing progress: the paper rocket plus the stage the pipeline is
 * actually in. `message` (from the server's event stream) is shown as a detail
 * line when it adds something beyond the stage label.
 *
 * Purely presentational: `status` / `message` come from `useResumeEvents`,
 * wired up by the `/resume` route.
 */
export function ResumeStepper({
  status,
  message,
}: {
  status: ResumeStatus | null;
  message: string | null;
}) {
  const current = stageIndex(status);
  const detail = message && !LABELS.includes(message) ? message : null;
  return <LaunchProgress stages={LABELS} current={current} detail={detail} />;
}
