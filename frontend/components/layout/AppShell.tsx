import type { ReactNode } from "react";

import { MobileNav } from "@/components/layout/MobileNav";
import { Sidebar } from "@/components/layout/Sidebar";

/**
 * The authenticated app frame: a sidebar on the left (desktop), a centred
 * content column, and a bottom nav bar on mobile. `pb-20 md:pb-0` keeps the
 * bottom bar from covering the last of the content on small screens.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bg md:grid md:grid-cols-[15rem_1fr]">
      <Sidebar />
      <main className="mx-auto w-full max-w-3xl px-4 py-8 pb-20 md:py-10 md:pb-0">
        {children}
      </main>
      <MobileNav />
    </div>
  );
}
