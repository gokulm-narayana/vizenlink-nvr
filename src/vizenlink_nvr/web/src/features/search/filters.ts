import { getZoneOffsetMs, zonedDayBounds } from "@/lib/time";
import { toIsoDate } from "@/lib/timeline";

function exactTime(value: string, zone: string): number | undefined {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value)) return;
  const wallClock = Date.parse(`${value}Z`);
  if (!Number.isFinite(wallClock) || new Date(wallClock).toISOString().slice(0, value.length) !== value) return;

  const day = 86_400_000;
  const offsets = new Set([-day, 0, day].map(delta => getZoneOffsetMs(new Date(wallClock + delta), zone)));
  const matches = [...offsets].map(offset => wallClock - offset).filter(instant =>
    instant + getZoneOffsetMs(new Date(instant), zone) === wallClock,
  );
  // Repeated wall times use their first occurrence. Skipped times have no matching instant.
  return matches.length ? Math.min(...matches) : undefined;
}

export function searchWindow(range: string, zone: string, from?: string, to?: string, now = new Date()): { start?: string; end?: string; error?: string } {
  if (range === "all") return {};
  if (range === "exact") {
    if (!from || !to) return { error: "Choose a start and end time." };
    const start = exactTime(from, zone);
    const end = exactTime(to, zone);
    if (start === undefined || end === undefined) return { error: `Choose valid local times in ${zone}.` };
    if (end <= start) return { error: "End time must be after start time." };
    return { start: new Date(start).toISOString(), end: new Date(end).toISOString() };
  }
  if (range === "custom") {
    if (!from || !to) return { error: "Choose a start and end date." };
    const validDate = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
    if (!validDate(from) || !validDate(to)) return { error: "Choose valid calendar dates." };
    if (to < from) return { error: "End date must be on or after start date." };
    return { start: zonedDayBounds(from, zone)[0].toISOString(), end: zonedDayBounds(to, zone)[1].toISOString() };
  }
  if (range === "today" || range === "yesterday") {
    const today = toIsoDate(now, zone);
    const day = range === "today" ? today : new Date(Date.parse(today + "T12:00:00Z") - 86400000).toISOString().slice(0, 10);
    const [start, end] = zonedDayBounds(day, zone);
    return { start: start.toISOString(), end: end.toISOString() };
  }
  const seconds = range === "hour" ? 3600 : range === "week" ? 604800 : 86400;
  return { start: new Date(now.getTime() - seconds * 1000).toISOString(), end: now.toISOString() };
}
