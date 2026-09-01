"use client";

import { useEffect, useRef } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";

import {
  ReviewSection,
  type ReviewSectionField,
} from "@/components/resume/ReviewSection";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { FormError } from "@/components/ui/FormError";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { applyProblemToForm } from "@/lib/api/form-errors";
import type { ResumeExtraction } from "@/lib/api/types";
import {
  reviewSchema,
  toExtraction,
  toFormValues,
  type ReviewFormValues,
} from "@/lib/resume/extraction-form";

/**
 * Shown under the fields the backend's `confirm_profile` merge does NOT apply
 * (`full_name`, `email`, `skills`, every `*_date`) — they stay visible so the
 * user can see what was extracted, but editing them here wouldn't stick.
 */
const NOT_MERGED_HINT = "Saved with your résumé — Mana uses this from a later step.";

const EXPERIENCE_FIELDS: ReviewSectionField[] = [
  { name: "company", label: "Company" },
  { name: "title", label: "Title" },
  { name: "employment_type", label: "Employment type" },
  // "City" (not "Location") so the page has exactly one "location"-labelled
  // control — the scalar one — which the review test types into.
  { name: "location", label: "City" },
  { name: "start_date", label: "Start", readOnly: true, hint: NOT_MERGED_HINT },
  { name: "end_date", label: "End", readOnly: true, hint: NOT_MERGED_HINT },
  { name: "highlights", label: "Highlights (one per line)", multiline: true },
  { name: "tech", label: "Tech (comma-separated)" },
  { name: "description", label: "Description" },
];

const EDUCATION_FIELDS: ReviewSectionField[] = [
  { name: "institution", label: "Institution" },
  { name: "degree", label: "Degree" },
  { name: "field", label: "Field" },
  { name: "start_date", label: "Start", readOnly: true, hint: NOT_MERGED_HINT },
  { name: "end_date", label: "End", readOnly: true, hint: NOT_MERGED_HINT },
  { name: "grade", label: "Grade" },
];

const PROJECT_FIELDS: ReviewSectionField[] = [
  { name: "name", label: "Name" },
  { name: "url", label: "URL" },
  { name: "highlights", label: "Highlights (one per line)", multiline: true },
  { name: "tech", label: "Tech (comma-separated)" },
  { name: "start_date", label: "Start", readOnly: true, hint: NOT_MERGED_HINT },
  { name: "end_date", label: "End", readOnly: true, hint: NOT_MERGED_HINT },
  { name: "description", label: "Description" },
];

const CERTIFICATION_FIELDS: ReviewSectionField[] = [
  { name: "name", label: "Name" },
  { name: "issuer", label: "Issuer" },
  { name: "credential_id", label: "Credential ID" },
  { name: "url", label: "URL" },
];

/**
 * The résumé extraction review form. Seeds every field from `extraction`
 * (`toFormValues`), lets the user lightly correct the editable scalars, list
 * fields, and the four `useFieldArray` sections (rows can only be removed here —
 * adding lives in `/profile`), then on submit hands the rebuilt
 * `ResumeExtraction` (`toExtraction`) to `onConfirm`, which POSTs it to
 * `/confirm-profile`.
 *
 * `full_name` / `email` / `skills` / every `*_date` are shown read-only: Phase
 * 2a's `confirm_profile` doesn't merge them, so an inline "edit" would be lost.
 * They still ride to the backend unchanged in the payload.
 *
 * A thrown `ProblemError` is mapped onto the fields / a root banner via
 * `applyProblemToForm`; anything else shows a generic root message.
 */
export function ExtractionReview({
  extraction,
  onConfirm,
  confirming = false,
}: {
  extraction: ResumeExtraction;
  onConfirm: (e: ResumeExtraction) => Promise<void>;
  confirming?: boolean;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  // Pull focus to the form heading on mount so a keyboard user who just
  // finished the upload isn't dropped on <body> with no cue the form appeared.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  const {
    control,
    register,
    getFieldState,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ReviewFormValues>({
    resolver: zodResolver(reviewSchema),
    defaultValues: toFormValues(extraction),
  });

  const onSubmit = handleSubmit(async (values) => {
    try {
      await onConfirm(toExtraction(values));
    } catch (err) {
      if (!applyProblemToForm(err, setError)) {
        setError("root", { message: "Something went wrong. Try again." });
      }
    }
  });

  const busy = confirming || isSubmitting;

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-col gap-6">
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="text-lg font-semibold text-text outline-none"
      >
        Review what we found
      </h2>

      <FormError message={errors.root?.message} />

      <Card>
        <CardHeader>
          <CardTitle>Basics</CardTitle>
        </CardHeader>
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <Field
            id="full_name"
            label="Full name"
            hint={NOT_MERGED_HINT}
            error={errors.full_name?.message}
          >
            <Input
              id="full_name"
              readOnly
              autoComplete="name"
              aria-invalid={errors.full_name ? true : undefined}
              {...register("full_name")}
            />
          </Field>

          <Field
            id="email"
            label="Email"
            hint={NOT_MERGED_HINT}
            error={errors.email?.message}
          >
            <Input
              id="email"
              type="email"
              readOnly
              autoComplete="email"
              aria-invalid={errors.email ? true : undefined}
              {...register("email")}
            />
          </Field>

          <Field id="location" label="Location" error={errors.location?.message}>
            <Input
              id="location"
              autoComplete="address-level2"
              aria-invalid={errors.location ? true : undefined}
              {...register("location")}
            />
          </Field>

          <Field id="github_url" label="GitHub URL" error={errors.github_url?.message}>
            <Input
              id="github_url"
              inputMode="url"
              aria-invalid={errors.github_url ? true : undefined}
              {...register("github_url")}
            />
          </Field>

          <Field
            id="linkedin_url"
            label="LinkedIn URL"
            error={errors.linkedin_url?.message}
          >
            <Input
              id="linkedin_url"
              inputMode="url"
              aria-invalid={errors.linkedin_url ? true : undefined}
              {...register("linkedin_url")}
            />
          </Field>

          <Field
            id="portfolio_url"
            label="Portfolio URL"
            error={errors.portfolio_url?.message}
          >
            <Input
              id="portfolio_url"
              inputMode="url"
              aria-invalid={errors.portfolio_url ? true : undefined}
              {...register("portfolio_url")}
            />
          </Field>

          <div className="sm:col-span-2">
            <Controller
              control={control}
              name="summary"
              render={({ field, fieldState }) => (
                <Field
                  id="summary"
                  label="Summary"
                  error={fieldState.error?.message}
                >
                  <Textarea
                    id="summary"
                    rows={4}
                    aria-invalid={fieldState.error ? true : undefined}
                    {...field}
                    value={field.value ?? ""}
                  />
                </Field>
              )}
            />
          </div>

          <div className="sm:col-span-2">
            <Field
              id="skills"
              label="Skills"
              hint={NOT_MERGED_HINT}
              error={errors.skills?.message}
            >
              <Input
                id="skills"
                readOnly
                aria-invalid={errors.skills ? true : undefined}
                {...register("skills")}
              />
            </Field>
          </div>
        </CardBody>
      </Card>

      <ReviewSection
        title="Experience"
        rowTestId="experience-row"
        rowLabel="experience"
        name="experiences"
        fields={EXPERIENCE_FIELDS}
        control={control}
        register={register}
        getFieldState={getFieldState}
      />
      <ReviewSection
        title="Education"
        rowTestId="education-row"
        rowLabel="education entry"
        name="education"
        fields={EDUCATION_FIELDS}
        control={control}
        register={register}
        getFieldState={getFieldState}
      />
      <ReviewSection
        title="Projects"
        rowTestId="project-row"
        rowLabel="project"
        name="projects"
        fields={PROJECT_FIELDS}
        control={control}
        register={register}
        getFieldState={getFieldState}
      />
      <ReviewSection
        title="Certifications"
        rowTestId="certification-row"
        rowLabel="certification"
        name="certifications"
        fields={CERTIFICATION_FIELDS}
        control={control}
        register={register}
        getFieldState={getFieldState}
      />

      <div>
        <Button type="submit" disabled={busy} loading={busy}>
          {confirming ? "Building…" : "Confirm & build my profile"}
        </Button>
      </div>
    </form>
  );
}
