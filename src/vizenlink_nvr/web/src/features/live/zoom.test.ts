import { describe, expect, it } from "vitest";
import { clampZoom, zoomAt, MAX_ZOOM } from "./useDigitalZoom";

describe("digital zoom maths", () => {
  it("returns home at 1x and never zooms out past it", () => {
    expect(clampZoom({ scale: 0.4, x: 50, y: 50 }, 800, 450)).toEqual({ scale: 1, x: 0, y: 0 });
  });
  it("caps the zoom level", () => {
    expect(zoomAt({ scale: 1, x: 0, y: 0 }, 50, 0, 0, 800, 450).scale).toBe(MAX_ZOOM);
  });
  it("keeps the point under the pointer in place", () => {
    // Pointer 100px right of centre: at 2x that picture point must still be 100px right.
    const z = zoomAt({ scale: 1, x: 0, y: 0 }, 2, 100, 0, 800, 450);
    expect(z).toEqual({ scale: 2, x: -100, y: 0 });
  });
  it("does not let the picture be dragged off the tile", () => {
    const z = clampZoom({ scale: 2, x: 5000, y: -5000 }, 800, 450);
    expect(z).toEqual({ scale: 2, x: 400, y: -225 });
  });
});
