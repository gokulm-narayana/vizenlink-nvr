import { useEffect } from "react";
import { useLocation } from "react-router";

/**
 * Full screen is always requested on the whole page, never on one tile or the grid.
 * Menus, tooltips and dialogs are mounted on <body>; when a smaller element is the
 * browser's fullscreen element they are not drawn at all, so their buttons look dead.
 */
type FsDocument = Document & { webkitFullscreenElement?: Element | null; webkitExitFullscreen?: () => Promise<void> | void };
type FsElement = HTMLElement & { webkitRequestFullscreen?: () => Promise<void> | void };

export const WALL_PARAM = "wall";
/** With `fit=all` the full screen view ignores filters and picks the grid that shows every camera. */
export const FIT_PARAM = "fit";
export const WALL_PATH = `/live?${WALL_PARAM}=1&${FIT_PARAM}=all`;

export function fullscreenElement(): Element | null {
  const doc = document as FsDocument;
  return doc.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
}

/** Must be called from a click or key handler. A refusal is fine: the page still hides its chrome. */
export function enterPageFullscreen(): void {
  if (fullscreenElement()) return;
  const root = document.documentElement as FsElement;
  try {
    const request = root.requestFullscreen?.() ?? root.webkitRequestFullscreen?.();
    if (request && typeof request.catch === "function") void request.catch(() => undefined);
  } catch {
    // Not allowed here (iPhone Safari, embedded views).
  }
}

export function exitPageFullscreen(): void {
  if (!fullscreenElement()) return;
  const doc = document as FsDocument;
  try {
    const request = doc.exitFullscreen?.() ?? doc.webkitExitFullscreen?.();
    if (request && typeof request.catch === "function") void request.catch(() => undefined);
  } catch {
    // Already left.
  }
}

export function isWallLocation(pathname: string, search: string): boolean {
  return pathname === "/live" && new URLSearchParams(search).get(WALL_PARAM) === "1";
}

/** Leaves page full screen whenever the app is no longer on the full screen live view. */
export function useWallFullscreenGuard(): void {
  const { pathname, search } = useLocation();
  useEffect(() => {
    if (!isWallLocation(pathname, search) && fullscreenElement() === document.documentElement) exitPageFullscreen();
  }, [pathname, search]);
}
