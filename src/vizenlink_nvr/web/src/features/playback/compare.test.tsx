import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ComparePlaybackPage, coveringSegment } from "./ComparePlaybackPage";

const { segments } = vi.hoisted(() => ({ segments: [{ id: 1, camera_serial: "A", start_time: "2026-11-11T12:00:00Z", end_time: "2026-11-11T12:00:01Z", duration_seconds: 1, file_size_bytes: 100, is_protected: false, stream_type: "main" }, { id: 2, camera_serial: "A", start_time: "2026-11-11T12:00:10Z", end_time: "2026-11-11T12:00:20Z", duration_seconds: 10, file_size_bytes: 100, is_protected: false, stream_type: "main" }] }));
vi.mock("@/lib/queries", () => ({ useCameras: () => ({ data: ["A", "B", "C", "D", "E"].map(serial => ({ serial, name: `Camera ${serial}` })) }), useAuthStatus: () => ({ data: { site_timezone: "UTC" } }) }));
vi.mock("./api", () => ({ useTimeline: () => ({ data: { segments }, refetch: vi.fn() }) }));
afterEach(() => vi.useRealTimers());

describe("Synchronized comparison", () => {
  it("leaves gaps empty instead of jumping one camera ahead", () => {
    expect(coveringSegment(segments, Date.parse("2026-11-11T12:00:00Z"))?.id).toBe(1);
    expect(coveringSegment(segments, Date.parse("2026-11-11T12:00:01Z"))).toBeUndefined();
    expect(coveringSegment(segments, Date.parse("2026-11-11T12:00:05Z"))).toBeUndefined();
    expect(coveringSegment(segments, Date.parse("2026-11-11T12:00:10Z"))?.id).toBe(2);
  });
  it("advances all selected cameras with one clock and preserves recording gaps", () => {
    vi.useFakeTimers();
    render(<MemoryRouter initialEntries={["/playback/compare?camera=A&camera=B&t=2026-11-11T12:00:00Z"]}><ComparePlaybackPage /></MemoryRouter>);
    expect(screen.getByRole("region", { name: "Camera A comparison" }).querySelector("video")).toHaveAttribute("src", "/api/v1/playback/segment/1");
    fireEvent.click(screen.getByRole("button", { name: "Play all cameras" }));
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getAllByText("No footage at this time")).toHaveLength(2);
    expect(screen.getByRole("region", { name: "Camera A comparison" }).querySelector("video")).not.toHaveAttribute("src");
    expect(screen.getByRole("region", { name: "Camera B comparison" }).querySelector("video")).not.toHaveAttribute("src");
    fireEvent.click(screen.getByRole("button", { name: "Pause all cameras" }));
    const paused = (screen.getByRole("slider", { name: "Shared playback position" }) as HTMLInputElement).value;
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("slider", { name: "Shared playback position" })).toHaveValue(paused);
  });
  it("selects more than four cameras and seeks every view from any timeline row", () => {
    render(<MemoryRouter initialEntries={["/playback/compare?t=2026-11-11T12:00:00Z"]}><ComparePlaybackPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Select cameras to compare" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all cameras" }));
    fireEvent.click(screen.getByRole("button", { name: "View selected cameras" }));
    expect(screen.getAllByRole("region", { name: /comparison$/ })).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: "Seek all cameras to Camera E at 12:00:10" }));
    expect(screen.getByRole("slider", { name: "Shared playback position" }))
      .toHaveValue(String(Date.parse("2026-11-11T12:00:10Z")));
    for (const region of screen.getAllByRole("region", { name: /comparison$/ })) {
      expect(region.querySelector("video")).toHaveAttribute("src", "/api/v1/playback/segment/2");
    }
  });
});
