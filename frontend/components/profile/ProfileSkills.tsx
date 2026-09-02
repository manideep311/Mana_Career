"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import type { ProfileSkill } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

/**
 * The taxonomy categories in the order they should appear on the profile, each
 * with a human-readable heading. Any category the API returns that is not in
 * this list is shown last, under its raw name.
 */
const CATEGORY_ORDER: { key: string; label: string }[] = [
  { key: "language", label: "Languages" },
  { key: "ml_framework", label: "ML frameworks" },
  { key: "ml_technique", label: "ML techniques" },
  { key: "data", label: "Data" },
  { key: "cloud", label: "Cloud" },
  { key: "devops", label: "DevOps" },
  { key: "backend", label: "Backend" },
  { key: "frontend", label: "Frontend" },
  { key: "database", label: "Databases" },
  { key: "tooling", label: "Tooling" },
  { key: "practice", label: "Practices" },
];

const CATEGORY_META = new Map<string, { label: string; index: number }>(
  CATEGORY_ORDER.map(
    ({ key, label }, index): [string, { label: string; index: number }] => [
      key,
      { label, index },
    ],
  ),
);

type SkillGroup = { key: string; label: string; skills: ProfileSkill[] };

/**
 * Buckets a flat skill list by `category`, keeping `CATEGORY_ORDER` first and
 * any unknown category last (alphabetical by raw name). Incoming order within a
 * category is preserved — the API already sorts those by label.
 */
function groupByCategory(skills: ProfileSkill[]): SkillGroup[] {
  const buckets = new Map<string, ProfileSkill[]>();
  for (const skill of skills) {
    const bucket = buckets.get(skill.category);
    if (bucket) bucket.push(skill);
    else buckets.set(skill.category, [skill]);
  }

  return [...buckets.entries()]
    .map(([key, grouped]) => {
      const meta = CATEGORY_META.get(key);
      return {
        key,
        label: meta?.label ?? key,
        order: meta?.index ?? Number.MAX_SAFE_INTEGER,
        skills: grouped,
      };
    })
    .sort((a, b) => a.order - b.order || a.key.localeCompare(b.key))
    .map(({ key, label, skills: grouped }) => ({ key, label, skills: grouped }));
}

/**
 * The Skills section of `/profile`: the taxonomy-mapped skills from
 * `GET /api/v1/profile/skills`, grouped by category, with a button that kicks
 * off a fresh rebuild from the résumé via `POST /api/v1/profile/rebuild`.
 */
export function ProfileSkills() {
  const { api } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const skillsQuery = useQuery({
    queryKey: qk.skills,
    queryFn: () => api.profile.skills(),
  });

  const rebuildMut = useMutation({
    mutationFn: () => api.profile.rebuild(),
    onSuccess: () => {
      toast({ title: "Rebuilding your skills — check back in a moment." });
      void queryClient.invalidateQueries({ queryKey: qk.skills });
      void queryClient.invalidateQueries({ queryKey: qk.strength });
    },
    onError: () =>
      toast({ title: "Couldn't start a rebuild.", variant: "danger" }),
  });

  if (skillsQuery.isPending) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (skillsQuery.isError || !skillsQuery.data) {
    return (
      <p className="text-sm text-text-muted">
        We couldn&apos;t load your skills right now.
      </p>
    );
  }

  const skills = skillsQuery.data;

  if (skills.length === 0) {
    return (
      <p className="text-sm text-text-muted">
        No skills mapped yet — upload a résumé and we&apos;ll pull them in.
      </p>
    );
  }

  const groups = groupByCategory(skills);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-text-muted">
          Pulled from your profile and mapped to a shared skill taxonomy.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={rebuildMut.isPending}
          onClick={() => rebuildMut.mutate()}
        >
          Rebuild from résumé
        </Button>
      </div>

      <div className="flex flex-col gap-4">
        {groups.map((group) => (
          <section key={group.key} className="flex flex-col gap-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-text-muted">
              {group.label}
            </h3>
            <ul className="flex flex-wrap gap-2">
              {group.skills.map((skill) => (
                <li
                  key={skill.slug}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-sm"
                >
                  <span className="font-medium text-text">{skill.label}</span>
                  {skill.proficiency ? (
                    <span className="rounded-full bg-surface-sunk px-1.5 py-0.5 text-xs font-medium text-text-muted">
                      {skill.proficiency}
                    </span>
                  ) : null}
                  {skill.evidence.length > 0 ? (
                    <span className="text-xs text-text-muted">
                      {skill.evidence.length} mention
                      {skill.evidence.length === 1 ? "" : "s"}
                    </span>
                  ) : null}
                  {skill.source === "resume_extraction" ? (
                    <span className="text-xs text-text-muted">
                      from your résumé
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
