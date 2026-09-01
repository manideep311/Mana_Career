/**
 * Form model for the résumé extraction review screen.
 *
 * The LLM produces a `ResumeExtraction`; the user reviews it in
 * `<ExtractionReview>` and lightly corrects it before confirming. react-hook-form
 * wants a flat, all-string shape, so:
 *
 * - every scalar is a plain `string` (empty, never `null`/`undefined`);
 * - `skills` and per-row `tech` are short tokens — edited as a single
 *   comma-separated `string` and split back on the way out;
 * - per-row `highlights` are LLM-extracted prose bullets that routinely contain
 *   commas, so they are edited as newline-delimited text (one bullet per line)
 *   and split on `\n` — never CSV, which would shred a bullet on every comma;
 * - the four sections are arrays of row objects driven by `useFieldArray`.
 *
 * `toFormValues` seeds the form from an extraction; `toExtraction` turns the
 * edited values back into a `ResumeExtraction` for `POST /confirm-profile`
 * (empty scalars collapse to `undefined`; arrays are kept even when empty).
 */
import { z } from "zod";

import type {
  ExtractedCertification,
  ExtractedEducation,
  ExtractedExperience,
  ExtractedProject,
  ResumeExtraction,
} from "@/lib/api/types";
import { csvToList, listToCsv } from "@/lib/forms";

/**
 * Every text field is optional — the review form never blocks a confirm on a
 * missing value. Kept as a non-defaulting `.optional()` so the schema's input
 * and output types match (no transform), which keeps `useForm` / `useFieldArray`
 * typing straightforward. `toFormValues` still fills each one with `""`.
 */
const text = () => z.string().optional();

const experienceRowSchema = z.object({
  company: text(),
  title: text(),
  employment_type: text(),
  location: text(),
  start_date: text(),
  end_date: text(),
  highlights: text(),
  tech: text(),
  description: text(),
  // No control renders this — `useFieldArray` keeps unregistered row keys, so it
  // round-trips untouched. Backend `confirm_profile` merges `is_current` (and it
  // defaults to `false`), so dropping it would silently demote a current role.
  is_current: z.boolean().optional(),
});

const educationRowSchema = z.object({
  institution: text(),
  degree: text(),
  field: text(),
  start_date: text(),
  end_date: text(),
  grade: text(),
});

const projectRowSchema = z.object({
  name: text(),
  url: text(),
  highlights: text(),
  tech: text(),
  start_date: text(),
  end_date: text(),
  description: text(),
});

const certificationRowSchema = z.object({
  name: text(),
  issuer: text(),
  credential_id: text(),
  url: text(),
});

/**
 * The review-form schema. Scalars are all optional; the four sections are
 * always-present arrays (each row's own fields are optional) so `useFieldArray`
 * has a concrete array to bind to. The backend does the real validation on
 * `/confirm-profile`.
 */
export const reviewSchema = z.object({
  full_name: text(),
  email: text(),
  location: text(),
  github_url: text(),
  linkedin_url: text(),
  portfolio_url: text(),
  summary: text(),
  skills: text(),
  experiences: z.array(experienceRowSchema),
  education: z.array(educationRowSchema),
  projects: z.array(projectRowSchema),
  certifications: z.array(certificationRowSchema),
});

/**
 * The value shape react-hook-form holds, seeds from, and hands back on submit.
 * The schema has no transforms, so input and output are the same type.
 */
export type ReviewFormValues = z.output<typeof reviewSchema>;

type ExperienceRow = ReviewFormValues["experiences"][number];
type EducationRow = ReviewFormValues["education"][number];
type ProjectRow = ReviewFormValues["projects"][number];
type CertificationRow = ReviewFormValues["certifications"][number];

const str = (value: unknown): string =>
  value === null || value === undefined ? "" : String(value);

/** Trim, and collapse an empty/whitespace string to `undefined`. */
const clean = (value: unknown): string | undefined => {
  const trimmed = str(value).trim();
  return trimmed === "" ? undefined : trimmed;
};

/** One prose bullet per line -> a trimmed, non-empty list (commas survive). */
const linesToList = (value: unknown): string[] =>
  str(value)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

/** A list of prose bullets -> newline-delimited text for a `<Textarea>`. */
const listToLines = (value: unknown): string =>
  Array.isArray(value) ? value.map(String).join("\n") : "";

/* -------------------------------------------------------------------------- */
/*  extraction -> form                                                         */
/* -------------------------------------------------------------------------- */

function experienceToForm(x: ExtractedExperience): ExperienceRow {
  return {
    company: str(x.company),
    title: str(x.title),
    employment_type: str(x.employment_type),
    location: str(x.location),
    start_date: str(x.start_date),
    end_date: str(x.end_date),
    highlights: listToLines(x.highlights),
    tech: listToCsv(x.tech),
    description: str(x.description),
    is_current: x.is_current,
  };
}

function educationToForm(x: ExtractedEducation): EducationRow {
  return {
    institution: str(x.institution),
    degree: str(x.degree),
    field: str(x.field),
    start_date: str(x.start_date),
    end_date: str(x.end_date),
    grade: str(x.grade),
  };
}

function projectToForm(x: ExtractedProject): ProjectRow {
  return {
    name: str(x.name),
    url: str(x.url),
    highlights: listToLines(x.highlights),
    tech: listToCsv(x.tech),
    start_date: str(x.start_date),
    end_date: str(x.end_date),
    description: str(x.description),
  };
}

function certificationToForm(x: ExtractedCertification): CertificationRow {
  return {
    name: str(x.name),
    issuer: str(x.issuer),
    credential_id: str(x.credential_id),
    url: str(x.url),
  };
}

/** Seed the review form from an extraction. */
export function toFormValues(e: ResumeExtraction): ReviewFormValues {
  return {
    full_name: str(e.full_name),
    email: str(e.email),
    location: str(e.location),
    github_url: str(e.github_url),
    linkedin_url: str(e.linkedin_url),
    portfolio_url: str(e.portfolio_url),
    summary: str(e.summary),
    skills: listToCsv(e.skills),
    experiences: (e.experiences ?? []).map(experienceToForm),
    education: (e.education ?? []).map(educationToForm),
    projects: (e.projects ?? []).map(projectToForm),
    certifications: (e.certifications ?? []).map(certificationToForm),
  };
}

/* -------------------------------------------------------------------------- */
/*  form -> extraction                                                         */
/* -------------------------------------------------------------------------- */

function experienceFromForm(x: ExperienceRow): ExtractedExperience {
  return {
    company: str(x.company).trim(),
    title: str(x.title).trim(),
    employment_type: clean(x.employment_type),
    location: clean(x.location),
    start_date: clean(x.start_date),
    end_date: clean(x.end_date),
    description: clean(x.description),
    highlights: linesToList(x.highlights),
    tech: csvToList(x.tech),
    is_current: x.is_current,
  };
}

function educationFromForm(x: EducationRow): ExtractedEducation {
  return {
    institution: str(x.institution).trim(),
    degree: clean(x.degree),
    field: clean(x.field),
    start_date: clean(x.start_date),
    end_date: clean(x.end_date),
    grade: clean(x.grade),
  };
}

function projectFromForm(x: ProjectRow): ExtractedProject {
  return {
    name: str(x.name).trim(),
    url: clean(x.url),
    description: clean(x.description),
    highlights: linesToList(x.highlights),
    tech: csvToList(x.tech),
    start_date: clean(x.start_date),
    end_date: clean(x.end_date),
  };
}

function certificationFromForm(x: CertificationRow): ExtractedCertification {
  return {
    name: str(x.name).trim(),
    issuer: clean(x.issuer),
    credential_id: clean(x.credential_id),
    url: clean(x.url),
  };
}

/** Turn the edited form values back into a `ResumeExtraction`. */
export function toExtraction(v: ReviewFormValues): ResumeExtraction {
  return {
    full_name: clean(v.full_name),
    email: clean(v.email),
    location: clean(v.location),
    github_url: clean(v.github_url),
    linkedin_url: clean(v.linkedin_url),
    portfolio_url: clean(v.portfolio_url),
    summary: clean(v.summary),
    skills: csvToList(v.skills),
    experiences: (v.experiences ?? []).map(experienceFromForm),
    education: (v.education ?? []).map(educationFromForm),
    projects: (v.projects ?? []).map(projectFromForm),
    certifications: (v.certifications ?? []).map(certificationFromForm),
  };
}
