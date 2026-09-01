"use client";

import {
  useFieldArray,
  type Control,
  type FieldArrayPath,
  type FieldPath,
  type FieldValues,
  type UseFormGetFieldState,
  type UseFormRegister,
} from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export interface ReviewSectionField {
  /** Row-relative field key, e.g. `"company"`. */
  name: string;
  label: string;
  /** Render a `<Textarea>` instead of `<Input>` (e.g. newline-delimited highlights). */
  multiline?: boolean;
  /**
   * Show the value but don't let the user edit it — used for fields the
   * backend's `confirm_profile` merge ignores (`*_date`), so an "edit" that
   * silently wouldn't stick is avoided.
   */
  readOnly?: boolean;
  /** Optional helper line under the control (wired to `aria-describedby`). */
  hint?: string;
}

/**
 * One `useFieldArray`-backed section of `<ExtractionReview>` (experiences,
 * education, projects, certifications).
 *
 * Renders a titled `<Card>` with one row per array entry; each row is a
 * `<fieldset data-testid={rowTestId}>` with a visually-hidden `<legend>` (so
 * screen-reader users can tell rows apart) holding a `<Field>`/`<Input>` (or
 * `<Textarea>` for `multiline` fields) per `fields` entry plus a **Remove**
 * button (`remove(index)`). There is no "add row" — new entries are added later
 * from `/profile`.
 *
 * `control` / `register` / `getFieldState` come from the parent `useForm`; `name`
 * is the array path (`"experiences"` …). `getFieldState` surfaces a per-row
 * field error (e.g. a backend `validation_error` mapped to
 * `experiences.0.company`) onto the matching `<Field>` / `<Input>`.
 */
export function ReviewSection<T extends FieldValues>({
  title,
  rowTestId,
  rowLabel,
  fields,
  control,
  register,
  getFieldState,
  name,
}: {
  title: string;
  rowTestId: string;
  /** Singular noun for one row, e.g. `"experience"` — used in the row legend and Remove label. */
  rowLabel: string;
  fields: ReviewSectionField[];
  control: Control<T>;
  register: UseFormRegister<T>;
  getFieldState: UseFormGetFieldState<T>;
  name: FieldArrayPath<T>;
}) {
  const { fields: rows, remove } = useFieldArray({ control, name });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-8">
        {rows.length === 0 ? (
          <p className="text-sm text-text-muted">
            None found. You can add entries later from your profile.
          </p>
        ) : (
          rows.map((row, index) => (
            <fieldset
              key={row.id}
              data-testid={rowTestId}
              className="flex min-w-0 flex-col gap-4 border-t border-border pt-6 first:border-0 first:pt-0"
            >
              <legend className="sr-only">
                {rowLabel} {index + 1}
              </legend>
              <div className="grid gap-4 sm:grid-cols-2">
                {fields.map((f) => {
                  const fid = `${name}-${index}-${f.name}`;
                  const path = `${name}.${index}.${f.name}` as FieldPath<T>;
                  const error = getFieldState(path).error?.message;
                  return (
                    <Field
                      key={f.name}
                      id={fid}
                      label={f.label}
                      hint={f.hint}
                      error={error}
                    >
                      {f.multiline ? (
                        <Textarea
                          id={fid}
                          rows={4}
                          readOnly={f.readOnly || undefined}
                          aria-invalid={error ? true : undefined}
                          {...register(path)}
                        />
                      ) : (
                        <Input
                          id={fid}
                          readOnly={f.readOnly || undefined}
                          aria-invalid={error ? true : undefined}
                          {...register(path)}
                        />
                      )}
                    </Field>
                  );
                })}
              </div>
              <div>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={`Remove ${rowLabel} ${index + 1}`}
                  onClick={() => remove(index)}
                >
                  Remove
                </Button>
              </div>
            </fieldset>
          ))
        )}
      </CardBody>
    </Card>
  );
}
