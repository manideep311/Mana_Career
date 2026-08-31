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
