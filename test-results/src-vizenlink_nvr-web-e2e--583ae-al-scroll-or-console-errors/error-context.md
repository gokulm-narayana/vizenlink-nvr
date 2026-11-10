# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: src/vizenlink_nvr/web/e2e/visual.spec.ts >> Visual backstop across routes, themes and viewports >> /dashboard (light, 1440px) renders without horizontal scroll or console errors
- Location: src/vizenlink_nvr/web/e2e/visual.spec.ts:27:9

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/dashboard", waiting until "load"

```

# Test source

```ts
  1   | import { test, expect } from "@playwright/test";
  2   | 
  3   | const SIGNED_IN_ROUTES = [
  4   |   "/",
  5   |   "/playback",
  6   |   "/events",
  7   |   "/gallery",
  8   |   "/dashboard",
  9   |   "/cameras",
  10  |   "/cameras/add",
  11  |   "/users",
  12  |   "/devices",
  13  |   "/profile",
  14  | ] as const;
  15  | 
  16  | const VIEWPORTS = [
  17  |   { width: 1440, height: 900 },
  18  |   { width: 390, height: 844 },
  19  | ] as const;
  20  | 
  21  | const THEMES = ["light", "dark"] as const;
  22  | 
  23  | test.describe("Visual backstop across routes, themes and viewports", () => {
  24  |   for (const route of SIGNED_IN_ROUTES) {
  25  |     for (const theme of THEMES) {
  26  |       for (const { width, height } of VIEWPORTS) {
  27  |         test(`${route} (${theme}, ${width}px) renders without horizontal scroll or console errors`, async ({
  28  |           page,
  29  |         }, testInfo) => {
  30  |           const errors: string[] = [];
  31  | 
  32  |           page.on("pageerror", (err) => {
  33  |             errors.push(`PageError: ${err.message}`);
  34  |           });
  35  | 
  36  |           page.on("console", (msg) => {
  37  |             if (msg.type() === "error") {
  38  |               const text = msg.text();
  39  |               // Ignore only /cam/ WHEP connection failures (no MediaMTX in e2e)
  40  |               if (text.includes("/cam/") || (text.includes("Failed to load resource") && text.includes("/cam/"))) {
  41  |                 return;
  42  |               }
  43  |               errors.push(`ConsoleError: ${text}`);
  44  |             }
  45  |           });
  46  | 
  47  |           await page.setViewportSize({ width, height });
  48  | 
  49  |           // Set theme before navigation
  50  |           await page.addInitScript((selectedTheme) => {
  51  |             localStorage.setItem("nvr_theme", selectedTheme);
  52  |             if (selectedTheme === "dark") {
  53  |               document.documentElement.classList.add("dark");
  54  |             } else {
  55  |               document.documentElement.classList.remove("dark");
  56  |             }
  57  |           }, theme);
  58  | 
> 59  |           await page.goto(route);
      |                      ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  60  | 
  61  |           // Wait for top-bar heading or page heading
  62  |           await page.locator("header h1, h1").first().waitFor({ state: "visible", timeout: 15_000 });
  63  | 
  64  |           // Check no horizontal scroll
  65  |           const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  66  |           expect(
  67  |             scrollWidth,
  68  |             `Horizontal overflow on ${route} (${theme}, ${width}px): ${scrollWidth} > ${width}`
  69  |           ).toBeLessThanOrEqual(width);
  70  | 
  71  |           // Check no unexpected console errors
  72  |           expect(
  73  |             errors,
  74  |             `Unexpected console errors on ${route} (${theme}, ${width}px)`
  75  |           ).toEqual([]);
  76  | 
  77  |           // Attach full page screenshot
  78  |           const screenshot = await page.screenshot({ fullPage: true });
  79  |           const slug = route === "/" ? "root" : route.replace(/^\//, "").replace(/\//g, "-");
  80  |           await testInfo.attach(`${slug}-${theme}-${width}.png`, {
  81  |             body: screenshot,
  82  |             contentType: "image/png",
  83  |           });
  84  |         });
  85  |       }
  86  |     }
  87  |   }
  88  | 
  89  |   // Signed out /login route
  90  |   for (const theme of THEMES) {
  91  |     for (const { width, height } of VIEWPORTS) {
  92  |       test(`/login (${theme}, ${width}px) renders without horizontal scroll or console errors`, async ({
  93  |         browser,
  94  |       }, testInfo) => {
  95  |         // Create an unauthenticated context without storageState
  96  |         const context = await browser.newContext({
  97  |           storageState: undefined,
  98  |           viewport: { width, height },
  99  |         });
  100 |         const page = await context.newPage();
  101 | 
  102 |         const errors: string[] = [];
  103 | 
  104 |         page.on("pageerror", (err) => {
  105 |           errors.push(`PageError: ${err.message}`);
  106 |         });
  107 | 
  108 |         page.on("console", (msg) => {
  109 |           if (msg.type() === "error") {
  110 |             const text = msg.text();
  111 |             if (text.includes("/cam/") || (text.includes("Failed to load resource") && text.includes("/cam/"))) {
  112 |               return;
  113 |             }
  114 |             errors.push(`ConsoleError: ${text}`);
  115 |           }
  116 |         });
  117 | 
  118 |         await page.addInitScript((selectedTheme) => {
  119 |           localStorage.setItem("nvr_theme", selectedTheme);
  120 |           if (selectedTheme === "dark") {
  121 |             document.documentElement.classList.add("dark");
  122 |           } else {
  123 |             document.documentElement.classList.remove("dark");
  124 |           }
  125 |         }, theme);
  126 | 
  127 |         await page.goto("/login");
  128 | 
  129 |         // Wait for login form
  130 |         await page.locator("form").first().waitFor({ state: "visible", timeout: 15_000 });
  131 | 
  132 |         const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  133 |         expect(
  134 |           scrollWidth,
  135 |           `Horizontal overflow on /login (${theme}, ${width}px): ${scrollWidth} > ${width}`
  136 |         ).toBeLessThanOrEqual(width);
  137 | 
  138 |         expect(
  139 |           errors,
  140 |           `Unexpected console errors on /login (${theme}, ${width}px)`
  141 |         ).toEqual([]);
  142 | 
  143 |         const screenshot = await page.screenshot({ fullPage: true });
  144 |         await testInfo.attach(`login-${theme}-${width}.png`, {
  145 |           body: screenshot,
  146 |           contentType: "image/png",
  147 |         });
  148 | 
  149 |         await context.close();
  150 |       });
  151 |     }
  152 |   }
  153 | });
  154 | 
  155 | 
```