"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV, isActive } from "@/components/layout/nav-items";
import { UserMenu } from "@/components/layout/UserMenu";
import { cn } from "@/lib/cn";

/**
 * Desktop-only left rail (`hidden md:flex`, `w-60`): the wordmark on top, the
 * primary nav in the middle, and the <UserMenu> pinned to the bottom.
 */
export function Sidebar() {
  const pathname = usePathname() ?? "";

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-surface md:flex">
      <Link
        href="/dashboard"
        className="px-5 py-5 text-lg font-semibold tracking-tight text-text"
      >
        Mana Career
      </Link>

      <nav aria-label="Primary" className="flex flex-1 flex-col gap-1 px-3">
        {NAV.map((item) => {
          const Icon = item.icon;

          if (!item.ready) {
            return (
              <span
                key={item.href}
                aria-disabled="true"
                className="flex items-center gap-3 rounded-[var(--radius)] px-3 py-2 text-sm text-text-subtle"
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="flex-1">{item.label}</span>
                <span className="rounded-full bg-surface-sunk px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-text-subtle">
                  Soon
                </span>
              </span>
            );
          }

          const active = isActive(pathname, item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-[var(--radius)] px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-accent-soft text-accent"
                  : "text-text-muted hover:bg-surface-sunk hover:text-text",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <UserMenu />
    </aside>
  );
}
