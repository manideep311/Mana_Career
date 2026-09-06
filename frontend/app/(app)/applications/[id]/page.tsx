"use client";

import { useState } from "react";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { AddNoteForm } from "@/components/applications/AddNoteForm";
import { StatusSelect } from "@/components/applications/StatusSelect";
import { Timeline } from "@/components/applications/Timeline";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import type { ApplicationStatus, ApplicationTimeline } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

function DetailInner({ id }: { id: string }) {
  const { api } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [savingNote, setSavingNote] = useState(false);

  const appQuery = useQuery({ queryKey: qk.application(id), queryFn: () => api.applications.get(id) });
  const timelineQuery = useQuery({
    queryKey: qk.applicationTimeline(id),
    queryFn: () => api.applications.timeline(id),
  });
  const jobId = appQuery.data?.job_id ?? "";
  const jobQuery = useQuery({
    queryKey: qk.job(jobId),
    queryFn: () => api.jobs.get(jobId),
    enabled: jobId !== "",
  });

  const patch = useMutation({
    mutationFn: (status: ApplicationStatus) => api.applications.patch(id, { status }),
    onError: () => toast({ title: "Couldn't update the status.", variant: "danger" }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: qk.application(id) });
      void queryClient.invalidateQueries({ queryKey: qk.applicationTimeline(id) });
    },
  });

  async function addNote(body: string) {
    setSavingNote(true);
    const key = qk.applicationTimeline(id);
    const prev = queryClient.getQueryData<ApplicationTimeline>(key);
    queryClient.setQueryData<ApplicationTimeline>(key, {
      items: [
        { kind: "note", at: new Date().toISOString(), title: "Note added", detail: { body } },
        ...(prev?.items ?? []),
      ],
    });
    try {
      await api.applications.addNote(id, body);
    } catch {
      if (prev) queryClient.setQueryData(key, prev);
      toast({ title: "Couldn't save the note.", variant: "danger" });
    } finally {
      setSavingNote(false);
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }

  async function remove() {
    if (!window.confirm("Remove this application from your tracker?")) return;
    try {
      await api.applications.remove(id);
      void queryClient.invalidateQueries({ queryKey: qk.applications() });
      router.push("/applications");
    } catch {
      toast({ title: "Couldn't remove that application.", variant: "danger" });
    }
  }

  if (appQuery.isPending) return <Skeleton className="h-64 w-full" />;
  if (appQuery.isError) {
    return <ErrorState title="We couldn't load this application." onRetry={() => appQuery.refetch()} />;
  }

  const a = appQuery.data;
  const job = jobQuery.data;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Link href="/applications" className="text-xs text-text-muted hover:underline">
          ← All applications
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-text">
              {job?.title ?? `Job ${a.job_id.slice(0, 8)}`}
            </h1>
            {job?.company ? <p className="text-sm text-text-muted">{job.company}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            <StatusSelect
              value={a.status as ApplicationStatus}
              onChange={(s) => patch.mutate(s)}
              disabled={patch.isPending}
            />
            <Button variant="outline" size="sm" onClick={remove}>
              Remove
            </Button>
          </div>
        </div>
      </header>

      <Card>
        <CardBody className="flex flex-wrap gap-2 p-4 text-xs">
          {a.resume_version_id ? (
            <Link
              href={`/resume/versions/${a.resume_version_id}`}
              className="rounded-full border border-border px-2 py-1 text-accent hover:underline"
            >
              Tailored résumé
            </Link>
          ) : null}
          {a.cover_letter_id ? (
            <span className="rounded-full border border-border px-2 py-1 text-text-muted">
              Cover letter attached
            </span>
          ) : null}
          {a.application_email_id ? (
            <span className="rounded-full border border-border px-2 py-1 text-text-muted">
              Email drafted
            </span>
          ) : null}
          {!a.resume_version_id && !a.cover_letter_id && !a.application_email_id ? (
            <span className="text-text-muted">No documents yet.</span>
          ) : null}
        </CardBody>
      </Card>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-text">Add a note</h2>
        <AddNoteForm onSubmit={addNote} submitting={savingNote} />
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-text">History</h2>
        {timelineQuery.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <Timeline items={timelineQuery.data?.items ?? []} />
        )}
      </section>
    </div>
  );
}

export default function ApplicationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";
  return (
    <RequireAuth>
      <DetailInner id={id} />
    </RequireAuth>
  );
}
