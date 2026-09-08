import { Card, CardBody } from "@/components/ui/card";
import type { SkillMention } from "@/lib/api/types";

/**
 * Two small read-only panels below the fold on the Insights page: skills showing
 * up across many of the user's saved roles, and project ideas surfaced from
 * their roadmaps. Pure — no hooks, no handlers.
 */
export function TrendingAndProjects({
  trending,
  projects,
}: {
  trending: SkillMention[];
  projects: string[];
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardBody className="flex flex-col gap-3 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-subtle">
            Trending skills
          </p>
          {trending.length === 0 ? (
            <p className="text-sm text-text-muted">Nothing trending yet.</p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {trending.map((t) => (
                <li
                  key={t.skill_slug}
                  className="inline-flex items-center gap-1 rounded-full bg-surface-sunk px-2 py-0.5 text-xs text-text-muted"
                >
                  <span className="font-medium text-text">{t.skill_label}</span>
                  {t.detail ? <span>{t.detail}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardBody className="flex flex-col gap-3 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-subtle">
            Suggested projects
          </p>
          {projects.length === 0 ? (
            <p className="text-sm text-text-muted">
              No project ideas yet — build a roadmap for some.
            </p>
          ) : (
            <ul className="list-disc pl-5 text-sm text-text-muted">
              {projects.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
