import { test, expect } from "@playwright/test";
import { E2E_OWNER } from "./fixtures";

test.use({ storageState: { cookies: [], origins: [] } });

test.describe("Auth routing e2e", () => {
  test("deep-link next round trip preserves path and query params @smoke", async ({ page }) => {
    // (b, @smoke) Open /playback?camera=X&t=T.
    // Expect URL path and search to be exactly /login?next=%2Fplayback%3Fcamera%3DX%26t%3DT.
    await page.goto("/playback?camera=X&t=T");
    await expect(page).toHaveURL("/login?next=%2Fplayback%3Fcamera%3DX%26t%3DT");

    // Sign in. Expect the URL to be /playback?camera=X&t=T.
    await page.fill("#username", E2E_OWNER.username);
    await page.fill("#password", E2E_OWNER.password);
    await page.click('button:has-text("Sign in")');
    await expect(page).toHaveURL("/playback?camera=X&t=T");
  });

  test("open-redirect attempt is rejected and defaults to /", async ({ page }) => {
    // (c) Open /login?next=%2F%2Fevil.example.
    await page.goto("/login?next=%2F%2Fevil.example");

    // Sign in. Expect path / on same origin.
    await page.fill("#username", E2E_OWNER.username);
    await page.fill("#password", E2E_OWNER.password);
    await page.click('button:has-text("Sign in")');
    await expect(page).toHaveURL("/");
  });

  test("signed-in user visiting /login redirects to /", async ({ page }) => {
    // (d) Sign in, then open /login. Expect /.
    await page.goto("/login");
    await page.fill("#username", E2E_OWNER.username);
    await page.fill("#password", E2E_OWNER.password);
    await page.click('button:has-text("Sign in")');
    await expect(page).toHaveURL("/");

    await page.goto("/login");
    await expect(page).toHaveURL("/");
  });

  test("sign out redirects to /login with no next parameter", async ({ page }) => {
    // (e) Sign in, open the user menu (Account menu button), click "Sign out".
    // Expect path /login with no next parameter.
    await page.goto("/login");
    await page.fill("#username", E2E_OWNER.username);
    await page.fill("#password", E2E_OWNER.password);
    await page.click('button:has-text("Sign in")');
    await expect(page).toHaveURL("/");

    await page.getByRole("button", { name: /Account menu/i }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
