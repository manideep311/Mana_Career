"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { makeQueryClient } from "@/lib/query";

/**
 * Owns a single `QueryClient` for the browser session. The client is created
 * lazily in `useState` so it survives re-renders but is never shared between
 * requests on the server.
 */
export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => makeQueryClient());
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
