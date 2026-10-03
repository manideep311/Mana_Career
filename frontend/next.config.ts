import type { NextConfig } from "next";

// Vercel sets VERCEL=1 during its builds. There, Next.js itself serves the
// site, so it sends the security headers that nginx sends in the self-hosted
// stack (keep the two lists in step: deploy/nginx/nginx.conf).
const onVercel = process.env.VERCEL === "1";

const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
  },
  {
    key: "Content-Security-Policy",
    value:
      "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
      "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; " +
      "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; " +
      "upgrade-insecure-requests",
  },
];

const config: NextConfig = {
  reactStrictMode: true,
  // The Docker image runs the standalone server; Vercel builds its own way.
  output: onVercel ? undefined : "standalone",
  outputFileTracingRoot: process.cwd(),
  // Don't advertise the framework (nginx also strips it in production).
  poweredByHeader: false,
  async headers() {
    return onVercel ? [{ source: "/:path*", headers: SECURITY_HEADERS }] : [];
  },
};

export default config;
