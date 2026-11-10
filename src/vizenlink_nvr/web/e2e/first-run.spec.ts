import { test, expect } from "@playwright/test";
import { E2E_OWNER, absRecordingsDir } from "./fixtures";

test.describe("First-run setup", () => {
  test("first-run setup from a deep link lands on live @smoke", async ({ page }) => {
    // 1. Open /playback?camera=X; expect the URL to be /setup
    await page.goto("/playback?camera=X");
    await expect(page).toHaveURL(/\/setup$/);

    // 2. Fill Owner username, Password, Confirm password, leave the browser time zone,
    // set the storage dir to the absolute .e2e/fresh/recordings, and tick Allow recordings on the system disk
    await page.fill("#owner_username", E2E_OWNER.username);
    await page.fill("#password", E2E_OWNER.password);
    await page.fill("#confirm_password", E2E_OWNER.confirmPassword);

    const recordingsDir = absRecordingsDir("fresh");
    await page.fill("#storage_path", recordingsDir);
    await page.click("#allow_system_disk");

    // 3. Click Create owner account
    await page.click('button:has-text("Create owner account")');

    // 4. Expect the URL / and the top-bar heading "Live"
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1, name: "Live View" })).toBeVisible();
  });
});
