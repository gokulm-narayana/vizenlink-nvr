export function resolveTimezones(): { list: string[]; defaultTz: string } {
  let defaultTz = "UTC";
  try {
    const resolved = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (resolved) {
      defaultTz = resolved;
    }
  } catch {
    // fallback to UTC
  }

  let list: string[] = [];
  try {
    const intlAny = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
    if (typeof intlAny.supportedValuesOf === "function") {
      list = intlAny.supportedValuesOf("timeZone");
    }
  } catch {
    // fallback
  }

  if (list.length === 0) {
    list = [defaultTz, "UTC"].filter((v, i, a) => a.indexOf(v) === i);
  } else if (!list.includes(defaultTz)) {
    list = [defaultTz, ...list].sort();
  }

  return { list, defaultTz };
}
