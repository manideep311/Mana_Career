import { API_BASE_URL } from "@/lib/env";

export class ProblemError extends Error {
  constructor(
    public code: string,
    public status: number,
    public problem: unknown,
  ) {
    super(`${code} (${status})`);
    this.name = "ProblemError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });
  if (res.status === 204) return undefined as T;
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const code =
      body && typeof body === "object" && "code" in body
        ? String((body as { code: unknown }).code)
        : "error";
    throw new ProblemError(code, res.status, body);
  }
  return body as T;
}
