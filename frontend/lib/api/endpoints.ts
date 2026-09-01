import {
  AccessResponse,
  AuthResponse,
  CareerProfile,
  ExtractedExperience,
  ExtractedEducation,
  ExtractedProject,
  ExtractedCertification,
  ItemOut,
  ProfileFull,
  ResumeExtraction,
  ResumeOut,
  Section,
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
  };
}
