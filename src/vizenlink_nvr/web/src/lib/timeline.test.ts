import { describe, it, expect } from "vitest";
import {
  getWindowRange,
  timeToPct,
  pctToTime,
  zoomAround,
  retentionSpan,
  nextZoom,
  ZOOM_LEVELS,
  type ZoomLevel,
} from "./timeline";

describe("lib/timeline", () => {
  describe("getWindowRange & DST", () => {
    it("returns 23 hours for America/New_York on 2026-03-08 spring-forward", () => {
      const [start, end] = getWindowRange("2026-03-08", "24h", "2026-03-08T12:00:00Z", "America/New_York");
      const durationHours = (end.getTime() - start.getTime()) / (3600 * 1000);
      expect(durationHours).toBe(23);
    });

    it("returns 25 hours for America/New_York on 2026-11-01 fall-back", () => {
      const [start, end] = getWindowRange("2026-11-01", "24h", "2026-11-01T12:00:00Z", "America/New_York");
      const durationHours = (end.getTime() - start.getTime()) / (3600 * 1000);
      expect(durationHours).toBe(25);
    });

    it("returns standard 24 hours for Asia/Kolkata", () => {
      const [start, end] = getWindowRange("2026-06-15", "24h", "2026-06-15T12:00:00Z", "Asia/Kolkata");
      const durationHours = (end.getTime() - start.getTime()) / (3600 * 1000);
      expect(durationHours).toBe(24);
    });

    it("clamps 12h, 4h and 1h zoom windows to day bounds", () => {
      const [dayStart, dayEnd] = getWindowRange("2026-06-15", "24h", "2026-06-15T00:00:00Z", "UTC");

      // Anchor at day start
      const [start12, end12] = getWindowRange("2026-06-15", "12h", dayStart, "UTC");
      expect(start12.getTime()).toBe(dayStart.getTime());
      expect(end12.getTime() - start12.getTime()).toBe(12 * 3600 * 1000);

      // Anchor at day end
      const [start4, end4] = getWindowRange("2026-06-15", "4h", dayEnd, "UTC");
      expect(end4.getTime()).toBe(dayEnd.getTime());
      expect(end4.getTime() - start4.getTime()).toBe(4 * 3600 * 1000);
    });
  });

  describe("timeToPct & pctToTime", () => {
    it("round-trips within 1 second at any zoom level", () => {
      for (const zoom of ZOOM_LEVELS) {
        const range = getWindowRange("2026-06-15", zoom, "2026-06-15T12:00:00Z", "UTC");
        const testPcts = [0, 15.5, 50, 75.33, 100];

        for (const pct of testPcts) {
          const time = pctToTime(pct, range);
          const computedPct = timeToPct(time, range);
          expect(Math.abs(computedPct - pct)).toBeLessThan(0.01);

          const roundTripTime = pctToTime(computedPct, range);
          expect(Math.abs(roundTripTime.getTime() - time.getTime())).toBeLessThanOrEqual(1000);
        }
      }
    });
  });

  describe("zoomAround", () => {
    it("keeps cursor time at same percentage position unless clamped at edge", () => {
      const initialRange = getWindowRange("2026-06-15", "24h", "2026-06-15T12:00:00Z", "UTC");
      const cursorTime = new Date(initialRange[0].getTime() + 10 * 3600 * 1000); // 10h in
      const initialPct = timeToPct(cursorTime, initialRange);

      // Zoom in to 12h
      const newRange = zoomAround(initialRange, cursorTime, "12h", "2026-06-15", "UTC");
      const newPct = timeToPct(cursorTime, newRange);

      expect(Math.abs(newPct - initialPct)).toBeLessThan(0.5);
    });

    it("clamps at day edges when zooming around edge anchor", () => {
      const initialRange = getWindowRange("2026-06-15", "24h", "2026-06-15T00:00:00Z", "UTC");
      const cursorTime = initialRange[0]; // Exactly at day start

      const newRange = zoomAround(initialRange, cursorTime, "4h", "2026-06-15", "UTC");
      expect(newRange[0].getTime()).toBe(initialRange[0].getTime());
      expect(newRange[1].getTime() - newRange[0].getTime()).toBe(4 * 3600 * 1000);
    });
  });

  describe("retentionSpan", () => {
    it("returns null when retentionDays is null or 0", () => {
      const range = getWindowRange("2026-06-15", "24h", "2026-06-15T12:00:00Z", "UTC");
      const now = new Date("2026-06-20T12:00:00Z");

      expect(retentionSpan(range, null, now)).toBeNull();
      expect(retentionSpan(range, 0, now)).toBeNull();
    });

    it("returns null when entire window is newer than retention cutoff", () => {
      // 7 days retention, window is yesterday
      const range = getWindowRange("2026-06-19", "24h", "2026-06-19T12:00:00Z", "UTC");
      const now = new Date("2026-06-20T12:00:00Z");

      expect(retentionSpan(range, 7, now)).toBeNull();
    });

    it("returns full window when entire window is older than retention cutoff", () => {
      // 7 days retention, window is 30 days ago
      const range = getWindowRange("2026-05-15", "24h", "2026-05-15T12:00:00Z", "UTC");
      const now = new Date("2026-06-20T12:00:00Z");

      const span = retentionSpan(range, 7, now);
      expect(span).not.toBeNull();
      expect(span![0].getTime()).toBe(range[0].getTime());
      expect(span![1].getTime()).toBe(range[1].getTime());
    });

    it("clips retention cutoff when it falls inside the window", () => {
      // 7 days retention: cutoff is 2026-06-13 12:00:00
      const now = new Date("2026-06-20T12:00:00Z");
      const range = getWindowRange("2026-06-13", "24h", "2026-06-13T12:00:00Z", "UTC");

      const span = retentionSpan(range, 7, now);
      expect(span).not.toBeNull();
      expect(span![0].getTime()).toBe(range[0].getTime());
      expect(span![1].getTime()).toBe(new Date("2026-06-13T12:00:00Z").getTime());
    });
  });

  describe("nextZoom", () => {
    it("cycles in and out correctly and clamps at bounds", () => {
      expect(nextZoom("24h", "in")).toBe("12h");
      expect(nextZoom("12h", "in")).toBe("4h");
      expect(nextZoom("4h", "in")).toBe("1h");
      expect(nextZoom("1h", "in")).toBe("1h");

      expect(nextZoom("1h", "out")).toBe("4h");
      expect(nextZoom("4h", "out")).toBe("12h");
      expect(nextZoom("12h", "out")).toBe("24h");
      expect(nextZoom("24h", "out")).toBe("24h");
    });
  });
});
