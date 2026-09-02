"use client";

import { useEffect, useState } from "react";

import { useRouter } from "next/navigation";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toaster";
import { useJobEvents } from "@/hooks/useJobEvents";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const schema = z.object({
  raw_text: z
    .string()
    .min(40, "Paste the full job description (at least 40 characters)."),
});

type FormValues = z.infer<typeof schema>;

/**
 * "Add a job" toggles an inline paste-a-JD panel. On submit the raw text is
 * POSTed (`api.jobs.create`); the returned id is handed to `useJobEvents`, and
 * the ingest pipeline's terminal status drives the outcome: `ready` invalidates
 * the jobs cache and routes to the new detail page, `failed` surfaces a toast.
 * Mirrors the résumé upload flow (mutation + SSE + navigate).
 */
export function AddJobDialog() {
  const { api } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [open, setOpen] = useState(false);
  const [newId, setNewId] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const createMut = useMutation({
    mutationFn: (raw_text: string) => api.jobs.create(raw_text),
    onSuccess: (res) => {
      toast({ title: "Ingesting the posting…" });
      setNewId(res.id);
    },
    onError: () =>
      toast({ title: "We couldn't add that posting.", variant: "danger" }),
  });

  const ev = useJobEvents(newId);

  useEffect(() => {
    if (newId === null) return;
    if (ev.status === "ready") {
      void queryClient.invalidateQueries({ queryKey: qk.jobs });
      router.push(`/jobs/${newId}`);
      setNewId(null);
      setOpen(false);
      reset();
    } else if (ev.status === "failed") {
      toast({ title: "We couldn't read that posting.", variant: "danger" });
      setNewId(null);
    }
  }, [ev.status, newId, queryClient, router, reset, toast]);

  const onSubmit = handleSubmit((values) => {
    createMut.mutate(values.raw_text);
  });

  return (
    <div className="flex w-full flex-col items-end gap-3 sm:w-96">
      <Button
        variant={open ? "ghost" : "default"}
        onClick={() => setOpen((prev) => !prev)}
      >
        {open ? "Cancel" : "Add a job"}
      </Button>

      {open ? (
        <form
          noValidate
          onSubmit={onSubmit}
          className="flex w-full flex-col gap-3 rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-1)]"
        >
          <label
            htmlFor="job-raw-text"
            className="text-sm font-medium text-text"
          >
            Paste a job description
          </label>
          <Textarea
            id="job-raw-text"
            rows={8}
            placeholder="Paste the full job posting here…"
            aria-invalid={errors.raw_text ? true : undefined}
            {...register("raw_text")}
          />
          {errors.raw_text ? (
            <p role="alert" className="text-sm text-danger">
              {errors.raw_text.message}
            </p>
          ) : null}
          <Button
            type="submit"
            loading={createMut.isPending}
            disabled={createMut.isPending}
          >
            Ingest
          </Button>
          {newId !== null ? (
            <p role="status" className="text-xs text-text-muted">
              {ev.message ?? "Reading the posting…"}
            </p>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}
