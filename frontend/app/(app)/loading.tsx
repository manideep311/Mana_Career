import { Skeleton } from "@/components/ui/skeleton";

// Route-change placeholder inside the app shell. Deliberately plain: the paper
// rocket is kept for real hand-offs (reading a résumé, building a roadmap).
export default function Loading() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-9 w-2/3" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-20 w-full" />
    </div>
  );
}
