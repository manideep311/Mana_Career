import { InsufficientInfoBlockView } from "@/components/ai/blocks/InsufficientInfoBlockView";
import { JobCardBlockView } from "@/components/ai/blocks/JobCardBlockView";
import { ResumeSuggestionBlockView } from "@/components/ai/blocks/ResumeSuggestionBlockView";
import { TextBlockView } from "@/components/ai/blocks/TextBlockView";
import type { ResponseBlock } from "@/lib/api/types";

/** Dispatches a `ResponseBlock` to its view; unknown/not-yet-built kinds get a muted line. */
export function BlockView({ block }: { block: ResponseBlock }) {
  switch (block.kind) {
    case "text":
      return <TextBlockView block={block} />;
    case "job_card":
      return <JobCardBlockView block={block} />;
    case "insufficient_info":
      return <InsufficientInfoBlockView block={block} />;
    case "resume_suggestion":
      return <ResumeSuggestionBlockView block={block} />;
    default:
      return (
        <p className="rounded-[var(--radius)] border border-border bg-surface-sunk p-3 text-xs text-text-subtle">
          {`This kind of result ("${block.kind}") is not available yet.`}
        </p>
      );
  }
}
