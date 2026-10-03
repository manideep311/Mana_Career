import type { Metadata } from "next";

import { AuthHeading } from "@/components/auth/AuthHeading";
import { RegisterForm } from "@/components/auth/RegisterForm";

export const metadata: Metadata = {
  title: "Create account | Mana Career",
};

export default function RegisterPage() {
  return (
    <>
      <AuthHeading
        align="start"
        title="Create your account"
        description="Start with your résumé and see where it can take you."
      />
      <div className="mt-8">
        <RegisterForm />
      </div>
    </>
  );
}
