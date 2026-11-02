import { expect, test } from "@playwright/test";

test("homepage communicates the value proposition and has no horizontal scroll", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("From AI prototype to production-ready enterprise systems");
  await expect(page.getByText("Assess → Build → Run")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("all public pages render", async ({ page }) => {
  for (const path of ["/services", "/ai-readiness", "/ai-strategy", "/custom-ai-development", "/ai-automation", "/knowledge-assistants",
    "/sales-revenue", "/prototype-to-production", "/use-cases", "/case-studies", "/about", "/contact", "/book-discovery-call", "/login", "/register"]) {
    const res = await page.goto(path);
    expect(res?.status(), path).toBe(200);
    await expect(page.locator("h1").first()).toBeVisible();
  }
});

test("discovery call form validates and submits to the API", async ({ page }) => {
  await page.goto("/book-discovery-call");
  await page.getByRole("button", { name: "Request discovery call" }).click();
  await expect(page.getByText("Please enter your name")).toBeVisible();
  await page.getByLabel("Full name").fill("E2E Visitor");
  await page.getByLabel("Work email").fill(`visitor-${Date.now()}@example.com`);
  await page.getByLabel("Company").fill("E2E Industries");
  await page.getByRole("button", { name: "Request discovery call" }).click();
  await expect(page.getByText("Request received")).toBeVisible();
});
