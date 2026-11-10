import { useAuthStatus } from "./queries";

export function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function useSiteTimeZone(): string {
  const { data } = useAuthStatus();
  return data?.site_timezone || getBrowserTimeZone();
}

/**
 * Returns the offset in milliseconds between UTC and the wall clock in `zone`
 * at the given instant. (Positive when zone is ahead of UTC, e.g. +05:30 -> +19800000).
 */
export function getZoneOffsetMs(date: Date, zone: string): number {
  const d = new Date(date.getTime());
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  const parts = formatter.formatToParts(d);
  let year = 0;
  let month = 0;
  let day = 0;
  let hour = 0;
  let minute = 0;
  let second = 0;

  for (const part of parts) {
    if (part.type === "year") year = Number(part.value);
    else if (part.type === "month") month = Number(part.value);
    else if (part.type === "day") day = Number(part.value);
    else if (part.type === "hour") hour = Number(part.value);
    else if (part.type === "minute") minute = Number(part.value);
    else if (part.type === "second") second = Number(part.value);
  }

  // Handle midnight 24:00 edge case from Intl
  if (hour === 24) hour = 0;

  const wallClockAsUTC = Date.UTC(year, month - 1, day, hour, minute, second);
  // Subtract d's millisecond component to keep second alignment
  return wallClockAsUTC - (d.getTime() - d.getMilliseconds());
}

/**
 * Finds the exact UTC instant of local midnight (00:00:00) on `isoDate` (YYYY-MM-DD)
 * in the given IANA timezone.
 */
export function zonedDayStart(isoDate: string, zone: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  const targetUtcMidnight = Date.UTC(year, month - 1, day, 0, 0, 0, 0);

  // First guess: assume offset at target UTC midnight
  const offset1 = getZoneOffsetMs(new Date(targetUtcMidnight), zone);
  const guess1 = new Date(targetUtcMidnight - offset1);

  // Second pass: refine offset at guess1 instant (handles DST shifts)
  const offset2 = getZoneOffsetMs(guess1, zone);
  return new Date(targetUtcMidnight - offset2);
}

/**
 * Returns [start, end) where start is local midnight on isoDate in `zone`,
 * and end is local midnight on the following day in `zone`.
 * Accurately spans 23 hours on spring-forward and 25 hours on fall-back.
 */
export function zonedDayBounds(isoDate: string, zone: string): [Date, Date] {
  const start = zonedDayStart(isoDate, zone);

  const [y, m, d] = isoDate.split("-").map(Number);
  const nextDateObj = new Date(Date.UTC(y, m - 1, d + 1));
  const nextIso = nextDateObj.toISOString().slice(0, 10);
  const end = zonedDayStart(nextIso, zone);

  return [start, end];
}

export function formatDateTime(
  date: Date | string | number,
  zone: string,
  options?: Intl.DateTimeFormatOptions
): string {
  const d = typeof date === "object" ? date : new Date(date);
  const opts: Intl.DateTimeFormatOptions = {
    timeZone: zone,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    ...options,
  };
  return new Intl.DateTimeFormat("en-US", opts).format(d);
}

export function formatTime(
  date: Date | string | number,
  zone: string,
  options?: Intl.DateTimeFormatOptions
): string {
  const d = typeof date === "object" ? date : new Date(date);
  const opts: Intl.DateTimeFormatOptions = {
    timeZone: zone,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    ...options,
  };
  return new Intl.DateTimeFormat("en-US", opts).format(d);
}

export function zoneAbbreviation(date: Date | string | number, zone: string): string {
  const d = typeof date === "object" ? date : new Date(date);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    timeZoneName: "short",
  }).formatToParts(d);
  const tzPart = parts.find((p) => p.type === "timeZoneName");
  return tzPart?.value || zone;
}

export function formatRelative(
  date: Date | string | number,
  now: Date | string | number = new Date()
): string {
  const d = typeof date === "object" ? date.getTime() : new Date(date).getTime();
  const n = typeof now === "object" ? now.getTime() : new Date(now).getTime();
  const diffSec = Math.floor((n - d) / 1000);

  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec} sec ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hr ago`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
}