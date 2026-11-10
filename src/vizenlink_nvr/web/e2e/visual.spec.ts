import { test, expect } from "@playwright/test";

const SIGNED_IN_ROUTES = [
  "/",
  "/playback",
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
] as const;

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
] as const;

const THEMES = ["light", "dark"] as const;

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
          await page.addInitScript((selectedTheme) => {
            localStorage.setItem("nvr_theme", selectedTheme);
          }, theme);

          await page.goto(route);

          // Wait for top-bar heading or page heading
          await page.locator("header h1, h1").first().waitFor({ state: "visible", timeout: 15_000 });

          // Check no horizontal scroll
          const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
          expect(
            scrollWidth,
            `Horizontal overflow on ${route} (${theme}, ${width}px): ${scrollWidth} > ${width}`
          ).toBeLessThanOrEqual(width);

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

        await page.addInitScript((selectedTheme) => {
          localStorage.setItem("nvr_theme", selectedTheme);
        }, theme);

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

