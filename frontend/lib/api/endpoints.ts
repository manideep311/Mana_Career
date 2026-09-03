import {
  AccessResponse,
  AuthResponse,
  CareerProfile,
  EvalResult,
  EvalRun,
  ExtractedExperience,
  ExtractedEducation,
  ExtractedProject,
  ExtractedCertification,
  ItemOut,
  JobCard,
  JobDetail,
  JobListResponse,
  JobMatch,
  JobQuery,
  JobStatus,
  MatchComponent,
  MatchStatus,
  ProfileFull,
  ProfileSkill,
  ResumeExtraction,
  ResumeOut,
  Section,
  SkillGap,
  SkillGapStatus,
  Strength,
  UserOut,
} from "@/lib/api/types";
import { Fetcher } from "@/lib/api/fetcher";

function json(method: string, body?: unknown) {
  return {
    method,
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  };
}

export function makeApi(f: Fetcher) {
  return {
    auth: {
      async register(body: { email: string; password: string; full_name: string }) {
        return f<AuthResponse>("/api/v1/auth/register", json("POST", body));
      },
      async login(body: { email: string; password: string }) {
        return f<AuthResponse>("/api/v1/auth/login", json("POST", body));
      },
      async refresh() {
        return f<AccessResponse>("/api/v1/auth/refresh", json("POST"));
      },
      async logout() {
        return f<void>("/api/v1/auth/logout", json("POST"));
      },
      async me() {
        return f<UserOut>("/api/v1/auth/me");
      },
      async changePassword(body: { old_password: string; new_password: string }) {
        return f<void>("/api/v1/auth/password/change", json("POST", body));
      },
    },
    profile: {
      async get() {
        return f<ProfileFull>("/api/v1/profile");
      },
      async update(patch: Partial<CareerProfile>) {
        return f<CareerProfile>("/api/v1/profile", {
          method: "PUT",
          body: JSON.stringify(patch),
          headers: { "Content-Type": "application/json" },
        });
      },
      async strength() {
        return f<Strength>("/api/v1/profile/strength");
      },
      async skills() {
        return f<ProfileSkill[]>("/api/v1/profile/skills");
      },
      async rebuild() {
        return f<void>("/api/v1/profile/rebuild", { method: "POST" });
      },
      items: {
        async list(section: Section) {
          return f<ItemOut[]>(`/api/v1/profile/${section}`);
        },
        async add(section: Section, body: Record<string, unknown>) {
          return f<ItemOut>(
            `/api/v1/profile/${section}`,
            json("POST", body),
          );
        },
        async update(section: Section, id: string, patch: Record<string, unknown>) {
          return f<ItemOut>(
            `/api/v1/profile/${section}/${id}`,
            {
              method: "PATCH",
              body: JSON.stringify(patch),
              headers: { "Content-Type": "application/json" },
            },
          );
        },
        async remove(section: Section, id: string) {
          return f<void>(`/api/v1/profile/${section}/${id}`, { method: "DELETE" });
        },
        async reorder(section: Section, ids: string[]) {
          return f<ItemOut[]>(
            `/api/v1/profile/${section}/reorder`,
            json("POST", { ids }),
          );
        },
      },
    },
    resumes: {
      async list() {
        return f<ResumeOut[]>("/api/v1/resumes");
      },
      async get(id: string) {
        return f<ResumeOut>(`/api/v1/resumes/${id}`);
      },
      async upload(file: File) {
        const form = new FormData();
        form.append("file", file);
        return f<ResumeOut>("/api/v1/resumes", { method: "POST", body: form });
      },
      async extraction(id: string) {
        return f<ResumeExtraction>(`/api/v1/resumes/${id}/extraction`);
      },
      async patch(id: string, body: { title?: string; is_primary?: boolean }) {
        return f<ResumeOut>(`/api/v1/resumes/${id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
          headers: { "Content-Type": "application/json" },
        });
      },
      async reprocess(id: string) {
        return f<ResumeOut>(`/api/v1/resumes/${id}/reprocess`, { method: "POST" });
      },
      async remove(id: string) {
        return f<void>(`/api/v1/resumes/${id}`, { method: "DELETE" });
      },
      async confirmProfile(id: string, extraction: ResumeExtraction) {
        return f<void>(
          `/api/v1/resumes/${id}/confirm-profile`,
          json("POST", { extraction }),
        );
      },
    },
    jobs: {
      async list(query: JobQuery = {}) {
        const qs = new URLSearchParams(
          Object.entries(query).filter(([, v]) => v !== undefined && v !== "")
            .map(([k, v]) => [k, String(v)]),
        ).toString();
        return f<JobListResponse>(`/api/v1/jobs${qs ? `?${qs}` : ""}`);
      },
      async get(id: string) { return f<JobDetail>(`/api/v1/jobs/${id}`); },
      async create(raw_text: string) {
        return f<{ id: string; status: JobStatus }>("/api/v1/jobs", json("POST", { raw_text }));
      },
      async patch(id: string, body: { title?: string }) {
        return f<JobDetail>(`/api/v1/jobs/${id}`, { method: "PATCH", body: JSON.stringify(body),
          headers: { "Content-Type": "application/json" } });
      },
      async remove(id: string) { return f<void>(`/api/v1/jobs/${id}`, { method: "DELETE" }); },
    },
    matches: {
      async create(job_id: string) {
        return f<{ id: string; status: MatchStatus }>("/api/v1/matches", json("POST", { job_id }));
      },
      async get(id: string) { return f<JobMatch>(`/api/v1/matches/${id}`); },
      async list(query: { job_id?: string; min_score?: number; sort?: string } = {}) {
        const qs = new URLSearchParams(
          Object.entries(query).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
        ).toString();
        return f<{ items: JobMatch[] }>(`/api/v1/matches${qs ? `?${qs}` : ""}`);
      },
      async components(id: string) { return f<MatchComponent[]>(`/api/v1/matches/${id}/components`); },
      async recompute(body: { scope: "all" | string }) {
        return f<{ status: string; count: number }>("/api/v1/matches/recompute", json("POST", body));
      },
    },
    skillGaps: {
      async list(job_match_id: string) {
        return f<SkillGap[]>(`/api/v1/skill-gaps?scope=job&job_match_id=${job_match_id}`);
      },
      async patch(id: string, status: SkillGapStatus) {
        return f<SkillGap>(`/api/v1/skill-gaps/${id}`, { method: "PATCH",
          body: JSON.stringify({ status }), headers: { "Content-Type": "application/json" } });
      },
    },
    eval: {
      async listRuns(query: { suite?: string; limit?: number; offset?: number } = {}) {
        const qs = new URLSearchParams(
          Object.entries(query).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
        ).toString();
        return f<{ items: EvalRun[]; total: number }>(`/api/v1/eval/runs${qs ? `?${qs}` : ""}`);
      },
      async getRun(id: string) { return f<EvalRun>(`/api/v1/eval/runs/${id}`); },
      async runResults(id: string) { return f<EvalResult[]>(`/api/v1/eval/runs/${id}/results`); },
      async createRun(suite: string) {
        return f<EvalRun>("/api/v1/eval/runs", json("POST", { suite }));
      },
    },
  };
}
