"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV, isActive } from "@/components/layout/nav-items";
import { cn } from "@/lib/cn";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Fixed bottom bar for small screens (`md:hidden`). Only the ready routes get a
 * tab; the not-ready items live in the sidebar until they ship.
 */
export function MobileNav() {
  const pathname = usePathname() ?? "";
  const { user } = useAuth();
  const items = NAV.filter(
    (item) => item.ready && (!item.adminOnly || user?.is_admin),
  );

  return (
    <nav
      aria-label="Primary mobile"
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface md:hidden"
    >
      {items.map((item) => {
        const Icon = item.icon;
        const active = isActive(pathname, item.href);

        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex flex-1 flex-col items-center gap-1 py-2 text-[11px] font-medium transition-colors",
              active ? "text-accent" : "text-text-muted",
            )}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
