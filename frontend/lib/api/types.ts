export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserOut;
}

export interface AccessResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export type StrengthDimension = { key: string; label: string; earned: number; max: number; hint: string; met: boolean };

export interface Strength {
  score: number;
  completeness: Record<string, boolean>;
  missing: string[];
  dimensions: StrengthDimension[];
}

export type ProfileSkill = { slug: string; label: string; category: string; proficiency: string | null; years: number | null; source: string; evidence: { kind: string; ref_id: string }[] };

export interface CareerProfile {
  id: string;
  user_id: string;
  headline?: string;
  bio?: string;
  location?: string;
  github_url?: string | null;
  linkedin_url?: string | null;
  portfolio_url?: string | null;
  preferred_roles?: string[] | null;
  preferred_locations?: string[] | null;
  work_modes?: string[] | null;
  expected_salary_min?: number | null;
  expected_salary_max?: number | null;
  salary_currency?: string | null;
  salary_period?: string | null;
  years_experience?: number | null;
  seniority?: string | null;
  career_goals?: string | null;
  profile_strength: number;
  completeness: Record<string, boolean>;
  created_at: string;
  updated_at: string;
}

export interface ItemOut {
  id: string;
  order_index: number;
  source: string;
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
}

export interface ProfileFull extends CareerProfile {
  experiences: ItemOut[];
  education: ItemOut[];
  projects: ItemOut[];
  certifications: ItemOut[];
}

export type Section = "experiences" | "education" | "projects" | "certifications";

export type ResumeStatus =
  | "uploaded"
  | "parsing"
  | "parsed"
  | "extracting"
  | "extracted"
  | "failed";

export interface ResumeOut {
  id: string;
  title: string | null;
  original_filename: string | null;
  content_type: string;
  size_bytes: number;
  page_count: number | null;
  status: ResumeStatus;
  parse_error: string | null;
  is_primary: boolean;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExtractedExperience {
  company: string;
  title: string;
  employment_type?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  location?: string | null;
  description?: string | null;
  highlights?: string[];
  tech?: string[];
}

export interface ExtractedEducation {
  institution: string;
  degree?: string | null;
  field?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  grade?: string | null;
}

export interface ExtractedProject {
  name: string;
  description?: string | null;
  url?: string | null;
  highlights?: string[];
  tech?: string[];
  start_date?: string | null;
  end_date?: string | null;
}

export interface ExtractedCertification {
  name: string;
  issuer?: string | null;
  issued_date?: string | null;
  expires_date?: string | null;
  credential_id?: string | null;
  url?: string | null;
}

export interface ResumeExtraction {
  full_name?: string | null;
  email?: string | null;
  location?: string | null;
  github_url?: string | null;
  linkedin_url?: string | null;
  portfolio_url?: string | null;
  summary?: string | null;
  skills?: string[];
  experiences?: ExtractedExperience[];
  education?: ExtractedEducation[];
  projects?: ExtractedProject[];
  certifications?: ExtractedCertification[];
}

export type JobSkillRef = { slug: string; label: string; weight: number };
export type JobStatus = "ingesting" | "ready" | "failed";
export type MatchBand = "strong" | "good" | "partial" | "weak";
export type MatchStatus = "scoring" | "ready" | "failed";
export type SkillGapStatus = "open" | "learning" | "closed";
export type MatchDimension =
  | "skill" | "experience" | "education" | "project" | "technology"
  | "location" | "role" | "seniority" | "salary" | "semantic";
export interface MatchComponent {
  dimension: MatchDimension; raw_score: number; weight: number; contribution: number;
  detail: Record<string, unknown>; evidence: Record<string, unknown>[];
}
export interface JobMatch {
  id: string; job_id: string; status: MatchStatus;
  score: number | null; band: MatchBand | null;
  dimension_scores: Record<string, number>;
  strengths: { dimension: string; raw_score: number; contribution: number }[];
  gaps: { dimension: string; raw_score: number; weight: number }[];
  explanation: string | null; computed_at: string | null;
}
export interface SkillGap {
  id: string; scope: "job" | "aggregate"; job_match_id: string | null;
  skill_slug: string; skill_label: string;
  severity: "critical" | "important" | "nice_to_have";
  frequency: number; rationale: string | null; status: SkillGapStatus;
}
export interface JobCard {
  id: string; title: string | null; company: string | null; location: string | null;
  work_mode: "remote" | "hybrid" | "onsite" | null;
  seniority: string | null; employment_type: string | null;
  salary_min: number | null; salary_max: number | null;
  salary_currency: string | null; salary_period: string | null;
  is_seed: boolean; status: JobStatus;
  posted_at: string | null; created_at: string;
  required_skills: JobSkillRef[];
  match_score?: number | null; match_band?: MatchBand | null; match_status?: MatchStatus | null;
}
export interface JobDetail extends JobCard {
  company_domain: string | null;
  experience_min_years: number | null; experience_max_years: number | null;
  description: string | null; responsibilities: string[];
  preferred_skills: JobSkillRef[]; raw_text: string;
}
export interface JobListResponse { items: JobCard[]; total: number; limit: number; offset: number }
export interface JobQuery {
  q?: string; work_mode?: string; seniority?: string; location?: string;
  employment_type?: string; salary_min?: number; skills?: string; sort?: string;
  limit?: number; offset?: number; has_match?: boolean;
}

/* -------------------------------------------------------------------------- */
/*  Eval (Phase 6, admin-only)                                                 */
/* -------------------------------------------------------------------------- */

export type EvalSuite = "retrieval" | "generation" | "matching";
export type EvalStatus = "running" | "passed" | "failed" | "error";

export interface EvalRun {
  id: string;
  suite: EvalSuite;
  dataset_version: string;
  git_sha: string;
  provider: string;
  model_ids: Record<string, unknown>;
  metrics: Record<string, number>;
  status: EvalStatus;
  started_at: string;
  ended_at: string | null;
}

export interface EvalResult {
  id: string;
  case_id: string;
  scores: Record<string, number>;
  passed: boolean;
  expected: Record<string, unknown>;
  actual: Record<string, unknown>;
}
