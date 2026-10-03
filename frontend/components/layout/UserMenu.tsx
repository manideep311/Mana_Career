"use client";

import { useCallback } from "react";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/providers/AuthProvider";

/** End the session and go to sign-in. Shared by the sidebar and the phone menu. */
export function useSignOut(): () => Promise<void> {
  const router = useRouter();
  const { logout } = useAuth();
  return useCallback(async () => {
    await logout();
    router.push("/login");
  }, [logout, router]);
}

/**
 * Footer of the sidebar: the signed-in email plus a "Sign out" action that
 * clears the session and sends the user back to `/login`.
 */
export function UserMenu() {
  const { user } = useAuth();
  const signOut = useSignOut();

  return (
    <div className="flex items-center gap-2 border-t border-border px-3 py-3">
      <span className="min-w-0 flex-1 truncate text-sm text-text-muted" title={user?.email}>
        {user?.email}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          void signOut();
        }}
      >
        Sign out
      </Button>
    </div>
  );
}
