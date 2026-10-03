"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toaster";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * Shown only when this server really sends email and the address isn't
 * confirmed yet: sending approved applications waits on that confirmation.
 */
export function VerifyEmailBanner() {
  const { api, user } = useAuth();
  const { toast } = useToast();
  const meta = useQuery({
    queryKey: qk.meta,
    queryFn: () => api.meta.get(),
    staleTime: Infinity,
    retry: false,
  });
  const resend = useMutation({
    mutationFn: () => api.auth.resendVerification(),
    onSuccess: (res) => toast({ title: res.detail }),
    onError: () => toast({ title: "Couldn't send a new link. Try again soon.", variant: "danger" }),
  });

  const mode = meta.data?.email_delivery;
  if (!user || user.email_verified || !mode || mode === "console") return null;

  return (
    <div
      role="region"
      aria-label="Confirm your email"
      className="mb-6 flex flex-col gap-3 rounded-[var(--radius)] border border-border bg-accent-soft px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="flex items-start gap-2 text-text">
        <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
        <span>
          Confirm your email to send applications. We sent a link to{" "}
          <strong className="font-semibold">{user.email}</strong>.
        </span>
      </p>
      <Button
        size="sm"
        variant="outline"
        className="shrink-0 self-start sm:self-auto"
        loading={resend.isPending}
        onClick={() => resend.mutate()}
      >
        Resend link
      </Button>
    </div>
  );
}
