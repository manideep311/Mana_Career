"use client";

import { InsightsView } from "@/components/insights/InsightsView";
import { RequireAuth } from "@/components/auth/RequireAuth";

export default function InsightsPage() {
  return (
    <RequireAuth>
      <div className="space-y-6">
        <header>
          <h1 className="font-display text-3xl text-text">Growth</h1>
          <p className="text-sm text-text-muted">
            Where you&apos;re strong, what to build next, and a roadmap to get there.
          </p>
        </header>
        <InsightsView />
      </div>
    </RequireAuth>
  );
}
