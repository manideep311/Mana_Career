import type { InsufficientInfoBlock } from "@/lib/api/types";

/** The agent could not gather enough to answer — shows what is still missing. */
export function InsufficientInfoBlockView({ block }: { block: InsufficientInfoBlock }) {
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-sm">
      <p className="text-text">I need a bit more to go on here.</p>
      {block.missing.length > 0 ? (
        <ul className="list-disc pl-5 text-text-muted">
          {block.missing.map((m, i) => (
            <li key={i}>{m}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
