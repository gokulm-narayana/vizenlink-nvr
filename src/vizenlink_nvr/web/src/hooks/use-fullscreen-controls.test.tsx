import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useFullscreenControls } from "./use-fullscreen-controls";

afterEach(() => {
  Object.defineProperty(document, "fullscreenElement", { configurable: true, value: null });
  vi.useRealTimers();
});

it("hides fullscreen chrome after inactivity, reveals it on input and restores it on exit", () => {
  vi.useFakeTimers();
  const element = document.createElement("div");
  const ref = { current: element };
  const { result, unmount } = renderHook(() => useFullscreenControls(ref));
  act(() => {
    Object.defineProperty(document, "fullscreenElement", { configurable: true, value: element });
    document.dispatchEvent(new Event("fullscreenchange"));
  });
  expect(result.current.isFullscreen).toBe(true);
  act(() => vi.advanceTimersByTime(3000));
  expect(result.current.controlsVisible).toBe(false);
  act(() => element.dispatchEvent(new Event("pointermove")));
  expect(result.current.controlsVisible).toBe(true);
  act(() => vi.advanceTimersByTime(3000));
  expect(result.current.controlsVisible).toBe(false);
  act(() => element.dispatchEvent(new Event("pointerdown")));
  expect(result.current.controlsVisible).toBe(true);
  act(() => {
    Object.defineProperty(document, "fullscreenElement", { configurable: true, value: null });
    document.dispatchEvent(new Event("fullscreenchange"));
  });
  expect(result.current).toEqual({ isFullscreen: false, controlsVisible: true });
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});
