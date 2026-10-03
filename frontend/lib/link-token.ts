/**
 * Emailed links carry their token after `#` (never sent to a server or in a
 * Referer header). Read it without side effects so React can call this more
 * than once, then drop it from the address bar once the page has it.
 */
export function readLinkToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  return token && token.length <= 200 ? token : null;
}

export function clearLinkToken(): void {
  if (typeof window === "undefined" || !window.location.hash) return;
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
}
