"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FormError } from "@/components/ui/FormError";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toaster";
import { applyProblemToForm } from "@/lib/api/form-errors";
import type { CareerProfile } from "@/lib/api/types";
import { csvToList, listToCsv } from "@/lib/forms";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

const WORK_MODES = ["remote", "hybrid", "onsite"] as const;
const SENIORITIES = ["junior", "mid", "senior", "staff", "lead", "principal"] as const;

/** Mirrors the backend `CareerProfileUpdate` schema. */
const schema = z.object({
  location: z.string().optional(),
  github_url: z.string().url().or(z.literal("")).optional(),
  linkedin_url: z.string().url().or(z.literal("")).optional(),
  portfolio_url: z.string().url().or(z.literal("")).optional(),
  preferred_roles: z.string().optional(),
  preferred_locations: z.string().optional(),
  work_modes: z.array(z.enum(WORK_MODES)).optional(),
  expected_salary_min: z.coerce.number().int().min(0).optional(),
  expected_salary_max: z.coerce.number().int().min(0).optional(),
  salary_currency: z.string().max(3).optional(),
  salary_period: z.enum(["year", "month", ""]).optional(),
  years_experience: z.coerce.number().min(0).max(70).optional(),
  seniority: z.enum(SENIORITIES).or(z.literal("")).optional(),
  career_goals: z.string().optional(),
});

type FormValues = z.input<typeof schema>;
type ParsedValues = z.output<typeof schema>;

const isTouched = (value: unknown): boolean =>
  Array.isArray(value) ? value.some(Boolean) : Boolean(value);

const oneOf = <T extends string>(opts: readonly T[], v: unknown): v is T =>
  typeof v === "string" && (opts as readonly string[]).includes(v);

export function ProfileScalarForm({ profile }: { profile: CareerProfile }) {
  const { api } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    setError,
    getValues,
    formState: { errors, isSubmitting, dirtyFields },
  } = useForm<FormValues, unknown, ParsedValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      location: profile.location ?? "",
      github_url: profile.github_url ?? "",
      linkedin_url: profile.linkedin_url ?? "",
      portfolio_url: profile.portfolio_url ?? "",
      preferred_roles: listToCsv(profile.preferred_roles),
      preferred_locations: listToCsv(profile.preferred_locations),
      work_modes: (profile.work_modes ?? []).filter(
        (m): m is (typeof WORK_MODES)[number] => oneOf(WORK_MODES, m),
      ),
      expected_salary_min: profile.expected_salary_min ?? "",
      expected_salary_max: profile.expected_salary_max ?? "",
      salary_currency: profile.salary_currency ?? "",
      salary_period: oneOf(["year", "month"] as const, profile.salary_period)
        ? profile.salary_period
        : "",
      years_experience: profile.years_experience ?? "",
      seniority: oneOf(SENIORITIES, profile.seniority) ? profile.seniority : "",
      career_goals: profile.career_goals ?? "",
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    const patch: Partial<CareerProfile> = {};

    for (const key of [
      "location",
      "github_url",
      "linkedin_url",
      "portfolio_url",
      "salary_currency",
      "career_goals",
    ] as const) {
      if (dirtyFields[key]) patch[key] = values[key] ?? "";
    }

    // `salary_period` / `seniority` are `Literal[...] | None` on the backend, so
    // an empty string 422s. A dirty-but-cleared select must send explicit null;
    // `model_dump(exclude_unset=True)` then clears the column.
    for (const key of ["salary_period", "seniority"] as const) {
      if (!dirtyFields[key]) continue;
      const value = values[key] ?? "";
      patch[key] = value === "" ? null : value;
    }

    for (const key of ["preferred_roles", "preferred_locations"] as const) {
      if (dirtyFields[key]) patch[key] = csvToList(values[key]);
    }

    if (isTouched(dirtyFields.work_modes)) patch.work_modes = values.work_modes ?? [];

    // Cleared number inputs coerce to 0 via `z.coerce.number()`; look at the raw
    // input instead and send null so the backend clears the field.
    for (const key of [
      "expected_salary_min",
      "expected_salary_max",
      "years_experience",
    ] as const) {
      if (!dirtyFields[key]) continue;
      const raw: unknown = getValues(key);
      const isBlank =
        raw === undefined ||
        raw === null ||
        (typeof raw === "string" && raw.trim() === "") ||
        (typeof raw === "number" && Number.isNaN(raw));
      patch[key] = isBlank ? null : values[key];
    }

    try {
      const updated = await api.profile.update(patch);
      queryClient.setQueryData(qk.profile, (prev) => ({
        ...(typeof prev === "object" && prev ? prev : {}),
        ...updated,
      }));
      void queryClient.invalidateQueries({ queryKey: qk.strength });
      toast({ title: "Profile saved" });
    } catch (err) {
      if (!applyProblemToForm(err, setError)) {
        setError("root", { message: "Something went wrong. Please try again." });
      }
    }
  });

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-col gap-5">
      <FormError message={errors.root?.message} />

      <Field id="location" label="Location" error={errors.location?.message}>
        <Input
          id="location"
          autoComplete="address-level2"
          aria-invalid={errors.location ? true : undefined}
          {...register("location")}
        />
      </Field>

      <div className="grid gap-5 sm:grid-cols-3">
        <Field id="github_url" label="GitHub URL" error={errors.github_url?.message}>
          <Input
            id="github_url"
            inputMode="url"
            aria-invalid={errors.github_url ? true : undefined}
            {...register("github_url")}
          />
        </Field>
        <Field id="linkedin_url" label="LinkedIn URL" error={errors.linkedin_url?.message}>
          <Input
            id="linkedin_url"
            inputMode="url"
            aria-invalid={errors.linkedin_url ? true : undefined}
            {...register("linkedin_url")}
          />
        </Field>
        <Field id="portfolio_url" label="Portfolio URL" error={errors.portfolio_url?.message}>
          <Input
            id="portfolio_url"
            inputMode="url"
            aria-invalid={errors.portfolio_url ? true : undefined}
            {...register("portfolio_url")}
          />
        </Field>
      </div>

      <Field
        id="preferred_roles"
        label="Preferred roles"
        hint="Comma-separated."
        error={errors.preferred_roles?.message}
      >
        <Input
          id="preferred_roles"
          aria-invalid={errors.preferred_roles ? true : undefined}
          {...register("preferred_roles")}
        />
      </Field>

      <Field
        id="preferred_locations"
        label="Preferred regions"
        hint="Comma-separated."
        error={errors.preferred_locations?.message}
      >
        <Input
          id="preferred_locations"
          aria-invalid={errors.preferred_locations ? true : undefined}
          {...register("preferred_locations")}
        />
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-text">Work modes</legend>
        <div className="flex flex-wrap gap-4">
          {WORK_MODES.map((mode) => (
            <label key={mode} className="flex items-center gap-2 text-sm text-text">
              <input
                type="checkbox"
                value={mode}
                aria-invalid={errors.work_modes ? true : undefined}
                {...register("work_modes")}
              />
              <span className="capitalize">{mode}</span>
            </label>
          ))}
        </div>
        {errors.work_modes?.message ? (
          <p role="alert" className="text-xs text-danger">
            {errors.work_modes.message}
          </p>
        ) : null}
      </fieldset>

      <div className="grid gap-5 sm:grid-cols-3">
        <Field
          id="expected_salary_min"
          label="Expected salary min"
          error={errors.expected_salary_min?.message}
        >
          <Input
            id="expected_salary_min"
            type="number"
            inputMode="numeric"
            aria-invalid={errors.expected_salary_min ? true : undefined}
            {...register("expected_salary_min")}
          />
        </Field>
        <Field
          id="expected_salary_max"
          label="Expected salary max"
          error={errors.expected_salary_max?.message}
        >
          <Input
            id="expected_salary_max"
            type="number"
            inputMode="numeric"
            aria-invalid={errors.expected_salary_max ? true : undefined}
            {...register("expected_salary_max")}
          />
        </Field>
        <Field
          id="salary_currency"
          label="Currency"
          hint="3-letter code."
          error={errors.salary_currency?.message}
        >
          <Input
            id="salary_currency"
            maxLength={3}
            aria-invalid={errors.salary_currency ? true : undefined}
            {...register("salary_currency")}
          />
        </Field>
      </div>

      <div className="grid gap-5 sm:grid-cols-3">
        <Field id="salary_period" label="Salary period" error={errors.salary_period?.message}>
          <select
            id="salary_period"
            aria-invalid={errors.salary_period ? true : undefined}
            className="h-10 w-full rounded-[var(--radius)] border border-border bg-surface px-3 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] aria-[invalid=true]:border-danger"
            {...register("salary_period")}
          >
            <option value="">Not set</option>
            <option value="year">Per year</option>
            <option value="month">Per month</option>
          </select>
        </Field>
        <Field
          id="years_experience"
          label="Years of experience"
          error={errors.years_experience?.message}
        >
          <Input
            id="years_experience"
            type="number"
            inputMode="numeric"
            aria-invalid={errors.years_experience ? true : undefined}
            {...register("years_experience")}
          />
        </Field>
        <Field id="seniority" label="Seniority" error={errors.seniority?.message}>
          <select
            id="seniority"
            aria-invalid={errors.seniority ? true : undefined}
            className="h-10 w-full rounded-[var(--radius)] border border-border bg-surface px-3 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] aria-[invalid=true]:border-danger"
            {...register("seniority")}
          >
            <option value="">Not set</option>
            {SENIORITIES.map((level) => (
              <option key={level} value={level} className="capitalize">
                {level}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <Field id="career_goals" label="Career goals" error={errors.career_goals?.message}>
        <textarea
          id="career_goals"
          rows={4}
          aria-invalid={errors.career_goals ? true : undefined}
          className="w-full rounded-[var(--radius)] border border-border bg-surface p-3 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] aria-[invalid=true]:border-danger"
          {...register("career_goals")}
        />
      </Field>

      <div>
        <Button type="submit" loading={isSubmitting}>
          Save changes
        </Button>
      </div>
    </form>
  );
}
