// Where the browser reaches the API. Unset in development (the API runs on
// :8000). "" or "/" means this site's own origin: behind nginx (Docker) or
// Vercel's /api forwarding (middleware.ts). A trailing slash is dropped.
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");
