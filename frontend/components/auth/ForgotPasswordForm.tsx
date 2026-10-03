"use client";

import { useState } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Mail } from "lucide-react";

import { AuthField } from "@/components/auth/AuthField";
import { AuthActions, AuthHeading } from "@/components/auth/AuthHeading";
import { MailIllustration } from "@/components/auth/MailIllustration";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/FormError";
import { useAuth } from "@/providers/AuthProvider";

const schema = z.object({ email: z.string().email("Enter a valid email address.") });
type Values = z.infer<typeof schema>;

/**
 * Ask for a reset link. The confirmation reads the same whether or not the
 * address has an account (the server words it that way on purpose).
 */
export function ForgotPasswordForm() {
  const { api } = useAuth();
  const [sent, setSent] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async ({ email }) => {
    try {
      const res = await api.auth.forgotPassword(email);
      setSent(res.detail);
    } catch {
      setError("root", { message: "Something went wrong. Please try again." });
    }
  });

  if (sent) {
    return (
      <>
        <AuthHeading
          illustration={<MailIllustration state="sent" />}
          title="Check your inbox"
          description={sent}
          role="status"
        />
        <p className="mt-3 text-center text-sm text-text-muted">
          Didn&apos;t get it? Check your spam folder, or try again in a few minutes.
        </p>
        <AuthActions
          primary={{ href: "/login", label: "Back to sign in" }}
          secondary={{ href: "/", label: "Go to home" }}
        />
      </>
    );
  }

  return (
    <>
      <AuthHeading
        align="start"
        title="Forgot your password?"
        description="Enter your email and we'll send you a link to choose a new one."
      />
      <form noValidate onSubmit={onSubmit} className="mt-8 flex flex-col gap-4">
        <FormError message={errors.root?.message} />
        <AuthField
          id="email"
          label="Email"
          icon={Mail}
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message}
          {...register("email")}
        />
        <Button type="submit" variant="gradient" size="xl" loading={isSubmitting} className="w-full">
          Send reset link
        </Button>
        <Link href="/login" className="text-center text-sm font-semibold text-[var(--auth-link,var(--accent))] underline underline-offset-2 hover:decoration-2">
          Back to sign in
        </Link>
      </form>
    </>
  );
}
