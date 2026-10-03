"use client";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { PageBanner } from "@/components/common/PageBanner";
import { InsightsView } from "@/components/insights/InsightsView";
import { PAGE_ART } from "@/lib/page-art";

export default function InsightsPage() {
  return (
    <RequireAuth>
      <div className="space-y-6">
        <PageBanner
          art={PAGE_ART.insights}
          title="Growth"
          description="Where you're strong, what to build next, and a roadmap to get there."
        />
        <InsightsView />
      </div>
    </RequireAuth>
  );
}
