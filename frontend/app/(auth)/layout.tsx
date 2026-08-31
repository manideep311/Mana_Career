import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-10">
      <span className="text-lg font-semibold tracking-tight text-text">
        Mana Career
      </span>
      <Card className="w-full max-w-sm">{children}</Card>
    </main>
  );
}
