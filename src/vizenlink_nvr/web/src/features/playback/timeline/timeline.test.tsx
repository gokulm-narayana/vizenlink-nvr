import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Timeline } from "./Timeline";
import type {
  ZoomLevel,
  TimelineSegment,
  TimelineOutage,
  TimelineEvent,
} from "@/lib/timeline";

describe("Timeline component", () => {
  const baseDate = new Date("2026-06-15T00:00:00Z");
  const currentTime = new Date("2026-06-15T12:00:00Z");

  const segments: TimelineSegment[] = [
    {
      id: 1,
      start_time: "2026-06-15T10:00:00Z",
      end_time: "2026-06-15T11:00:00Z",
      is_protected: false,
      duration_seconds: 3600,
    },
    {
      id: 2,
      start_time: "2026-06-15T14:00:00Z",
      end_time: "2026-06-15T15:00:00Z",
      is_protected: true,
      duration_seconds: 3600,
    },
  ];

  const outages: TimelineOutage[] = [
    {
      id: 1,
      started_at: "2026-06-15T08:00:00Z",
      ended_at: "2026-06-15T09:00:00Z",
      duration_seconds: 3600,
      reason: "Network loss",
    },
  ];

  const events: TimelineEvent[] = [
    {
      id: 1,
      event_type: "motion",
      start_time: "2026-06-15T10:30:00Z",
      is_locked: false,
    },
    {
      id: 2,
      event_type: "line_crossing",
      start_time: "2026-06-15T14:30:00Z",
      is_locked: true,
    },
  ];

  const defaultProps = {
    baseDate,
    currentTime,
    onSeek: vi.fn(),
    segments,
    outages,
    events,
    zoomLevel: "24h" as ZoomLevel,
    onZoomChange: vi.fn(),
    inMarker: null,
    outMarker: null,
    onSetInMarker: vi.fn(),
    onSetOutMarker: vi.fn(),
    onClearMarkers: vi.fn(),
    zone: "UTC",
    retentionDays: 7,
    onTogglePlay: vi.fn(),
    onToggleMute: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithClient = (ui: React.ReactElement) => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
  };

  it("renders with slider role and appropriate ARIA attributes", () => {
    renderWithClient(<Timeline {...defaultProps} />);

    const slider = screen.getByRole("slider", { name: "Timeline" });
    expect(slider).toBeInTheDocument();
    expect(slider).toHaveAttribute("tabindex", "0");
    expect(slider).toHaveAttribute("aria-valuenow", currentTime.getTime().toString());
    expect(slider).toHaveAttribute("aria-valuetext");
  });

  it("handles keyboard navigation: arrow keys seek, +/- zoom, Space play, M mute", () => {
    const onSeek = vi.fn();
    const onZoomChange = vi.fn();
    const onTogglePlay = vi.fn();
    const onToggleMute = vi.fn();

    renderWithClient(
      <Timeline
        {...defaultProps}
        onSeek={onSeek}
        onZoomChange={onZoomChange}
        onTogglePlay={onTogglePlay}
        onToggleMute={onToggleMute}
      />
    );

    const slider = screen.getByRole("slider", { name: "Timeline" });

    // ArrowRight: +10s
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(onSeek).toHaveBeenCalledWith(new Date(currentTime.getTime() + 10000));

    // Shift + ArrowLeft: -60s
    fireEvent.keyDown(slider, { key: "ArrowLeft", shiftKey: true });
    expect(onSeek).toHaveBeenCalledWith(new Date(currentTime.getTime() - 60000));

    // '+' zooms in
    fireEvent.keyDown(slider, { key: "+" });
    expect(onZoomChange).toHaveBeenCalledWith("12h");

    // '-' zooms out
    fireEvent.keyDown(slider, { key: "-" });
    expect(onZoomChange).toHaveBeenCalledWith("24h");

    // Space toggles play
    fireEvent.keyDown(slider, { key: " " });
    expect(onTogglePlay).toHaveBeenCalled();

    // 'M' toggles mute
    fireEvent.keyDown(slider, { key: "m" });
    expect(onToggleMute).toHaveBeenCalled();
  });

  it("renders legend with all five encodings", () => {
    renderWithClient(<Timeline {...defaultProps} />);

    expect(screen.getByText("Recorded")).toBeInTheDocument();
    expect(screen.getByText("Recording outage")).toBeInTheDocument();
    expect(screen.getByText("Removed by retention")).toBeInTheDocument();
    expect(screen.getByText("Event")).toBeInTheDocument();
    expect(screen.getByText("Locked")).toBeInTheDocument();
  });

  it("renders hidden table with recorded spans for screen readers", () => {
    renderWithClient(<Timeline {...defaultProps} />);

    const table = screen.getByRole("table", { hidden: true });
    expect(table).toBeInTheDocument();
    expect(table).toHaveClass("sr-only");

    expect(
      screen.getByText("Recorded video spans for this day")
    ).toBeInTheDocument();
    expect(screen.getAllByText("3600s")).toHaveLength(2);
  });

  it("handles mouse click/pointer seek", () => {
    const onSeek = vi.fn();
    renderWithClient(<Timeline {...defaultProps} onSeek={onSeek} />);

    const slider = screen.getByRole("slider", { name: "Timeline" });
    slider.getBoundingClientRect = vi.fn(() => ({
      left: 0,
      top: 0,
      width: 1000,
      height: 120,
      right: 1000,
      bottom: 120,
      x: 0,
      y: 0,
      toJSON: () => {},
    }));

    fireEvent.pointerDown(slider, { clientX: 500, pointerId: 1 });
    expect(onSeek).toHaveBeenCalled();
  });

  it("handles wheel zoom around pointer position", () => {
    const onZoomChange = vi.fn();
    renderWithClient(<Timeline {...defaultProps} onZoomChange={onZoomChange} />);

    const slider = screen.getByRole("slider", { name: "Timeline" });
    slider.getBoundingClientRect = vi.fn(() => ({
      left: 0,
      top: 0,
      width: 1000,
      height: 120,
      right: 1000,
      bottom: 120,
      x: 0,
      y: 0,
      toJSON: () => {},
    }));

    // Wheel up: zoom in
    fireEvent.wheel(slider, { deltaY: -100, clientX: 500 });
    expect(onZoomChange).toHaveBeenCalledWith("12h");
  });

  it("renders markers and handles In/Out button clicks", async () => {
    const user = userEvent.setup();
    const onSetInMarker = vi.fn();
    const onSetOutMarker = vi.fn();
    const onClearMarkers = vi.fn();

    const { rerender } = renderWithClient(
      <Timeline
        {...defaultProps}
        onSetInMarker={onSetInMarker}
        onSetOutMarker={onSetOutMarker}
        onClearMarkers={onClearMarkers}
      />
    );

    const inBtn = screen.getByRole("button", { name: /\[ In/i });
    await user.click(inBtn);
    expect(onSetInMarker).toHaveBeenCalled();

    const outBtn = screen.getByRole("button", { name: /Out \]/i });
    await user.click(outBtn);
    expect(onSetOutMarker).toHaveBeenCalled();

    // Rerender with markers set to test clear
    const queryClient = new QueryClient();
    rerender(
      <QueryClientProvider client={queryClient}>
        <Timeline
          {...defaultProps}
          inMarker={new Date("2026-06-15T10:00:00Z")}
          outMarker={new Date("2026-06-15T11:00:00Z")}
          onClearMarkers={onClearMarkers}
        />
      </QueryClientProvider>
    );

    const clearBtn = screen.getByRole("button", { name: "Clear markers" });
    await user.click(clearBtn);
    expect(onClearMarkers).toHaveBeenCalled();
  });
});
