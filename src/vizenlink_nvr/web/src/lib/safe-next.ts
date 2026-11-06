/**
 * Validates a redirect target path against open-redirect and forbidden route rules.
 *
 * A valid next target must:
 * - Start with a single "/" and not start with "//"
 * - Not contain any backslash character ("\")
 * - Not start with "/login", "/setup", or "/api"
 *
 * Returns the validated target string, or null if invalid or missing.
 */
export function safeNext(next?: string | null): string | null {
  if (!next || typeof next !== "string") {
    return null;
  }

  // Must start with single / and not //
  if (!next.startsWith("/") || next.startsWith("//")) {
    return null;
  }

  // Must not contain any backslash
  if (next.includes("\\")) {
    return null;
  }

  // Must not target /login, /setup, or /api (exact match or path/query prefix)
  const isForbiddenPrefix = (prefix: string) =>
    next === prefix ||
    next.startsWith(prefix + "/") ||
    next.startsWith(prefix + "?");

  if (
    isForbiddenPrefix("/login") ||
    isForbiddenPrefix("/setup") ||
    isForbiddenPrefix("/api")
  ) {
    return null;
  }

  return next;
}
