import { describe, it, expect, beforeEach } from "vitest";
import {
  zonedDayBounds,
  formatDateTime,
  formatTime,
  zoneAbbreviation,
  formatRelative,
} from "./time";

describe("Time and Timezone Helpers", () => {
  beforeEach(() => {
    process.env.TZ = "UTC";
  });

  it("zonedDayBounds handles DST spring-forward (23 hours)", () => {
    // 2026-03-08 in America/New_York is spring-forward
    const [start, end] = zonedDayBounds("2026-03-08", "America/New_York");
    const durationHours = (end.getTime() - start.getTime()) / (3600 * 1000);
    expect(durationHours).toBe(23);
    expect(start.toISOString()).toBe("2026-03-08T05:00:00.000Z");
    expect(end.toISOString()).toBe("2026-03-09T04:00:00.000Z");
  });

  it("zonedDayBounds handles DST fall-back (25 hours)", () => {
    // 2026-11-01 in America/New_York is fall-back
    const [start, end] = zonedDayBounds("2026-11-01", "America/New_York");
    const durationHours = (end.getTime() - start.getTime()) / (3600 * 1000);
    expect(durationHours).toBe(25);
    expect(start.toISOString()).toBe("2026-11-01T04:00:00.000Z");
    expect(end.toISOString()).toBe("2026-11-02T05:00:00.000Z");
  });

  it("zonedDayBounds handles standard 24 hour day in Asia/Kolkata starting at 18:30:00Z previous day", () => {
    const [start, end] = zonedDayBounds("2026-11-05", "Asia/Kolkata");
    const durationHours = (end.getTime() - start.getTime()) / (3600 * 1000);
    expect(durationHours).toBe(24);
    expect(start.toISOString()).toBe("2026-11-04T18:30:00.000Z");
    expect(end.toISOString()).toBe("2026-11-05T18:30:00.000Z");
  });

  it("formatDateTime formats in the given zone, not the host zone", () => {
    const instant = new Date("2026-11-05T00:00:00.000Z");
    // In UTC, it's Nov 5 00:00:00
    // In Asia/Kolkata (+05:30), it's Nov 5 05:30:00
    const formatted = formatDateTime(instant, "Asia/Kolkata");
    expect(formatted).toContain("Nov 5, 2026");
    expect(formatted).toContain("05:30:00");
  });

  it("zoneAbbreviation returns short zone name", () => {
    const winterInstant = new Date("2026-01-15T12:00:00.000Z");
    const summerInstant = new Date("2026-07-15T12:00:00.000Z");

    const nyWinter = zoneAbbreviation(winterInstant, "America/New_York");
    const nySummer = zoneAbbreviation(summerInstant, "America/New_York");
    expect(["EST", "GMT-5"]).toContain(nyWinter);
    expect(["EDT", "GMT-4"]).toContain(nySummer);

    const kolkata = zoneAbbreviation(winterInstant, "Asia/Kolkata");
    expect(["IST", "GMT+5:30"]).toContain(kolkata);
  });

  it("formatRelative formats relative time accurately", () => {
    const now = new Date("2026-11-05T12:00:00.000Z");
    const threeMinAgo = new Date("2026-11-05T11:57:00.000Z");
    expect(formatRelative(threeMinAgo, now)).toBe("3 min ago");

    const justNow = new Date("2026-11-05T11:59:58.000Z");
    expect(formatRelative(justNow, now)).toBe("just now");

    const twoHoursAgo = new Date("2026-11-05T10:00:00.000Z");
    expect(formatRelative(twoHoursAgo, now)).toBe("2 hr ago");
  });
});
