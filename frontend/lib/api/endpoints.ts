import {
  AccessResponse,
  AuthResponse,
  CareerProfile,
  ItemOut,
  ProfileFull,
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
  };
}
