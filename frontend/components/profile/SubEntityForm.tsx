"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FormError } from "@/components/ui/FormError";
import { Input } from "@/components/ui/input";
import { applyProblemToForm } from "@/lib/api/form-errors";
import type { ItemOut, Section } from "@/lib/api/types";
import { csvToList, listToCsv } from "@/lib/forms";
import { qk } from "@/lib/query";
import { useAuth } from "@/providers/AuthProvider";

import { CONFIG, type FieldSpec } from "./subentity-config";

type FormValues = Record<string, string | boolean>;

function fieldSchema(spec: FieldSpec): z.ZodTypeAny {
  switch (spec.type) {
    case "checkbox":
      return z.boolean().optional();
    case "url":
      return z.string().url("Enter a valid URL.").or(z.literal("")).optional();
    case "chips":
    case "date":
      return z.string().optional();
    default:
      return spec.required
        ? z.string().min(1, `${spec.label} is required.`)
        : z.string().optional();
  }
}

function buildSchema(fields: FieldSpec[]) {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const f of fields) shape[f.name] = fieldSchema(f);
  return z.object(shape);
}

function toDefaults(fields: FieldSpec[], item?: ItemOut): FormValues {
  const out: FormValues = {};
  for (const f of fields) {
    const raw = item ? item[f.name] : undefined;
    if (f.type === "checkbox") out[f.name] = Boolean(raw);
    else if (f.type === "chips") out[f.name] = listToCsv(raw);
    else out[f.name] = raw === null || raw === undefined ? "" : String(raw);
  }
  return out;
}

/** One field's value, serialized for the API (chips → list, checkbox → bool). */
function serializeField(spec: FieldSpec, raw: string | boolean | undefined): unknown {
  if (spec.type === "chips") return csvToList(raw);
  if (spec.type === "checkbox") return Boolean(raw);
  const text = typeof raw === "string" ? raw.trim() : "";
  if (text === "" && (spec.type === "date" || spec.type === "url")) return null;
  return text;
}

/**
 * Generic add/edit form for one profile sub-entity, driven by `CONFIG[section]`.
 * On create it POSTs every non-empty field; on edit it PATCHes only the dirty
 * ones. Success invalidates the section list + the strength score, then calls
 * `onDone()`. A backend `validation_error` maps back onto the matching field.
 */
export function SubEntityForm({
  section,
  item,
  onDone,
}: {
  section: Section;
  item?: ItemOut;
  onDone: () => void;
}) {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const config = CONFIG[section];

  const schema = useMemo(() => buildSchema(config.fields), [config.fields]);
  const defaultValues = useMemo(
    () => toDefaults(config.fields, item),
    [config.fields, item],
  );

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting, dirtyFields },
  } = useForm<FormValues>({
    resolver: zodResolver(schema) as unknown as Resolver<FormValues>,
    defaultValues,
  });

  const errText = (name: string): string | undefined => {
    const message = errors[name]?.message;
    return typeof message === "string" ? message : undefined;
  };

  const onSubmit = handleSubmit(async (values) => {
    try {
      if (item) {
        const patch: Record<string, unknown> = {};
        for (const f of config.fields) {
          if (dirtyFields[f.name]) {
            patch[f.name] = serializeField(f, values[f.name]);
          }
        }
        await api.profile.items.update(section, item.id, patch);
      } else {
        const body: Record<string, unknown> = {};
        for (const f of config.fields) {
          const value = serializeField(f, values[f.name]);
          const skip =
            !f.required &&
            f.type !== "chips" &&
            f.type !== "checkbox" &&
            (value === "" || value === null);
          if (!skip) body[f.name] = value;
        }
        await api.profile.items.add(section, body);
      }
      void queryClient.invalidateQueries({ queryKey: qk.section(section) });
      void queryClient.invalidateQueries({ queryKey: qk.strength });
      onDone();
    } catch (err) {
      if (!applyProblemToForm(err, setError)) {
        setError("root", { message: "Something went wrong. Please try again." });
      }
    }
  });

  return (
    <form
      noValidate
      onSubmit={onSubmit}
      className="flex flex-col gap-4 border-t border-border pt-4"
    >
      <FormError message={errors.root?.message} />

      {config.fields.map((f) => {
        const fid = `${section}-${item?.id ?? "new"}-${f.name}`;
        const error = errText(f.name);

        if (f.type === "checkbox") {
          return (
            <label
              key={f.name}
              htmlFor={fid}
              className="flex items-center gap-2 text-sm text-text"
            >
              <input id={fid} type="checkbox" {...register(f.name)} />
              <span>{f.label}</span>
            </label>
          );
        }

        if (f.type === "textarea") {
          return (
            <Field key={f.name} id={fid} label={f.label} error={error}>
              <textarea
                id={fid}
                rows={3}
                aria-invalid={error ? true : undefined}
                className="w-full rounded-[var(--radius)] border border-border bg-surface p-3 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] aria-[invalid=true]:border-danger"
                {...register(f.name)}
              />
            </Field>
          );
        }

        const inputType =
          f.type === "date" ? "date" : f.type === "url" ? "url" : "text";

        return (
          <Field
            key={f.name}
            id={fid}
            label={f.label}
            hint={f.type === "chips" ? "Comma-separated." : undefined}
            error={error}
          >
            <Input
              id={fid}
              type={inputType}
              aria-invalid={error ? true : undefined}
              {...register(f.name)}
            />
          </Field>
        );
      })}

      <div className="flex gap-3">
        <Button type="submit" loading={isSubmitting}>
          {item ? "Save" : "Add"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
