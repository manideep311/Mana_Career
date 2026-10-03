"use client";

import { useEffect, useRef, useState } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PasswordField } from "@/components/auth/AuthField";
import { AuthActions, AuthHeading } from "@/components/auth/AuthHeading";
import { MailIllustration } from "@/components/auth/MailIllustration";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/FormError";
import { ProblemError } from "@/lib/api/fetcher";
import { clearLinkToken, readLinkToken } from "@/lib/link-token";
import { useAuth } from "@/providers/AuthProvider";

const schema = z
  .object({
    password: z.string().min(10, "Use at least 10 characters.").max(200),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "The passwords don't match.",
    path: ["confirm"],
  });
type Values = z.infer<typeof schema>;

/** Choose a new password from an emailed link; ends every signed-in session. */
export function ResetPasswordForm() {
  const { api } = useAuth();
  // The server never sees the `#token` part, so read it after hydration (once:
  // React may run effects twice in development, and reading clears it).
  const [token, setToken] = useState<string | null>(null);
  const [state, setState] = useState<"reading" | "form" | "done" | "bad-link">("reading");
  const read = useRef(false);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (read.current) return;
    read.current = true;
    const found = readLinkToken();
    clearLinkToken();
    setToken(found);
    setState(found ? "form" : "bad-link");
  }, []);

  const onSubmit = handleSubmit(async ({ password }) => {
    try {
      await api.auth.resetPassword({ token: token as string, new_password: password });
      setState("done");
    } catch (err) {
      if (err instanceof ProblemError && err.code === "invalid_link") {
        setState("bad-link");
      } else {
        setError("root", { message: "Something went wrong. Please try again." });
      }
    }
  });

  if (state === "bad-link") {
    return (
      <>
        <AuthHeading
          illustration={<MailIllustration state="error" />}
          title="This link has expired"
          description="This link is invalid or has expired. Reset links work once and last 30 minutes."
          role="alert"
        />
        <AuthActions
          primary={{ href: "/forgot-password", label: "Request a new link" }}
          secondary={{ href: "/login", label: "Back to sign in" }}
        />
      </>
    );
  }
  if (state === "done") {
    return (
      <>
        <AuthHeading
          illustration={<MailIllustration state="success" />}
          title="Password changed"
          description="Your password has been changed, and you've been signed out everywhere."
          role="status"
        />
        <AuthActions
          primary={{ href: "/login", label: "Sign in" }}
          secondary={{ href: "/", label: "Go to home" }}
        />
      </>
    );
  }

  return (
    <>
      <AuthHeading
        align="start"
        title="Choose a new password"
        description="Pick something you haven't used here before."
      />
      {state === "form" ? (
        <form noValidate onSubmit={onSubmit} className="mt-8 flex flex-col gap-4">
          <FormError message={errors.root?.message} />
          <PasswordField
            id="password"
            label="New password"
            autoComplete="new-password"
            hint="At least 10 characters."
            error={errors.password?.message}
            {...register("password")}
          />
          <PasswordField
            id="confirm"
            label="Confirm new password"
            autoComplete="new-password"
            error={errors.confirm?.message}
            {...register("confirm")}
          />
          <Button type="submit" variant="gradient" size="xl" loading={isSubmitting} className="w-full">
            Set new password
          </Button>
        </form>
      ) : null}
    </>
  );
}
