import { test, expect } from "@playwright/test";

test.describe("Shell sidebar e2e", () => {
  // Phase 10 (owner: "all screen sizes"): full sidebar from 1024px; tablets (768-1023px) default to the icon rail.
  const desktopWidths = [
    { width: 1280, smoke: true, expected: "expanded" },
    { width: 1024, smoke: false, expected: "expanded" },
    { width: 900, smoke: false, expected: "collapsed" },
    { width: 768, smoke: false, expected: "collapsed" },
  ];

  for (const { width, smoke, expected } of desktopWidths) {
    const title = `desktop sidebar is ${expected} by default at ${width}px on / and /dashboard${smoke ? " @smoke" : ""}`;
    test(title, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });

      // Open / with nvr_sidebar cleared
      await page.goto("/");
      await page.evaluate(() => localStorage.removeItem("nvr_sidebar"));
      await page.reload();

      const desktopSidebar = page.locator('div[data-slot="sidebar"][data-state]');
      await expect(desktopSidebar).toHaveAttribute("data-state", expected);

      // Repeat on /dashboard
      await page.goto("/dashboard");
      await expect(desktopSidebar).toHaveAttribute("data-state", expected);
    });
  }

  test("sidebar collapse persists across reload and viewport resize", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/");
    await page.evaluate(() => localStorage.removeItem("nvr_sidebar"));
    await page.reload();

    const desktopSidebar = page.locator('div[data-slot="sidebar"][data-state]');
    await expect(desktopSidebar).toHaveAttribute("data-state", "expanded");

    // Click Toggle sidebar
    await page.getByRole("button", { name: "Toggle sidebar" }).click();
    await expect(desktopSidebar).toHaveAttribute("data-state", "collapsed");

    // Reload: still collapsed
    await page.reload();
    await expect(desktopSidebar).toHaveAttribute("data-state", "collapsed");

    // Resize to 1440 and back to 768: still collapsed, and nvr_sidebar equals "collapsed"
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(desktopSidebar).toHaveAttribute("data-state", "collapsed");

    await page.setViewportSize({ width: 768, height: 900 });
    await expect(desktopSidebar).toHaveAttribute("data-state", "collapsed");

    const stored = await page.evaluate(() => localStorage.getItem("nvr_sidebar"));
    expect(stored).toBe("collapsed");
  });

  test("drawer below 768px opens without touching nvr_sidebar", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/");
    await page.evaluate(() => localStorage.removeItem("nvr_sidebar"));
    await page.reload();

    const beforeVal = await page.evaluate(() => localStorage.getItem("nvr_sidebar"));

    // Resize to 390px (mobile)
    await page.setViewportSize({ width: 390, height: 844 });

    // Click Toggle sidebar trigger
    await page.getByRole("button", { name: "Toggle sidebar" }).click();

    // Sheet dialog / drawer is visible
    const mobileSidebar = page.locator('[data-slot="sidebar"][data-mobile="true"]');
    await expect(mobileSidebar).toBeVisible();

    // Close the drawer with Escape
    await page.keyboard.press("Escape");
    await expect(mobileSidebar).not.toBeVisible();

    const afterVal = await page.evaluate(() => localStorage.getItem("nvr_sidebar"));
    expect(afterVal).toBe(beforeVal);
  });
});
