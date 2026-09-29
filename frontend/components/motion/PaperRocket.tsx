import { cn } from "@/lib/cn";

/**
 * A sheet of paper folds into a rocket, launches, and leaves a short trail.
 *
 * Decorative only (`aria-hidden`): the words next to it carry the meaning.
 * CSS/SVG, no JS timers; the loop lives in `app/globals.css` (`.paper-rocket`)
 * and holds still on the finished rocket under `prefers-reduced-motion`.
 * Reserve it for the few moments that are real hand-offs: reading a résumé,
 * building a roadmap, preparing a document.
 */
export function PaperRocket({
  size = 64,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      data-testid="paper-rocket"
      className={cn("paper-rocket shrink-0 overflow-visible text-accent", className)}
    >
      <rect
        className="pr-sheet"
        x="19"
        y="14"
        width="26"
        height="34"
        rx="2"
        fill="var(--surface)"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <line
        className="pr-crease"
        x1="19"
        y1="31"
        x2="45"
        y2="31"
        stroke="currentColor"
        strokeWidth="1"
      />
      <g transform="rotate(35 32 32)">
        <line
          className="pr-trail"
          x1="32"
          y1="26"
          x2="32"
          y2="46"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <g className="pr-rocket">
          <path
            d="M32 10 L42 42 L32 36 L22 42 Z"
            fill="var(--accent-soft)"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <path d="M32 10 L32 36" stroke="currentColor" strokeWidth="1" />
        </g>
      </g>
    </svg>
  );
}
