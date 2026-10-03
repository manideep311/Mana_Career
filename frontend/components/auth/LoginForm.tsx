"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ArrowRight, Mail } from "lucide-react";

import { AuthField, PasswordField } from "@/components/auth/AuthField";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/FormError";
import { applyProblemToForm } from "@/lib/api/form-errors";
import { useAuth } from "@/providers/AuthProvider";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

type LoginValues = z.infer<typeof schema>;

export function LoginForm() {
  const router = useRouter();
  const { login } = useAuth();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    try {
      await login(values);
      router.push("/dashboard");
    } catch (err) {
      if (!applyProblemToForm(err, setError)) {
        setError("root", { message: "Something went wrong. Please try again." });
      }
    }
  });

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-col gap-4">
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
      <PasswordField
        id="password"
        label="Password"
        autoComplete="current-password"
        placeholder="Your password"
        error={errors.password?.message}
        {...register("password")}
      />
      <Link
        href="/forgot-password"
        className="-mt-1 self-end text-sm font-semibold text-[var(--auth-link,var(--accent))] underline underline-offset-2 hover:decoration-2"
      >
        Forgot password?
      </Link>

      <Button type="submit" variant="gradient" size="xl" loading={isSubmitting} className="mt-2 w-full">
        Sign in
        {isSubmitting ? null : <ArrowRight className="h-5 w-5" aria-hidden />}
      </Button>

      <p className="mt-2 text-center text-sm text-text-muted">
        New to Mana Career?{" "}
        <Link href="/register" className="font-semibold text-[var(--auth-link,var(--accent))] underline underline-offset-2 hover:decoration-2">
          Create an account
        </Link>
      </p>
    </form>
  );
}
