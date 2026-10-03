"use client";

import { useEffect, useId, useRef, useState } from "react";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Activity, Compass, LogOut, User } from "lucide-react";

import { useSignOut } from "@/components/layout/UserMenu";
import { cn } from "@/lib/cn";
import { useAuth } from "@/providers/AuthProvider";

function initials(name: string | undefined, email: string | undefined): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length > 0) return words.slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
  return (email ?? "?")[0]!.toUpperCase();
}

const LINKS = [
  { href: "/insights", label: "Growth", icon: Compass },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/profile", label: "Profile", icon: User },
];

/**
 * Phones only (`md:hidden`): the wordmark and an account menu with the pages
 * that don't fit in the bottom bar, and "Sign out" (the sidebar that holds it
 * on desktop is hidden here).
 */
export function MobileHeader() {
  const { user } = useAuth();
  const signOut = useSignOut();
  const pathname = usePathname() ?? "";
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on navigation.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>("[role='menuitem']")?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    function onPointer(e: PointerEvent) {
      const target = e.target as Node;
      if (!menuRef.current?.contains(target) && !buttonRef.current?.contains(target)) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  const item =
    "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-text hover:bg-surface-sunk focus-visible:bg-surface-sunk";

  return (
    <header className="sticky top-0 z-40 flex items-center justify-between border-b border-border bg-surface/95 px-4 py-3 backdrop-blur md:hidden">
      <Link href="/dashboard" className="font-display text-lg">
        <span className="text-accent">Mana</span> <span className="text-text">Career</span>
      </Link>

      <div className="relative">
        <button
          ref={buttonRef}
          type="button"
          aria-label="Account menu"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={menuId}
          onClick={() => setOpen((o) => !o)}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent"
        >
          {initials(user?.full_name, user?.email)}
        </button>

        {open ? (
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-label="Account"
            className="absolute right-0 top-12 w-64 rounded-2xl border border-border bg-surface p-2 shadow-[var(--shadow-2)] animate-rise"
          >
            <div className="border-b border-border px-3 pb-3 pt-2">
              <p className="truncate text-sm font-semibold text-text">{user?.full_name}</p>
              <p className="truncate text-xs text-text-muted">{user?.email}</p>
            </div>
            <div className="flex flex-col gap-0.5 py-1">
              {LINKS.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  role="menuitem"
                  aria-current={pathname.startsWith(href) ? "page" : undefined}
                  className={cn(item, pathname.startsWith(href) && "text-accent")}
                >
                  <Icon className="h-4 w-4 text-text-muted" aria-hidden />
                  {label}
                </Link>
              ))}
            </div>
            <div className="border-t border-border pt-1">
              <button
                type="button"
                role="menuitem"
                className={cn(item, "text-danger")}
                onClick={() => {
                  setOpen(false);
                  void signOut();
                }}
              >
                <LogOut className="h-4 w-4" aria-hidden />
                Sign out
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </header>
  );
}
