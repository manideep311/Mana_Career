import type { ItemOut, Section } from "@/lib/api/types";

/** One editable field on a sub-entity form. */
export interface FieldSpec {
  name: string;
  label: string;
  type: "text" | "url" | "date" | "textarea" | "chips" | "checkbox";
  required?: boolean;
}

export interface SectionConfig {
  /** Human singular, e.g. "Experience". */
  singular: string;
  /** Label for the create button, e.g. "Add experience". */
  addLabel: string;
  fields: FieldSpec[];
  /** One-line label for a saved item, shown in the list. */
  summary: (item: ItemOut) => string;
}

/** Coerce an unknown item value to a display string (null/undefined → ""). */
const s = (v: unknown): string => (v === null || v === undefined ? "" : String(v));

/**
 * Field + copy config for every profile sub-entity list. Field names and shapes
 * mirror the Phase 1b backend schemas (`SUBENTITY_SCHEMAS` in
 * `backend/app/api/v1/schemas/profile.py`).
 */
export const CONFIG: Record<Section, SectionConfig> = {
  experiences: {
    singular: "Experience",
    addLabel: "Add experience",
    fields: [
      { name: "company", label: "Company", type: "text", required: true },
      { name: "title", label: "Title", type: "text", required: true },
      { name: "employment_type", label: "Employment type", type: "text" },
      { name: "start_date", label: "Start date", type: "date" },
      { name: "end_date", label: "End date", type: "date" },
      { name: "is_current", label: "I currently work here", type: "checkbox" },
      { name: "location", label: "Location", type: "text" },
      { name: "description", label: "Description", type: "textarea" },
      { name: "highlights", label: "Highlights", type: "chips" },
      { name: "tech", label: "Technologies", type: "chips" },
    ],
    summary: (i) => `${s(i.title)} · ${s(i.company)}`,
  },
  education: {
    singular: "Education",
    addLabel: "Add education",
    fields: [
      { name: "institution", label: "Institution", type: "text", required: true },
      { name: "degree", label: "Degree", type: "text" },
      { name: "field", label: "Field of study", type: "text" },
      { name: "start_date", label: "Start date", type: "date" },
      { name: "end_date", label: "End date", type: "date" },
      { name: "grade", label: "Grade", type: "text" },
    ],
    summary: (i) => `${s(i.degree) || "Studies"} · ${s(i.institution)}`,
  },
  projects: {
    singular: "Project",
    addLabel: "Add project",
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      { name: "description", label: "Description", type: "textarea" },
      { name: "url", label: "URL", type: "url" },
      { name: "start_date", label: "Start date", type: "date" },
      { name: "end_date", label: "End date", type: "date" },
      { name: "highlights", label: "Highlights", type: "chips" },
      { name: "tech", label: "Technologies", type: "chips" },
    ],
    summary: (i) => s(i.name),
  },
  certifications: {
    singular: "Certification",
    addLabel: "Add certification",
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      { name: "issuer", label: "Issuer", type: "text" },
      { name: "issued_date", label: "Issue date", type: "date" },
      { name: "expires_date", label: "Expiry date", type: "date" },
      { name: "credential_id", label: "Credential ID", type: "text" },
      { name: "url", label: "URL", type: "url" },
    ],
    summary: (i) => (i.issuer ? `${s(i.name)} · ${s(i.issuer)}` : s(i.name)),
  },
};
