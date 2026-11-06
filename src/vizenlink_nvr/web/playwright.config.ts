import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  workers: 1,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "uv run python ../../../tools/e2e_serve.py --port 8765 --data-dir .e2e/fresh",
      url: "http://127.0.0.1:8765/api/v1/auth/status",
      reuseExistingServer: false,
      timeout: 120_000,
      env: { NVR_SECRETS_BACKEND: "file" },
    },
    {
      command: "uv run python ../../../tools/e2e_serve.py --port 8766 --data-dir .e2e/app",
      url: "http://127.0.0.1:8766/api/v1/auth/status",
      reuseExistingServer: false,
      timeout: 120_000,
      env: { NVR_SECRETS_BACKEND: "file" },
    },
  ],
  projects: [
    {
      name: "first-run",
      testMatch: /first-run\.spec\.ts/,
      use: {
        baseURL: "http://127.0.0.1:8765",
        ...devices["Desktop Chrome"],
      },
    },
    {
      name: "setup",
      testMatch: /global\.setup\.ts/,
      use: {
        baseURL: "http://127.0.0.1:8766",
      },
    },
    {
      name: "app",
      dependencies: ["setup"],
      testIgnore: [/first-run\.spec\.ts/, /global\.setup\.ts/],
      use: {
        baseURL: "http://127.0.0.1:8766",
        storageState: ".e2e/owner.json",
        ...devices["Desktop Chrome"],
      },
    },
  ],
});
