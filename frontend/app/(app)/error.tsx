"use client";

import { RouteError } from "@/components/common/RouteError";

// Inside the app shell, so the sidebar and navigation stay usable.
export default function AppError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} />;
}
