import type { Metadata } from "next";

import { AuthHeading } from "@/components/auth/AuthHeading";
import { LoginForm } from "@/components/auth/LoginForm";

export const metadata: Metadata = {
  title: "Sign in | Mana Career",
};

export default function LoginPage() {
  return (
    <>
      <AuthHeading
        align="start"
        title="Welcome back"
        description="Sign in to continue shaping your career."
      />
      <div className="mt-8">
        <LoginForm />
      </div>
    </>
  );
}
