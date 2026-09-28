import { expect, test } from "@playwright/test";
import { nav, signInAs } from "./helpers";

test("navigation is role-aware", async ({ page }) => {
  await signInAs(page, "Dr. Meera Iyer");
  const links = nav(page).getByRole("link");
  await expect(links.filter({ hasText: "Pharmacy" })).toBeVisible();
  await expect(links.filter({ hasText: "Surgery & OT" })).toBeVisible();
  await expect(links.filter({ hasText: "Staff & Roles" })).toHaveCount(0);
  await expect(links.filter({ hasText: "Inventory" })).toHaveCount(0);
  await expect(links.filter({ hasText: "Audit Trail" })).toHaveCount(0);

  // Deep link to a forbidden page shows a friendly 403, not a broken screen.
  await page.goto("/staff");
  await expect(page.getByText("You don't have access to this page")).toBeVisible();
});

test("an account that isn't provisioned is blocked", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /hasn't been added/ }).click();
  await expect(page.getByText("Access not available")).toBeVisible();
  await expect(page.getByText(/has not been added to RxPulse/)).toBeVisible();
});

test("admin manages staff and roles", async ({ page }) => {
  await signInAs(page, "Asha Menon");
  await nav(page).getByRole("link", { name: "Staff & Roles" }).click();
  await expect(page.getByRole("heading", { name: /Staff & Role-Based Access Control/ })).toBeVisible();

  // Roles show real permission counts and every staff row shows its roles
  const pharmacistRole = page.getByRole("button", { name: /^Pharmacist\b/ });
  await expect(pharmacistRole).toContainText(/\d+ permissions/);
  await expect(page.getByRole("row", { name: /Farhan Qureshi/ })).toContainText("Pharmacist@ Main Pharmacy");

  // Invite a new OT nurse
  await page.getByRole("button", { name: "Add Staff Member" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Work email (Microsoft account)").fill("rina.das@eyecare.example");
  await dialog.getByLabel("Display name").fill("Rina Das");
  const roleSelect = dialog.getByRole("combobox").first();
  await roleSelect.selectOption((await roleSelect.locator("option", { hasText: "OT Nurse" }).getAttribute("value"))!);
  await dialog.getByRole("button", { name: "Add staff member" }).click();
  await expect(page.getByText("Invitation created for rina.das@eyecare.example")).toBeVisible();
  const search = page.getByPlaceholder("Search name or email…");
  await search.fill("rina");
  await expect(page.getByRole("row", { name: /Rina Das/ })).toContainText("Invited");
  await search.fill("suresh");
  await expect(page.getByRole("row", { name: /Suresh Kumar/ })).toContainText("Inactive");
  await search.fill("");

  // Deactivate with an in-app confirmation (not window.confirm)
  await page.getByRole("row", { name: /Ananya Sen/ }).getByRole("button", { name: "Deactivate" }).click();
  await expect(page.getByRole("dialog", { name: "Deactivate staff member?" })).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Deactivate" }).click();
  await expect(page.getByRole("row", { name: /Ananya Sen/ })).toContainText("Inactive");

  // Super Admin role is read-only
  await page.getByRole("button", { name: /^Super Admin/ }).click();
  await expect(page.getByText("Super Admin always holds every permission")).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("checkbox").first()).toBeDisabled();
});
