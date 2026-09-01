import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Dashboard nudge shown until the user has a confirmed résumé. Points them at
 * the résumé flow so their profile can be seeded from an upload instead of
 * being filled in field by field.
 */
export function SetupProfileCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Finish setting up your profile</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col items-start gap-4">
        <p>
          Upload your résumé and we&apos;ll pull in your experience and education
          so you can skip the typing.
        </p>
        <Link href="/resume" className={buttonVariants({ variant: "default" })}>
          Upload your résumé
        </Link>
      </CardBody>
    </Card>
  );
}
