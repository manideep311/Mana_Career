"use client";

import { RouteError } from "@/components/common/RouteError";

export default function Error(props: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="px-6">
      <RouteError {...props} />
    </main>
  );
}
