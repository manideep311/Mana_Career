"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/common/ErrorState";
import { StrengthMeter } from "@/components/common/StrengthMeter";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

function partOfDay(now: Date = new Date()): "morning" | "afternoon" | "evening" {
  const hour = now.getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

export default function DashboardPage() {
  const { user, api } = useAuth();
  const firstName = user?.full_name?.split(" ")[0] ?? "there";

  const strength = useQuery({
    queryKey: qk.strength,
    queryFn: () => api.profile.strength(),
  });

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-text">
          Good {partOfDay()}, {firstName} 👋
        </h1>
        <p className="text-sm text-text-muted">
          Here&apos;s where you stand in your career journey.
        </p>
      </header>

      {strength.isPending ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : strength.isError || !strength.data ? (
        <ErrorState onRetry={() => void strength.refetch()} />
      ) : (
        <Card>
          <CardBody className="flex flex-col gap-6">
            <StrengthMeter
              score={strength.data.score}
              missing={strength.data.missing}
            />
            {strength.data.score < 100 ? (
              <Link
                href="/profile"
                className={buttonVariants({ variant: "outline" })}
              >
                Complete your profile →
              </Link>
            ) : null}
          </CardBody>
        </Card>
      )}
    </div>
  );
}
