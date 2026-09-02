"use client";

import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/common/ErrorState";
import { StrengthMeter } from "@/components/common/StrengthMeter";
import { ProfileScalarForm } from "@/components/profile/ProfileScalarForm";
import { ProfileSkills } from "@/components/profile/ProfileSkills";
import { SubEntityList } from "@/components/profile/SubEntityList";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Section } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/** The four sub-entity lists, in display order, with their visible headings. */
const SECTIONS: { section: Section; heading: string }[] = [
  { section: "experiences", heading: "Work experience" },
  { section: "education", heading: "Education" },
  { section: "projects", heading: "Projects" },
  { section: "certifications", heading: "Certifications" },
];

/**
 * The whole career-profile editor: a calculated strength meter, the scalar
 * form, then the four reorderable sub-entity lists. The strength query loads
 * independently of the profile so a slow score never blocks editing.
 */
export default function ProfilePage() {
  const { api } = useAuth();

  const profileQuery = useQuery({
    queryKey: qk.profile,
    queryFn: () => api.profile.get(),
  });

  const strengthQuery = useQuery({
    queryKey: qk.strength,
    queryFn: () => api.profile.strength(),
  });

  if (profileQuery.isPending) {
    return (
      <div className="flex flex-col gap-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (profileQuery.isError || !profileQuery.data) {
    return <ErrorState onRetry={() => void profileQuery.refetch()} />;
  }

  const profile = profileQuery.data;

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-text">Your profile</h1>
        <p className="text-sm text-text-muted">
          Keep this current — it powers your matches and your application prep.
        </p>
      </header>

      <Card>
        <CardBody>
          {strengthQuery.isPending ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-3 w-full" />
            </div>
          ) : strengthQuery.isError || !strengthQuery.data ? (
            <p className="text-sm text-text-muted">
              We couldn&apos;t load your score right now.
            </p>
          ) : (
            <StrengthMeter
              score={strengthQuery.data.score}
              missing={strengthQuery.data.missing}
              dimensions={strengthQuery.data.dimensions}
            />
          )}
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <ProfileScalarForm profile={profile} />
        </CardBody>
      </Card>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-text">Skills</h2>
        <Card>
          <CardBody>
            <ProfileSkills />
          </CardBody>
        </Card>
      </section>

      {SECTIONS.map(({ section, heading }) => (
        <section key={section} className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-text">{heading}</h2>
          <SubEntityList section={section} />
        </section>
      ))}
    </div>
  );
}
