import { test, expect } from "@playwright/test";

const SIGNED_IN_ROUTES = [
  "/",
  "/live",
  "/playback",
  "/playback/compare",
  "/search",
  "/assistant",
  "/events",
  "/gallery",
  "/dashboard",
  "/cameras",
  "/cameras/add",
  "/users",
  "/devices",
  "/profile",
  "/settings",
  "/settings/recording",
  "/settings/storage",
  "/settings/audit",
  "/settings/users",
  "/settings/devices",
] as const;

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
] as const;

const THEMES = ["light", "dark"] as const;

for (const viewport of [...VIEWPORTS, { width: 320, height: 480 }]) {
  test(`keeps alert filters below the header while scrolling at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const timestamp = new Date().toISOString();
    const items = Array.from({ length: 24 }, (_, index) => ({
      id: index + 1,
      camera_serial: "DEMO",
      event_type: "motion",
      source: "camera",
      start_time: timestamp,
      created_at: timestamp,
      is_locked: false,
      clock_sync_state: "synced",
    }));
    await page.route("**/api/v1/events?*", (route) => route.fulfill({
      json: { items, total: items.length, limit: 50, offset: 0 },
    }));

    await page.goto("/events");
    await expect(page.getByText("Total events:")).toHaveText("Total events: 24");
    await page.mouse.move(viewport.width / 2, viewport.height - 20);
    await page.mouse.wheel(0, 700);

    const filters = page.getByRole("region", { name: "Alert filters and actions" });
    await expect.poll(() => filters.evaluate((element) => {
      const header = document.querySelector(".workspace-header")?.getBoundingClientRect();
      const bar = element.getBoundingClientRect();
      return Boolean(header && window.scrollY > 0 && Math.abs(bar.top - header.bottom) < 2
        && bar.height <= window.innerHeight * 0.45 + 1);
    })).toBe(true);
  });
}

test.describe("Mobile device pairing layout", () => {
  for (const viewport of [...VIEWPORTS, { width: 320, height: 480 }]) {
    test(`keeps the full pairing code and controls in reach at ${viewport.width}px`, async ({ page }) => {
      const pairingCode = "0123456789abcdef".repeat(2);
      await page.setViewportSize(viewport);
      await page.route("**/api/v1/mobile/qr/init", (route) => route.fulfill({
        json: {
          pairing_code: pairingCode,
          qr_payload: JSON.stringify({ host: "recorder.local", pairing_code: pairingCode }),
          expires_at: new Date(Date.now() + 300_000).toISOString(),
        },
      }));

      await page.goto("/devices");
      await page.getByRole("button", { name: "Pair mobile device" }).first().click();
      const dialog = page.getByRole("dialog", { name: "Pair mobile device" });
      const qr = dialog.getByRole("img", { name: "Pairing QR code" });
      const code = dialog.getByText(pairingCode, { exact: true });
      const copy = dialog.getByRole("button", { name: "Copy pairing code" });
      await expect(qr).toBeVisible();

      await expect.poll(async () => {
        const [frame, ...contents] = await Promise.all([
          dialog.boundingBox(), qr.boundingBox(), code.boundingBox(), copy.boundingBox(),
        ]);
        if (!frame || contents.some((box) => !box)) return false;
        return frame.x > 0 && frame.y >= 0 && frame.x + frame.width < viewport.width
          && frame.y + frame.height <= viewport.height
          && contents.every((box) => box && box.x >= frame.x && box.x + box.width <= frame.x + frame.width)
          && await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth);
      }).toBe(true);

      const close = dialog.getByRole("button", { name: "Close pairing" });
      await close.scrollIntoViewIfNeeded();
      await expect(close).toBeInViewport();
      await close.click();
      await expect(dialog).toBeHidden();
    });
  }
});

test.describe("Visual backstop across routes, themes and viewports", () => {
  for (const route of SIGNED_IN_ROUTES) {
    for (const theme of THEMES) {
      for (const { width, height } of VIEWPORTS) {
        test(`${route} (${theme}, ${width}px) renders without horizontal scroll or console errors`, async ({
          page,
        }, testInfo) => {
          const errors: string[] = [];

          page.on("pageerror", (err) => {
            errors.push(`PageError: ${err.message}`);
          });

          page.on("console", (msg) => {
            if (msg.type() === "error") {
              const text = msg.text();
              const url = msg.location()?.url || "";
              // Ignore only /cam/ WHEP connection failures and upstream 502s (no MediaMTX / physical cameras in e2e)
              if (
                text.includes("/cam/") ||
                url.includes("/cam/") ||
                text.includes("502 (Bad Gateway)")
              ) {
                return;
              }
              errors.push(`ConsoleError: ${text}`);
            }
          });

          await page.setViewportSize({ width, height });

          // Set theme before navigation
          expect((await page.request.patch("/api/v1/auth/preferences", { data: { theme } })).ok()).toBe(true);

          await page.goto(route);

          // Wait for top-bar heading or page heading
          await page.locator("header h1, h1").first().waitFor({ state: "visible", timeout: 15_000 });

          // Check no horizontal scroll
          const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
          expect(
            scrollWidth,
            `Horizontal overflow on ${route} (${theme}, ${width}px): ${scrollWidth} > ${width}`
          ).toBeLessThanOrEqual(width);
          const mainOverflow = await page.locator("#main").evaluate((main) => main.scrollWidth - main.clientWidth);
          expect(mainOverflow, `Horizontal overflow in the main content of ${route}`).toBeLessThanOrEqual(0);

          // Check no unexpected console errors
          expect(
            errors,
            `Unexpected console errors on ${route} (${theme}, ${width}px)`
          ).toEqual([]);

          // Attach full page screenshot
          const screenshot = await page.screenshot({ fullPage: true });
          const slug = route === "/" ? "root" : route.replace(/^\//, "").replace(/\//g, "-");
          await testInfo.attach(`${slug}-${theme}-${width}.png`, {
            body: screenshot,
            contentType: "image/png",
          });
        });
      }
    }
  }

  // Signed out /login route
  for (const theme of THEMES) {
    for (const { width, height } of VIEWPORTS) {
      test(`/login (${theme}, ${width}px) renders without horizontal scroll or console errors`, async ({
        browser,
      }, testInfo) => {
        // Create an unauthenticated context without storageState
        const context = await browser.newContext({
          baseURL: "http://127.0.0.1:8766",
          storageState: undefined,
          viewport: { width, height },
        });
        const page = await context.newPage();

        const errors: string[] = [];

        page.on("pageerror", (err) => {
          errors.push(`PageError: ${err.message}`);
        });

        page.on("console", (msg) => {
          if (msg.type() === "error") {
            const text = msg.text();
            const url = msg.location()?.url || "";
            if (
              text.includes("/cam/") ||
              url.includes("/cam/") ||
              text.includes("502 (Bad Gateway)")
            ) {
              return;
            }
            errors.push(`ConsoleError: ${text}`);
          }
        });

        await page.emulateMedia({ colorScheme: theme });

        await page.goto("/login");

        // Wait for login form
        await page.locator("form").first().waitFor({ state: "visible", timeout: 15_000 });

        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
        expect(
          scrollWidth,
          `Horizontal overflow on /login (${theme}, ${width}px): ${scrollWidth} > ${width}`
        ).toBeLessThanOrEqual(width);

        expect(
          errors,
          `Unexpected console errors on /login (${theme}, ${width}px)`
        ).toEqual([]);

        const screenshot = await page.screenshot({ fullPage: true });
        await testInfo.attach(`login-${theme}-${width}.png`, {
          body: screenshot,
          contentType: "image/png",
        });

        await context.close();
      });
    }
  }
});

