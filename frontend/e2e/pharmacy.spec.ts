import { expect, test } from "@playwright/test";
import { nav, signInAs } from "./helpers";

test("pharmacist: OTC walk-in sale, FEFO allocation, dispatch with invoice", async ({ page }) => {
  await signInAs(page, "Farhan Qureshi");
  await nav(page).getByRole("link", { name: "Pharmacy" }).click();
  await expect(page.getByRole("heading", { name: "Pharmacy Orders & FEFO Dispatch" })).toBeVisible();

  await page.getByRole("button", { name: "New Counter Sale" }).click();
  const d = page.getByRole("dialog");
  await d.getByRole("button", { name: "Walk-in buyer" }).click();
  await d.getByLabel("Buyer name").fill("Mr. Test Buyer");
  await d.getByPlaceholder("Search medicine or consumable…").fill("lubricant");
  await d.getByRole("button", { name: /Carboxymethylcellulose/ }).click();
  await d.getByRole("button", { name: "Create sale & allocate" }).click();
  await expect(page.getByText(/created · stock reserved by FEFO/)).toBeVisible();

  const row = page.getByRole("row", { name: /Mr\. Test Buyer/ });
  await expect(row).toContainText("Allocated");
  await expect(row).toContainText(/CM\w+: 1u/); // FEFO batch chip
  await row.getByRole("button", { name: "Dispatch" }).click();
  const confirm = page.getByRole("dialog", { name: /Dispatch CS-/ });
  await expect(confirm).toContainText("Mr. Test Buyer (walk-in)");
  await confirm.getByRole("button", { name: "Confirm dispatch" }).click();
  await expect(page.getByText(/Dispatched · invoice INV-/)).toBeVisible();
  await expect(page.getByRole("row", { name: /Mr\. Test Buyer/ })).toContainText("Dispatched");
});

test("pharmacist: Schedule H item needs a prescription at the counter", async ({ page }) => {
  await signInAs(page, "Farhan Qureshi");
  await page.goto("/pharmacy");
  await page.getByRole("button", { name: "New Counter Sale" }).click();
  const d = page.getByRole("dialog");
  await d.getByRole("button", { name: "Walk-in buyer" }).click();
  await d.getByLabel("Buyer name").fill("No Rx Buyer");
  await d.getByPlaceholder("Search medicine or consumable…").fill("moxi");
  await d.getByRole("button", { name: /Moxifloxacin/ }).click();
  await expect(d.getByText("Required: basket contains Schedule H/H1/X items")).toBeVisible();
  await expect(d.getByRole("button", { name: "Create sale & allocate" })).toBeDisabled();
  await d.getByLabel(/Prescription reference/).fill("OPD-RX-1");
  await expect(d.getByRole("button", { name: "Create sale & allocate" })).toBeEnabled();
});

test("doctor raises a requisition and only sees their own", async ({ page }) => {
  await signInAs(page, "Dr. Rajesh Kulkarni");
  await nav(page).getByRole("link", { name: "Pharmacy" }).click();
  await expect(page.getByRole("heading", { name: "Pharmacy Requisitions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New Counter Sale" })).toHaveCount(0);

  await page.getByRole("button", { name: "New Requisition" }).click();
  const d = page.getByRole("dialog");
  await d.getByLabel(/Department/).fill("OT-2 (Cataract)");
  await d.getByPlaceholder("Search medicine or consumable…").fill("balanced");
  await d.getByRole("button", { name: /Balanced Salt Solution/ }).click();
  await d.getByRole("button", { name: "Submit requisition" }).click();
  await expect(page.getByText(/RQ-\d{4}-\d{5} created/)).toBeVisible();

  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(2); // seeded requisition + the new one; no counter sales
  await expect(page.getByRole("button", { name: "Dispatch" })).toHaveCount(0);
});

test("inventory shows names, server-computed expiry and valuation", async ({ page }) => {
  await signInAs(page, "Asha Menon");
  await page.goto("/inventory?q=moxifloxacin");
  const first = page.locator("tbody tr").first();
  await expect(first).toContainText("Moxifloxacin 0.5% Eye Drops 5ml");
  await page.getByRole("combobox").filter({ hasText: "All batches" }).selectOption("expired");
  await page.getByPlaceholder(/Search medicine, SKU/).fill("");
  const expired = page.getByRole("row", { name: /PA2405/ });
  await expect(expired).toContainText("Expired");
  await expect(expired).toContainText(/Expired 12 days ago/);
  await expect(expired).not.toContainText("₹0.00");
});
