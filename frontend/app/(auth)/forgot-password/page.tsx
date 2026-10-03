import type { Metadata } from "next";

import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export const metadata: Metadata = { title: "Reset your password | Mana Career" };

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
