"use client";

import { useEffect, useRef, useState } from "react";

import { AuthActions, AuthHeading } from "@/components/auth/AuthHeading";
import { MailIllustration } from "@/components/auth/MailIllustration";
import { clearLinkToken, readLinkToken } from "@/lib/link-token";
import { useAuth } from "@/providers/AuthProvider";

/** Confirms the address as soon as the page opens; the link works once. */
export function VerifyEmail() {
  const { api, status, reloadUser } = useAuth();
  // "working" on the server and on first paint alike (the server can't see the
  // `#token` part); the link is read and spent exactly once after hydration.
  const [state, setState] = useState<"working" | "done" | "bad-link">("working");
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // React may run effects twice in development
    started.current = true;
    const token = readLinkToken();
    clearLinkToken();
    if (!token) {
      setState("bad-link");
      return;
    }
    api.auth
      .verifyEmail(token)
      .then(async () => {
        setState("done");
        await reloadUser().catch(() => undefined);
      })
      .catch(() => setState("bad-link"));
  }, [api, reloadUser]);

  const primary =
    status === "authed"
      ? { href: "/dashboard", label: "Go to your dashboard" }
      : { href: "/login", label: "Sign in" };
  const home = { href: "/", label: "Go to home" };

  if (state === "working") {
    return (
      <AuthHeading
        illustration={<MailIllustration state="waiting" />}
        title="Confirming your email…"
        description="This only takes a moment."
        role="status"
      />
    );
  }
  if (state === "done") {
    return (
      <>
        <AuthHeading
          illustration={<MailIllustration state="success" />}
          title="Email confirmed"
          description="Your email address is confirmed. You can now send applications you approve."
          role="status"
        />
        <AuthActions primary={primary} secondary={home} />
      </>
    );
  }
  return (
    <>
      <AuthHeading
        illustration={<MailIllustration state="error" />}
        title="Confirm your email"
        description={
          <>
            This link is invalid or has expired. Confirmation links work once and last 48
            hours. If you&apos;re signed in, use &ldquo;Resend link&rdquo; in the banner at the
            top of the app.
          </>
        }
        role="alert"
      />
      <AuthActions primary={primary} secondary={home} />
    </>
  );
}
