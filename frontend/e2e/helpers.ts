import { expect, type Page } from "@playwright/test";

export const DOMAIN = "eyecare.example";

export async function signInAs(page: Page, displayName: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(displayName) }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

export function nav(page: Page) {
  return page.getByRole("navigation", { name: "Main" });
}
