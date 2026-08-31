"use client";

import { useEffect, type ReactNode } from "react";

import { useRouter } from "next/navigation";

import { Spinner } from "@/components/ui/spinner";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Client-side auth gate for the `(app)` route group.
 *
 * - `loading` — the bootstrap request is still in flight; show a centred spinner
 *   and nothing else.
 * - `anon` — no session; redirect to `/login` and render nothing.
 * - `authed` — render the protected tree.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "anon") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (status === "anon") {
    return null;
  }

  return <>{children}</>;
}
