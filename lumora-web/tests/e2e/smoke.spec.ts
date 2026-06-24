import { test, expect } from "@playwright/test";

// Smoke floor: every key surface loads and the access gate holds. Catches the
// most common regressions (a route white-screens, the gate breaks, the data
// API 500s) without asserting on volatile content.

test("landing renders with a headline and title", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1").first()).toBeVisible();
  await expect(page).toHaveTitle(/Lumora/);
});

test("enter page shows the invite field", async ({ page }) => {
  await page.goto("/enter");
  await expect(page.locator("#invite")).toBeVisible();
});

test("protected route redirects to the invite gate", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/enter/);
  await expect(page.locator("#invite")).toBeVisible();
});

test("whale-alerts API responds with alerts", async ({ request }) => {
  const res = await request.get("/api/whale-alerts");
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body).toHaveProperty("alerts");
});

test("heatmap API responds", async ({ request }) => {
  const res = await request.get(
    "/api/heatmap?source=live&symbol=BTCUSDT&exchange=binance_spot&timeframe=5m",
  );
  expect(res.ok()).toBeTruthy();
});
