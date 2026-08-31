import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/LoginForm";
import { CardBody, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Sign in | Mana Career",
};

export default function LoginPage() {
  return (
    <>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <p className="text-sm text-text-muted">
          Welcome back. Enter your details to continue.
        </p>
      </CardHeader>
      <CardBody>
        <LoginForm />
      </CardBody>
    </>
  );
}
