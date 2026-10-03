import type { ReactNode } from "react";

import Link from "next/link";

import { AuthArt } from "@/components/auth/AuthArt";

/**
 * Account pages: the artwork fills the screen, the wordmark sits over the sky,
 * and one half-transparent frosted card on the right carries the page. A
 * strong blur plus darker secondary text and links inside the card keep the
 * words readable over the picture. Each page supplies its
 * own heading (the card's h1).
 *
 * Column widths and gutters here are mirrored by AuthArt's right offsets.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="relative isolate min-h-screen overflow-hidden bg-[#1c1730]">
      <AuthArt />

      <div className="grid min-h-screen content-start gap-8 px-5 py-7 sm:px-10 sm:py-10 lg:grid-cols-[minmax(0,1fr)_28rem] lg:content-stretch lg:items-center lg:gap-12 lg:px-16 lg:py-12 xl:grid-cols-[minmax(0,1fr)_30rem] xl:px-20 2xl:grid-cols-[minmax(0,1fr)_34rem] 2xl:px-24">
        <div className="lg:self-start lg:pt-4">
          <Link href="/" aria-label="Mana Career home" className="inline-block font-display text-3xl">
            <span className="text-accent-2">Mana</span> <span className="text-accent">Career</span>
          </Link>
          <p className="mt-2 text-[11px] font-medium uppercase tracking-[0.42em] text-text/70">
            Careers shaped by you
          </p>
        </div>

        <div className="w-full max-w-md justify-self-center rounded-[28px] border border-white/60 bg-white/50 px-6 py-8 [--auth-link:#1a0d5c] [--text-muted:#1f1c2b] [--text-subtle:#1f1c2b] shadow-[0_40px_90px_-30px_rgba(10,6,40,0.65)] backdrop-blur-2xl sm:px-10 sm:py-11 lg:max-w-none">
          {children}
        </div>
      </div>
    </main>
  );
}
