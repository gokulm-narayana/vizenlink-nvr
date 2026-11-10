import { test, expect } from "@playwright/test";

test.describe("16-camera 4x4 Live grid performance & style backstop", () => {
  test("16-camera 4x4 Live grid keeps main-thread long tasks within budget and renders without backdrop-blur or box-shadow", async ({
    request,
    page,
  }) => {
    // 1. Create 16 cameras PERF-01..PERF-16 through POST /api/v1/cameras
    for (let i = 1; i <= 16; i++) {
      const serial = `PERF-${String(i).padStart(2, "0")}`;
      const res = await request.post("/api/v1/cameras", {
        data: {
          serial,
          name: `Perf Camera ${i}`,
          host: "127.0.0.1",
          https_port: 443,
          username: "admin",
          password: "testpassword123",
          main_stream: {
            scheme: "rtsp",
            port: 554,
            path: `/stream${i}`,
            codec: "h264",
            width: 1920,
            height: 1080,
            transport: "tcp",
            profile_token: `Profile_${i}`,
            venc_token: `VideoEncoder_${i}`,
          },
        },
      });

      if (res.status() === 503) {
        throw new Error(
          "Launcher lost runtime vault (503 on POST /api/v1/cameras). Check e2e launcher."
        );
      }
      expect([201, 409]).toContain(res.status());
    }

    // 2. Set grid layout to 4x4 dimension and view mode to advanced
    // Install PerformanceObserver for longtask before load
    await page.addInitScript(() => {
      localStorage.setItem(
        "vizenlink_nvr_grid_layout_v1",
        JSON.stringify({ dimension: 4, page: 0, slotAssignments: {} })
      );
      localStorage.setItem("nvr_view_mode", "advanced");

      (window as any).__longTasks = [];
      try {
        const observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            (window as any).__longTasks.push({
              duration: entry.duration,
              startTime: entry.startTime,
            });
          }
        });
        observer.observe({ entryTypes: ["longtask"] });
      } catch (e) {
        console.warn("PerformanceObserver for longtask not supported", e);
      }
    });

    // 3. Open /
    await page.goto("/live"); // Phase 10: Multiview moved from / to /live

    // 4. Wait for all 16 tiles to render
    const tiles = page.locator('div[role="group"][aria-label*="Perf Camera"]');
    await expect(tiles).toHaveCount(16, { timeout: 20_000 });

    // 5. Collect long tasks for 5 s after 16th tile renders
    await page.waitForTimeout(5000);

    // 6. Assertions on long tasks:
    // No single long task exceeds 200 ms
    // Total blocking time (sum over tasks of duration - 50) stays under 500 ms
    const longTasks: Array<{ duration: number; startTime: number }> =
      await page.evaluate(() => (window as any).__longTasks || []);

    let totalBlockingTime = 0;
    for (const task of longTasks) {
      expect(
        task.duration,
        `Long task duration exceeds 200 ms: ${task.duration}ms`
      ).toBeLessThanOrEqual(200);
      if (task.duration > 50) {
        totalBlockingTime += task.duration - 50;
      }
    }

    expect(
      totalBlockingTime,
      `Total blocking time exceeds 500 ms: ${totalBlockingTime}ms`
    ).toBeLessThanOrEqual(500);

    // 7. Assertions on styles:
    // Every tile overlay chip has a computed backdrop-filter of 'none'
    // No tile has a box-shadow
    const computedStyles = await page.evaluate(() => {
      const tileEls = Array.from(
        document.querySelectorAll('div[role="group"][aria-label*="Perf Camera"]')
      );
      const tileBoxShadows = tileEls.map((el) => {
        const cs = window.getComputedStyle(el);
        return cs.boxShadow;
      });

      const chipEls = Array.from(
        document.querySelectorAll(
          'div[role="group"][aria-label*="Perf Camera"] .bg-video-overlay'
        )
      );
      const chipFilters = chipEls.map((el) => {
        const cs = window.getComputedStyle(el);
        return cs.backdropFilter || (cs as any).webkitBackdropFilter || "none";
      });

      return {
        tileCount: tileEls.length,
        chipCount: chipEls.length,
        tileBoxShadows,
        chipFilters,
      };
    });

    expect(computedStyles.tileCount).toBe(16);
    expect(computedStyles.chipCount).toBeGreaterThan(0);

    for (const shadow of computedStyles.tileBoxShadows) {
      expect(
        shadow === "none" || shadow === "" || shadow.includes("0px 0px 0px 0px")
      ).toBe(true);
    }

    for (const filter of computedStyles.chipFilters) {
      expect(filter).toBe("none");
    }
  });
});

