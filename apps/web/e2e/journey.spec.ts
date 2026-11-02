import { expect, test } from "@playwright/test";

import { login } from "./helpers";

const ANSWER_INDEX = 2; // pick the third option for every question: a mid-range, valid profile

test("visitor registers, completes the readiness assessment and sees a deterministic report", async ({ page }) => {
  const email = `founder-${Date.now()}@e2e-co.example`;
  await page.goto("/register?next=assessment");
  await page.getByLabel("Full name").fill("Erin Example");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill("E2E-password-123");
  await page.getByLabel("Organisation").fill(`E2E Co ${Date.now()}`);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/portal\/assessments\//);

  await expect(page.getByText("About your organisation")).toBeVisible();
  await page.getByLabel("Reduce operational costs").check();
  await page.getByRole("button", { name: "Continue" }).click();

  for (let step = 0; step < 6; step++) {
    await expect(page.locator("fieldset").first()).toBeVisible();
    // answer every visible question, including conditional follow-ups that appear after answering
    for (let pass = 0; pass < 2; pass++) {
      const sets = page.locator("fieldset");
      const n = await sets.count();
      for (let i = 0; i < n; i++) {
        const options = sets.nth(i).locator("label");
        const count = await options.count();
        await options.nth(Math.min(ANSWER_INDEX, count - 1)).click();
      }
    }
    await page.getByRole("button", { name: "Continue" }).click();
  }
  await expect(page.getByText("Review and submit")).toBeVisible();
  await page.getByRole("button", { name: "Submit assessment" }).click();

  await expect(page.getByText("Overall AI readiness", { exact: true })).toBeVisible();
  await expect(page.getByText("/100").first()).toBeVisible();
  await expect(page.getByText("Prioritised AI opportunities")).toBeVisible();
  await expect(page.getByText("30 / 60 / 90 day plan")).toBeVisible();
  await expect(page.getByText("Executive summary")).toBeVisible({ timeout: 30_000 });
});

test("engineer sees live dashboard data, CRM and monitoring", async ({ page }) => {
  await login(page, "engineer@deploymind.example");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Mock AI mode")).toBeVisible();
  await page.getByRole("link", { name: "CRM" }).click();
  await expect(page.getByText("Acme Professional Services").first()).toBeVisible();
  await page.getByRole("link", { name: "Monitoring" }).click();
  await expect(page.getByText("Showing real telemetry")).toBeVisible();
  await page.getByLabel("Telemetry source").selectOption("demo");
  await expect(page.getByText("synthetic demo telemetry")).toBeVisible();
  await page.getByRole("link", { name: "Evaluations" }).click();
  await expect(page.getByText("Baseline - hybrid top_k=5")).toBeVisible();
});

test("customer asks the knowledge assistant and gets a cited answer", async ({ page }) => {
  await login(page, "customer@acme-ps.example");
  await page.getByRole("link", { name: "AI Assistant", exact: true }).click();
  await page.getByLabel("Question").fill("Who approves expense claims above 500 pounds?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.locator("p", { hasText: "require approval from a director" }).first()).toBeVisible();
  await expect(page.getByText("Sources", { exact: true }).last()).toBeVisible();
  await page.getByLabel("Question").fill("What is the share price target for next year?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText("Insufficient evidence").last()).toBeVisible();
});

test("customer sees proposal, project and incident history in the portal", async ({ page }) => {
  await login(page, "customer@acme-ps.example");
  await page.getByRole("link", { name: "Proposals", exact: true }).click();
  await expect(page.getByText("Accepted", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await page.getByText("Enquiry triage & knowledge assistant").first().click();
  await expect(page.getByText("Overall progress")).toBeVisible();
  await page.getByRole("link", { name: "Incident updates" }).click();
  await page.getByText("INC-0001").click();
  await expect(page.getByText("Mitigation deployed")).toBeVisible();
  await expect(page.getByText("AI incident analysis")).toHaveCount(0);
});

test("a customer of another tenant cannot open Acme's project by URL", async ({ page, request }) => {
  await login(page, "customer@acme-ps.example");
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await page.getByText("Enquiry triage & knowledge assistant").first().click();
  await expect(page).toHaveURL(/\/portal\/projects\//);
  const acmeProjectUrl = page.url();
  await page.getByRole("button", { name: "Sign out" }).click();

  await login(page, "customer@northwind-legal.example");
  await page.goto(acmeProjectUrl);
  await expect(page.getByText("Could not load this data")).toBeVisible();
  await expect(page.getByText("Enquiry triage & knowledge assistant")).toHaveCount(0);
});
