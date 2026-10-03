import { expect, test } from "@playwright/test";

import { PASSWORD, signUp, uniqueEmail } from "./support";

test("forgot password never reveals whether an account exists", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page).toHaveURL(/\/forgot-password$/);
  await page.getByLabel("Email", { exact: true }).fill(uniqueEmail("nobody"));
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If an account exists for that address");
});

test("an expired or made-up reset link offers a new one", async ({ page }) => {
  await page.goto("/reset-password#token=not-a-real-token");
  await page.getByLabel("New password", { exact: true }).fill("a-brand-new-passphrase");
  await page.getByLabel("Confirm new password", { exact: true }).fill("a-brand-new-passphrase");
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByRole("heading", { name: "This link has expired" })).toBeVisible();
  // The token never stays in the address bar.
  expect(new URL(page.url()).hash).toBe("");
});

test("sign out from the sidebar, then sign back in", async ({ page }) => {
  const email = uniqueEmail("desktop");
  await signUp(page, email);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // A signed-out visitor can't reach the app.
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("sign out on a phone from the account menu @phone", async ({ page }) => {
  await signUp(page, uniqueEmail("phone"));
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
});
