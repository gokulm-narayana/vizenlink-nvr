import { zonedDayBounds } from "./time";

export type ZoomLevel = "24h" | "12h" | "4h" | "1h";
export const ZOOM_LEVELS: ZoomLevel[] = ["24h", "12h", "4h", "1h"];

export interface TimelineSegment {
  id: number;
  start_time: string;
  end_time: string;
  is_protected: boolean;
  duration_seconds: number;
}

export interface TimelineOutage {
  id: number;
  started_at: string;
  ended_at?: string | null;
  duration_seconds?: number | null;
  reason?: string | null;
}

export interface TimelineEvent {
  id: number;
  event_type: string;
  start_time: string;
  end_time?: string | null;
  is_locked: boolean;
}

function toIsoDate(d: Date | string, zone: string): string {
  if (typeof d === "string" && /^\d{4}-\d{2}-\d{2}$/.test(d)) {
    return d;
  }
  const dateObj = typeof d === "string" ? new Date(d) : d;
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(dateObj); // "YYYY-MM-DD"
}

export function nextZoom(current: ZoomLevel, direction: "in" | "out"): ZoomLevel {
  const index = ZOOM_LEVELS.indexOf(current);
  if (index === -1) return "24h";

  if (direction === "in") {
    const nextIdx = Math.min(index + 1, ZOOM_LEVELS.length - 1);
    return ZOOM_LEVELS[nextIdx];
  } else {
    const prevIdx = Math.max(index - 1, 0);
    return ZOOM_LEVELS[prevIdx];
  }
}

export function getWindowRange(
  day: Date | string,
  zoom: ZoomLevel,
  anchor: Date | string,
  zone: string
): [Date, Date] {
  const isoDate = toIsoDate(day, zone);
  const [dayStart, dayEnd] = zonedDayBounds(isoDate, zone);

  if (zoom === "24h") {
    return [dayStart, dayEnd];
  }

  const durationHours = zoom === "12h" ? 12 : zoom === "4h" ? 4 : 1;
  const durationMs = durationHours * 3600 * 1000;

  const anchorDate = typeof anchor === "string" ? new Date(anchor) : anchor;
  let centerMs = anchorDate.getTime();
  if (isNaN(centerMs) || centerMs < dayStart.getTime() || centerMs > dayEnd.getTime()) {
    centerMs = dayStart.getTime() + durationMs / 2;
  }

  let winStart = new Date(centerMs - durationMs / 2);
  let winEnd = new Date(centerMs + durationMs / 2);

  if (winStart < dayStart) {
    winStart = dayStart;
    winEnd = new Date(dayStart.getTime() + durationMs);
  }
  if (winEnd > dayEnd) {
    winEnd = dayEnd;
    winStart = new Date(dayEnd.getTime() - durationMs);
  }

  return [winStart, winEnd];
}

export function timeToPct(
  time: Date | string | number,
  windowRange: [Date, Date]
): number {
  const [winStart, winEnd] = windowRange;
  const t = typeof time === "number" ? time : new Date(time).getTime();
  const totalMs = Math.max(1, winEnd.getTime() - winStart.getTime());
  return Math.max(0, Math.min(100, ((t - winStart.getTime()) / totalMs) * 100));
}

export function pctToTime(
  pct: number,
  windowRange: [Date, Date]
): Date {
  const [winStart, winEnd] = windowRange;
  const totalMs = Math.max(1, winEnd.getTime() - winStart.getTime());
  const clamped = Math.max(0, Math.min(100, pct));
  return new Date(winStart.getTime() + (clamped / 100) * totalMs);
}

export function zoomAround(
  range: [Date, Date],
  cursorTime: Date,
  nextZoomLevel: ZoomLevel,
  day: Date | string,
  zone: string
): [Date, Date] {
  const currentPct = timeToPct(cursorTime, range);
  const isoDate = toIsoDate(day, zone);
  const [dayStart, dayEnd] = zonedDayBounds(isoDate, zone);

  if (nextZoomLevel === "24h") {
    return [dayStart, dayEnd];
  }

  const durationHours = nextZoomLevel === "12h" ? 12 : nextZoomLevel === "4h" ? 4 : 1;
  const durationMs = durationHours * 3600 * 1000;

  const newStartMs = cursorTime.getTime() - (currentPct / 100) * durationMs;
  let startMs = newStartMs;
  let endMs = startMs + durationMs;

  if (startMs < dayStart.getTime()) {
    startMs = dayStart.getTime();
    endMs = Math.min(dayEnd.getTime(), startMs + durationMs);
  } else if (endMs > dayEnd.getTime()) {
    endMs = dayEnd.getTime();
    startMs = Math.max(dayStart.getTime(), endMs - durationMs);
  }

  return [new Date(startMs), new Date(endMs)];
}

export function retentionSpan(
  windowRange: [Date, Date],
  retentionDays: number | null,
  now: Date | number = new Date()
): [Date, Date] | null {
  if (retentionDays === null || retentionDays <= 0) {
    return null;
  }

  const [winStart, winEnd] = windowRange;
  const nowMs = typeof now === "number" ? now : now.getTime();
  const cutoffMs = nowMs - retentionDays * 24 * 3600 * 1000;

  if (cutoffMs <= winStart.getTime()) {
    return null;
  }

  if (cutoffMs >= winEnd.getTime()) {
    return [winStart, winEnd];
  }

  return [winStart, new Date(cutoffMs)];
}
