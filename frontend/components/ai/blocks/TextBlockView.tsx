import type { TextBlock } from "@/lib/api/types";

/** A plain-text assistant block. Paragraphs split on blank lines — no markdown engine yet. */
export function TextBlockView({ block }: { block: TextBlock }) {
  const paras = block.markdown.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  return (
    <div className="flex flex-col gap-2 text-sm text-text">
      {paras.map((p, i) => (
        <p key={i}>{p}</p>
      ))}
    </div>
  );
}
