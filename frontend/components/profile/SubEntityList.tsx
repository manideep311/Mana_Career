"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toaster";
import type { ItemOut, Section } from "@/lib/api/types";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

import { SubEntityForm } from "./SubEntityForm";
import { CONFIG } from "./subentity-config";

/**
 * Lists one profile sub-entity section (experiences / education / projects /
 * certifications) with add / edit / delete / move-up / move-down. Reorder is
 * optimistic: the cache is rewritten immediately, then the full id order is
 * POSTed; a failure rolls the cache back.
 */
export function SubEntityList({ section }: { section: Section }) {
  const { api } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const config = CONFIG[section];

  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: qk.section(section),
    queryFn: () => api.profile.items.list(section),
  });

  const items: ItemOut[] = data ?? [];

  const invalidateAll = (): void => {
    void queryClient.invalidateQueries({ queryKey: qk.section(section) });
    void queryClient.invalidateQueries({ queryKey: qk.strength });
  };

  const handleReorder = (index: number, direction: -1 | 1): void => {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;

    const next = items.slice();
    const moved = next[index];
    next[index] = next[target];
    next[target] = moved;

    const previous = items;
    queryClient.setQueryData(qk.section(section), next);
    void api.profile.items
      .reorder(
        section,
        next.map((item) => item.id),
      )
      .then(() => {
        void queryClient.invalidateQueries({ queryKey: qk.strength });
      })
      .catch(() => {
        queryClient.setQueryData(qk.section(section), previous);
        toast({ title: "We could not reorder those.", variant: "danger" });
      });
  };

  const handleDelete = (id: string): void => {
    const previous = items;
    queryClient.setQueryData(
      qk.section(section),
      items.filter((item) => item.id !== id),
    );
    void api.profile.items
      .remove(section, id)
      .then(() => {
        invalidateAll();
        toast({ title: `${config.singular} removed.` });
      })
      .catch(() => {
        queryClient.setQueryData(qk.section(section), previous);
        toast({ title: "We could not delete that.", variant: "danger" });
      });
  };

  if (isPending) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <p role="alert" className="text-sm text-danger">
        We could not load your {section}.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {items.length === 0 ? (
        <EmptyState
          title={`No ${section} yet.`}
          description="Add one to strengthen your profile."
        />
      ) : (
        items.map((item, index) => (
          <Card key={item.id}>
            <CardBody className="flex flex-col gap-3">
              {editingId === item.id ? (
                <SubEntityForm
                  section={section}
                  item={item}
                  onDone={() => setEditingId(null)}
                />
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="text-sm font-medium text-text">
                    {config.summary(item)}
                  </span>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={index === 0}
                      onClick={() => handleReorder(index, -1)}
                    >
                      Move up
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={index === items.length - 1}
                      onClick={() => handleReorder(index, 1)}
                    >
                      Move down
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingId(item.id)}
                    >
                      Edit
                    </Button>
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      onClick={() => handleDelete(item.id)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        ))
      )}

      {adding ? (
        <Card>
          <CardBody>
            <SubEntityForm section={section} onDone={() => setAdding(false)} />
          </CardBody>
        </Card>
      ) : (
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setAdding(true)}
          >
            {config.addLabel}
          </Button>
        </div>
      )}
    </div>
  );
}
