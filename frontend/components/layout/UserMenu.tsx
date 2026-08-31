"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Footer of the sidebar: the signed-in email plus a "Sign out" action that
 * clears the session and sends the user back to `/login`.
 */
export function UserMenu() {
  const router = useRouter();
  const { user, logout } = useAuth();

  async function onSignOut() {
    await logout();
    router.push("/login");
  }

  return (
    <div className="flex items-center gap-2 border-t border-border px-3 py-3">
      <span className="min-w-0 flex-1 truncate text-sm text-text-muted" title={user?.email}>
        {user?.email}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          void onSignOut();
        }}
      >
        Sign out
      </Button>
    </div>
  );
}
