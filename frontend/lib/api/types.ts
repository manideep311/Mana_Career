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

export interface Strength {
  score: number;
  completeness: Record<string, boolean>;
  missing: string[];
}

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
