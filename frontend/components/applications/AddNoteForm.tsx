"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/FormError";

// FormError takes a `message` prop (string | unknown), NOT children — see
// components/auth/LoginForm.tsx. Render <FormError message={errors.body?.message} />.

const schema = z.object({
  body: z.string().min(1, "Write a note first.").max(4000, "Keep it under 4000 characters."),
});
type Values = z.infer<typeof schema>;

export function AddNoteForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (body: string) => Promise<void>;
  submitting: boolean;
}) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  return (
    <form
      className="space-y-2"
      onSubmit={handleSubmit(async (v) => {
        await onSubmit(v.body);
        reset();
      })}
    >
      <textarea
        aria-label="New note"
        rows={3}
        className="w-full rounded-[var(--radius)] border border-border bg-surface p-2 text-sm text-text"
        placeholder="Add a note — a call, a follow-up, a thought…"
        {...register("body")}
      />
      <FormError message={errors.body?.message} />
      <Button type="submit" size="sm" loading={submitting}>
        Add note
      </Button>
    </form>
  );
}
