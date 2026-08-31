import type { Metadata } from "next";

import { RegisterForm } from "@/components/auth/RegisterForm";
import { CardBody, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Create account | Mana Career",
};

export default function RegisterPage() {
  return (
    <>
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <p className="text-sm text-text-muted">
          Start building a stronger career profile.
        </p>
      </CardHeader>
      <CardBody>
        <RegisterForm />
      </CardBody>
    </>
  );
}
