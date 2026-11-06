import { test as setup, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { E2E_OWNER, absRecordingsDir } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const authFile = path.resolve(__dirname, "..", ".e2e", "owner.json");

setup("setup owner account", async ({ request }) => {
  const res = await request.post("/api/v1/auth/setup", {
    data: {
      owner_username: E2E_OWNER.username,
      owner_password: E2E_OWNER.password,
      timezone: "UTC",
      storage_path: absRecordingsDir("app"),
      allow_system_disk: true,
    },
  });
  expect(res.status()).toBe(200);
  await request.storageState({ path: authFile });
});
