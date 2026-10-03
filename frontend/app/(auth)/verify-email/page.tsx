import type { Metadata } from "next";

import { VerifyEmail } from "@/components/auth/VerifyEmail";

export const metadata: Metadata = {
  title: "Confirm your email | Mana Career",
  referrer: "no-referrer",
};

export default function VerifyEmailPage() {
  return <VerifyEmail />;
}
