import type { TimelineItem } from "@/lib/api/types";

// Only semantic tokens exist in this app (accent / positive / warning / danger /
// text-muted / border) — there is no `brand` or raw Tailwind palette. Do not
// invent `bg-violet-500` etc.
const DOT: Record<string, string> = {
  status_change: "bg-accent",
  note: "bg-text-muted",
  ai_action: "bg-accent",
  email_sent: "bg-positive",
  interview_scheduled: "bg-warning",
};

function detailEntries(detail: Record<string, unknown>): [string, string][] {
  return Object.entries(detail)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v)]);
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-text-muted">No history yet.</p>;
  }
  return (
    <ol className="space-y-4">
      {items.map((it, i) => {
        const entries = detailEntries(it.detail);
        return (
          <li key={`${it.at}-${i}`} className="flex gap-3">
            <span
              aria-hidden
              className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${DOT[it.kind] ?? "bg-border"}`}
            />
            <div className="min-w-0">
              <p className="text-sm text-text">{it.title}</p>
              <p className="text-xs text-text-muted">
                {new Date(it.at).toLocaleString()}
              </p>
              {entries.length > 0 ? (
                <dl className="mt-1 space-y-0.5 text-xs text-text-muted">
                  {entries.map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="font-medium capitalize">{k}</dt>
                      <dd className="min-w-0 break-words">{v}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
