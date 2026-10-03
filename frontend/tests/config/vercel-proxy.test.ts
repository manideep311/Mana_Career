// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { config, middleware } from "../../middleware";

/** The request headers a rewrite hands to its destination. */
function forwarded(res: Response): Record<string, string> {
  const names = (res.headers.get("x-middleware-override-headers") ?? "").split(",");
  return Object.fromEntries(
    names.filter(Boolean).map((n) => [n, res.headers.get(`x-middleware-request-${n}`) ?? ""]),
  );
}

afterEach(() => vi.unstubAllEnvs());

describe("Vercel /api forwarding", () => {
  it("only runs for /api", () => {
    expect(config.matcher).toBe("/api/:path*");
  });

  it("does nothing without API_ORIGIN (local development)", () => {
    vi.stubEnv("API_ORIGIN", "");
    const res = middleware(new NextRequest("https://site.test/api/v1/meta"));
    expect(res.headers.get("x-middleware-rewrite")).toBeNull();
  });

  it("forwards to the API with the visitor's address and the shared secret", () => {
    vi.stubEnv("API_ORIGIN", "https://api.example.onrender.com");
    vi.stubEnv("PROXY_SHARED_SECRET", "s".repeat(40));
    const res = middleware(
      new NextRequest("https://site.test/api/v1/jobs?limit=5", {
        headers: { "x-real-ip": "203.0.113.9" },
      }),
    );
    expect(res.headers.get("x-middleware-rewrite")).toBe(
      "https://api.example.onrender.com/api/v1/jobs?limit=5",
    );
    const sent = forwarded(res);
    expect(sent["x-mana-client-ip"]).toBe("203.0.113.9");
    expect(sent["x-mana-proxy-secret"]).toBe("s".repeat(40));
    expect(sent.host).toBe("api.example.onrender.com");
  });

  it("drops a visitor's own attempt to claim an address", () => {
    vi.stubEnv("API_ORIGIN", "https://api.example.onrender.com");
    vi.stubEnv("PROXY_SHARED_SECRET", "");
    const res = middleware(
      new NextRequest("https://site.test/api/v1/auth/login", {
        headers: { "x-mana-proxy-secret": "guess", "x-mana-client-ip": "1.2.3.4" },
      }),
    );
    const sent = forwarded(res);
    expect(sent["x-mana-proxy-secret"]).toBeUndefined();
    expect(sent["x-mana-client-ip"]).toBeUndefined();
  });
});

describe("Next.js config", () => {
  it("sends security headers itself only on Vercel", async () => {
    vi.stubEnv("VERCEL", "1");
    vi.resetModules();
    const onVercel = (await import("../../next.config")).default;
    expect(onVercel.output).toBeUndefined();
    const [rule] = await onVercel.headers!();
    const names = rule.headers.map((h) => h.key);
    expect(names).toEqual(
      expect.arrayContaining(["Content-Security-Policy", "Strict-Transport-Security", "X-Frame-Options"]),
    );

    vi.stubEnv("VERCEL", "");
    vi.resetModules();
    const selfHosted = (await import("../../next.config")).default;
    expect(selfHosted.output).toBe("standalone");
    expect(await selfHosted.headers!()).toEqual([]);
  });
});
