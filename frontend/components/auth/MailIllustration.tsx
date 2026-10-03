export type MailState = "error" | "success" | "waiting" | "sent";

const TONE: Record<MailState, { badge: string; glow: string; spark: string }> = {
  error: { badge: "#ef4454", glow: "#fde3e6", spark: "#f4637b" },
  success: { badge: "#1f9d5b", glow: "#dcf3e6", spark: "#3fbf7f" },
  waiting: { badge: "#5a4ae3", glow: "#ebe8fd", spark: "#8b7cf6" },
  sent: { badge: "#5a4ae3", glow: "#ebe8fd", spark: "#8b7cf6" },
};

function Mark({ state }: { state: MailState }) {
  const white = { stroke: "#fff", strokeWidth: 4, strokeLinecap: "round" as const, fill: "none" };
  if (state === "error") {
    return (
      <>
        <path d="M93 57 L107 71" {...white} />
        <path d="M107 57 L93 71" {...white} />
      </>
    );
  }
  if (state === "success") return <path d="M92 64 L98 70 L109 58" {...white} strokeLinejoin="round" />;
  if (state === "sent") return <path d="M92 64 L108 57 L102 72 L99 66 Z" fill="#fff" stroke="#fff" strokeWidth={2} strokeLinejoin="round" />;
  return (
    <g fill="#fff" className="motion-safe:animate-pulse">
      <circle cx="93" cy="64" r="2.6" />
      <circle cx="100" cy="64" r="2.6" />
      <circle cx="107" cy="64" r="2.6" />
    </g>
  );
}

/**
 * An open envelope with a status badge (error, success, waiting, sent), for
 * the account pages. Decorative: the heading next to it says what happened.
 */
export function MailIllustration({ state, className }: { state: MailState; className?: string }) {
  const tone = TONE[state];
  const id = `mail-${state}`;
  return (
    <svg
      viewBox="0 0 200 170"
      className={className ?? "h-36 w-44"}
      aria-hidden="true"
      focusable="false"
      data-testid={`mail-${state}`}
    >
      <defs>
        <radialGradient id={`${id}-glow`} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor={tone.glow} stopOpacity="1" />
          <stop offset="1" stopColor={tone.glow} stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${id}-body`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#eceefe" />
          <stop offset="1" stopColor="#d7daf9" />
        </linearGradient>
      </defs>

      <circle cx="100" cy="82" r="78" fill={`url(#${id}-glow)`} />
      <ellipse cx="100" cy="156" rx="58" ry="6" fill="#5a4ae3" opacity="0.1" />

      {/* back of the envelope and its open flap */}
      <rect x="40" y="78" width="120" height="74" rx="10" fill={`url(#${id}-body)`} />
      <path d="M40 82 L100 38 L160 82 Z" fill="#cfd3f8" strokeLinejoin="round" />

      {/* the letter */}
      <rect x="60" y="34" width="80" height="84" rx="8" fill="#ffffff" stroke="#e3e5fb" />

      {/* front flaps */}
      <path d="M40 86 L100 122 L40 152 Z" fill="#dfe2fc" />
      <path d="M160 86 L100 122 L160 152 Z" fill="#d4d7fa" />
      <path d="M40 152 L100 112 L160 152 Z" fill="#e6e8fd" />

      {/* status badge */}
      <circle cx="100" cy="64" r="17" fill={tone.badge} />
      <Mark state={state} />

      {/* sparks */}
      <g stroke={tone.spark} strokeWidth="3.5" strokeLinecap="round">
        <path d="M34 60 L44 68" />
        <path d="M30 84 L42 83" />
        <path d="M160 40 L168 31" />
        <path d="M158 60 L171 60" />
      </g>
    </svg>
  );
}
