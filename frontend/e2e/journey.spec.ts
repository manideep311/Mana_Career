import { expect, test } from "@playwright/test";

import { signUp, uniqueEmail, uploadAndConfirmResume } from "./support";

/**
 * The core path through the real stack: landing → sign up → résumé read and
 * confirmed → guidance on the dashboard → an application prepared, reviewed,
 * approved and recorded. Runs against demo providers (no model keys), so the
 * guidance here is the deterministic layer.
 */
test("from the landing page to an approved application", async ({ page }) => {
  await test.step("the landing page leads to sign-up", async () => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { level: 1, name: /build the career you actually want/i }),
    ).toBeVisible();
    await page.getByRole("link", { name: /start my career journey/i }).click();
    await expect(page).toHaveURL(/\/register$/);
  });

  await test.step("create an account", async () => {
    await signUp(page, uniqueEmail("journey"));
  });

  await test.step("upload a résumé and confirm what was read", async () => {
    await uploadAndConfirmResume(page);
  });

  await test.step("the dashboard gives a direction and next steps", async () => {
    await expect(
      page.getByRole("heading", { level: 1, name: /Good (morning|afternoon|evening), Asha/ }),
    ).toBeVisible();
    await expect(page.getByText("Your direction")).toBeVisible();
    await expect(page.getByRole("region", { name: "Your journey" })).toBeVisible();
    // Honest guidance: fit is described in words, never as a percentage.
    await expect(page.locator("main")).not.toContainText(/\d\s?%/);
  });

  await test.step("the résumé review explains what to improve", async () => {
    await page.goto("/resume");
    await expect(page.getByRole("heading", { name: "How your résumé reads" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "What to improve" })).toBeVisible();
  });

  let jobTitle = "";
  await test.step("prepare an application for a catalogue role", async () => {
    await page.goto("/jobs");
    const firstJob = page.locator('main a[href^="/jobs/"]').first();
    await expect(firstJob).toBeVisible();
    await firstJob.click();
    await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}$/);
    jobTitle = (await page.getByRole("heading", { level: 1 }).innerText()).trim();
    await page.getByRole("link", { name: "Prepare application" }).click();
    await expect(page).toHaveURL(/\/applications\/new\//);
    await page.getByRole("button", { name: "Prepare application" }).click();
    await expect(page.getByText(/Review your application for/)).toBeVisible({ timeout: 120_000 });
  });

  await test.step("nothing is sent without a recipient and an explicit approval", async () => {
    await expect(page.getByText("Nothing will be sent until you approve it.")).toBeVisible();
    await page.getByRole("button", { name: /approve & send/i }).click();
    await expect(page.getByText("Enter the hiring contact's email address.")).toBeVisible();

    await page.getByLabel("Send to").fill("hiring@example.invalid");
    await page.getByRole("button", { name: /approve & send/i }).click();
    await expect(
      page.getByRole("status").filter({ hasText: /recorded as sent|Delivered to your inbox|sent to/i }),
    ).toBeVisible({ timeout: 60_000 });
  });

  await test.step("the application shows on the board as applied", async () => {
    await page.goto("/applications");
    const applied = page.getByRole("region", { name: "Applied" });
    await expect(applied.getByText(jobTitle, { exact: false }).first()).toBeVisible();
  });
});
