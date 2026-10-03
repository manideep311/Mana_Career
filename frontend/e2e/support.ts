import { expect, type Page } from "@playwright/test";

export const PASSWORD = "e2e-only-passphrase-1";

/** A fresh address per run, on a reserved domain nothing can deliver to. */
export function uniqueEmail(tag: string): string {
  return `e2e-${tag}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.invalid`;
}

/** Create an account through the real sign-up form; lands on /resume. */
export async function signUp(page: Page, email: string, fullName = "Asha Rao"): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Full name", { exact: true }).fill(fullName);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/resume$/);
}

const RESUME_LINES = [
  "Asha Rao",
  "asha.rao@example.com | +91 98765 43210 | Bengaluru",
  "SUMMARY",
  "Backend engineer who builds reliable APIs and data pipelines.",
  "EXPERIENCE",
  "Backend Engineer, Acme Payments   2021 - 2024",
  "- Built Python and FastAPI services handling 2 million requests a day",
  "- Designed PostgreSQL schemas and cut report query time by 40%",
  "- Containerised services with Docker and set up CI for every repository",
  "Software Engineer, Brightlane   2019 - 2021",
  "- Wrote REST APIs in Python for an internal analytics tool used by 300 people",
  "- Responsible for code reviews and on-call rotations",
  "EDUCATION",
  "B.Tech Computer Science, 2019",
  "SKILLS",
  "Python, FastAPI, PostgreSQL, Docker, Git, SQL, REST APIs",
];

function escapePdf(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

/**
 * A one-page text PDF (Helvetica), built in code so no binary fixture lives in
 * the repo. Real text, so the parser reads it like any exported résumé.
 */
export function resumePdf(lines: string[] = RESUME_LINES): Buffer {
  const content = [
    "BT",
    "/F1 11 Tf",
    "14 TL",
    "72 740 Td",
    ...lines.map((line) => `(${escapePdf(line)}) '`),
    "ET",
  ].join("\n");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
      "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${Buffer.byteLength(content, "latin1")} >>\nstream\n${content}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(Buffer.byteLength(pdf, "latin1"));
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf, "latin1");
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf, "latin1");
}

/** Upload the sample résumé, wait for processing, confirm what was read. */
export async function uploadAndConfirmResume(page: Page): Promise<void> {
  await page.goto("/resume");
  await page.getByTestId("resume-file-input").setInputFiles({
    name: "asha-rao-resume.pdf",
    mimeType: "application/pdf",
    buffer: resumePdf(),
  });
  await expect(page.getByRole("heading", { name: "Review what we found" })).toBeVisible({
    timeout: 90_000,
  });
  await page.getByRole("button", { name: /Confirm & build my profile/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 30_000 });
}
