"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FormError } from "@/components/ui/FormError";
import { Input } from "@/components/ui/input";
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

      <Field id="full_name" label="Full name" error={errors.full_name?.message}>
        <Input
          id="full_name"
          type="text"
          autoComplete="name"
          aria-invalid={errors.full_name ? true : undefined}
          {...register("full_name")}
        />
      </Field>

      <Field id="email" label="Email" error={errors.email?.message}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          aria-invalid={errors.email ? true : undefined}
          {...register("email")}
        />
      </Field>

      <Field
        id="password"
        label="Password"
        hint="At least 10 characters."
        error={errors.password?.message}
      >
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.password ? true : undefined}
          {...register("password")}
        />
      </Field>

      <Button type="submit" loading={isSubmitting} className="mt-1 w-full">
        Create account
      </Button>

      <p className="text-center text-sm text-text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
