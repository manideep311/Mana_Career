import type { ReactNode } from "react";

import { ManaPanelDock } from "@/components/ai/ManaPanelDock";
import { DemoBanner } from "@/components/layout/DemoBanner";
import { VerifyEmailBanner } from "@/components/layout/VerifyEmailBanner";
import { MobileHeader } from "@/components/layout/MobileHeader";
import { MobileNav } from "@/components/layout/MobileNav";
import { Sidebar } from "@/components/layout/Sidebar";

/**
 * The authenticated app frame: a sidebar on the left (desktop); on phones a
 * top bar with the account menu (incl. sign out) and a bottom nav bar. The
 * bottom padding keeps that bar from covering the last of the content.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bg md:grid md:grid-cols-[15rem_1fr]">
      <MobileHeader />
      <Sidebar />
      <main className="mx-auto w-full max-w-3xl px-4 py-6 pb-24 md:py-10 md:pb-10">
        <DemoBanner />
        <VerifyEmailBanner />
        {children}
      </main>
      <MobileNav />
      <ManaPanelDock />
    </div>
  );
}
