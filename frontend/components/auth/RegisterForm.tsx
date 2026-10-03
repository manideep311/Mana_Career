"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ArrowRight, Mail, UserRound } from "lucide-react";

import { AuthField, PasswordField } from "@/components/auth/AuthField";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/FormError";
import { ProblemError } from "@/lib/api/fetcher";
import { applyProblemToForm } from "@/lib/api/form-errors";
import { useAuth } from "@/providers/AuthProvider";

const schema = z.object({
  full_name: z.string().min(1, "Enter your name."),
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(10, "Use at least 10 characters."),
});

type RegisterValues = z.infer<typeof schema>;

export function RegisterForm() {
  const router = useRouter();
  const { register: registerUser } = useAuth();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    try {
      await registerUser(values);
      router.push("/resume");
    } catch (err) {
      if (err instanceof ProblemError && err.code === "email_taken") {
        setError("email", { message: "That email is already registered." });
        return;
      }
      if (!applyProblemToForm(err, setError)) {
        setError("root", { message: "Something went wrong. Please try again." });
      }
    }
  });

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-col gap-4">
      <FormError message={errors.root?.message} />

      <AuthField
        id="full_name"
        label="Full name"
        icon={UserRound}
        type="text"
        autoComplete="name"
        placeholder="Your name"
        error={errors.full_name?.message}
        {...register("full_name")}
      />
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
      <PasswordField
        id="password"
        label="Password"
        autoComplete="new-password"
        placeholder="Create a password"
        hint="At least 10 characters."
        error={errors.password?.message}
        {...register("password")}
      />

      <Button type="submit" variant="gradient" size="xl" loading={isSubmitting} className="mt-2 w-full">
        Create account
        {isSubmitting ? null : <ArrowRight className="h-5 w-5" aria-hidden />}
      </Button>

      <p className="mt-2 text-center text-sm text-text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-[var(--auth-link,var(--accent))] underline underline-offset-2 hover:decoration-2">
          Sign in
        </Link>
      </p>
    </form>
  );
}
