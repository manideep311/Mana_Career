import { NextResponse, type NextRequest } from "next/server";

const PROXY_SECRET_HEADER = "x-mana-proxy-secret";
const PROXY_CLIENT_HEADER = "x-mana-client-ip";

/**
 * Hosted on Vercel, the browser calls `/api` on the website's own address and
 * this forwards it to the API (API_ORIGIN, e.g. the Render service). Keeping
 * the API same-origin keeps the sign-in cookie first-party, so it works even
 * where browsers block third-party cookies.
 *
 * The API only believes a visitor address that arrives with
 * PROXY_SHARED_SECRET, so its rate limits count people rather than Vercel's
 * servers. Vercel itself sets `x-real-ip` / `x-forwarded-for` (overwriting
 * anything the browser sent). Without API_ORIGIN (local development) this
 * does nothing and the app calls NEXT_PUBLIC_API_BASE_URL directly.
 */
export function middleware(request: NextRequest) {
  const origin = process.env.API_ORIGIN;
  if (!origin) return NextResponse.next();

  const target = new URL(`${request.nextUrl.pathname}${request.nextUrl.search}`, origin);
  const headers = new Headers(request.headers);
  // Never pass along a claim the browser made about itself.
  headers.delete(PROXY_SECRET_HEADER);
  headers.delete(PROXY_CLIENT_HEADER);
  headers.set("host", target.host);

  const secret = process.env.PROXY_SHARED_SECRET;
  const visitor =
    request.headers.get("x-real-ip") ??
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  if (secret && visitor) {
    headers.set(PROXY_SECRET_HEADER, secret);
    headers.set(PROXY_CLIENT_HEADER, visitor);
  }
  return NextResponse.rewrite(target, { request: { headers } });
}

export const config = { matcher: "/api/:path*" };
