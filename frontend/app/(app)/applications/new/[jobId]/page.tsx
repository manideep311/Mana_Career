"use client";

import { useParams } from "next/navigation";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { PrepareApplicationBuilder } from "@/components/applications/PrepareApplicationBuilder";

export default function PrepareApplicationPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId ?? "";

  return (
    <RequireAuth>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-text">Prepare application</h1>
          <p className="text-sm text-text-muted">
            You review and approve everything before anything is sent.
          </p>
        </header>
        <PrepareApplicationBuilder jobId={jobId} />
      </div>
    </RequireAuth>
  );
}
