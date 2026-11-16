import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export const MIN_ZOOM = 1;
export const MAX_ZOOM = 8;

export interface ZoomState {
  scale: number;
  /** Pan offset in CSS pixels, applied before scaling. */
  x: number;
  y: number;
}

const HOME: ZoomState = { scale: 1, x: 0, y: 0 };

/** Keep the picture covering the tile: it may not be dragged past its own edge. */
export function clampZoom(next: ZoomState, width: number, height: number): ZoomState {
  const scale = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next.scale));
  if (scale === 1) return HOME;
  const maxX = (width * (scale - 1)) / 2;
  const maxY = (height * (scale - 1)) / 2;
  return {
    scale,
    x: Math.min(maxX, Math.max(-maxX, next.x)),
    y: Math.min(maxY, Math.max(-maxY, next.y)),
  };
}

/** Zoom towards a point (offset from the tile centre) so what is under the pointer stays there. */
export function zoomAt(current: ZoomState, scale: number, px: number, py: number, width: number, height: number): ZoomState {
  const clamped = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, scale));
  const ratio = clamped / current.scale;
  return clampZoom({ scale: clamped, x: px - (px - current.x) * ratio, y: py - (py - current.y) * ratio }, width, height);
}

/**
 * Digital zoom for a live tile: wheel or pinch-like trackpad scroll zooms at the pointer,
 * dragging pans, and the picture never leaves the tile. It only magnifies what the browser
 * already received; it does not change the camera or the recording.
 */
export function useDigitalZoom(container: RefObject<HTMLElement | null>, enabled: boolean) {
  const [zoom, setZoom] = useState<ZoomState>(HOME);
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const drag = useRef<{ id: number; startX: number; startY: number; x: number; y: number; moved: boolean } | null>(null);

  const size = useCallback(() => {
    const rect = container.current?.getBoundingClientRect();
    return { width: rect?.width ?? 0, height: rect?.height ?? 0, left: rect?.left ?? 0, top: rect?.top ?? 0 };
  }, [container]);

  const reset = useCallback(() => setZoom(HOME), []);
  const step = useCallback((factor: number) => {
    const { width, height } = size();
    setZoom((z) => zoomAt(z, z.scale * factor, 0, 0, width, height));
  }, [size]);

  // Leaving the large view puts the picture back.
  useEffect(() => {
    if (!enabled) setZoom(HOME);
  }, [enabled]);

  // React's onWheel is passive, so the page would scroll while zooming; attach natively.
  useEffect(() => {
    const element = container.current;
    if (!element || !enabled) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const { width, height, left, top } = size();
      const px = event.clientX - left - width / 2;
      const py = event.clientY - top - height / 2;
      const factor = Math.exp(-event.deltaY * 0.0015);
      setZoom((z) => zoomAt(z, z.scale * factor, px, py, width, height));
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [container, enabled, size]);

  const panHandlers = {
    onPointerDown: (event: React.PointerEvent<HTMLElement>) => {
      if (zoomRef.current.scale === 1 || event.button !== 0) return;
      if ((event.target as HTMLElement).closest("button, a, [role=menu]")) return;
      drag.current = { id: event.pointerId, startX: event.clientX, startY: event.clientY, x: zoomRef.current.x, y: zoomRef.current.y, moved: false };
      event.currentTarget.setPointerCapture?.(event.pointerId);
    },
    onPointerMove: (event: React.PointerEvent<HTMLElement>) => {
      const d = drag.current;
      if (!d || d.id !== event.pointerId) return;
      const dx = event.clientX - d.startX;
      const dy = event.clientY - d.startY;
      if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
      const { width, height } = size();
      setZoom((z) => clampZoom({ scale: z.scale, x: d.x + dx, y: d.y + dy }, width, height));
    },
    onPointerUp: (event: React.PointerEvent<HTMLElement>) => {
      if (drag.current?.id === event.pointerId) drag.current = null;
    },
    onPointerCancel: () => {
      drag.current = null;
    },
  };

  return { zoom, zoomed: zoom.scale > 1, reset, zoomIn: () => step(1.5), zoomOut: () => step(1 / 1.5), panHandlers };
}
