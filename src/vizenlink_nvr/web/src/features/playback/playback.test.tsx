import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PlaybackPage } from "./PlaybackPage";
import { findCoveringOrNextSegment, usePlaybackEngine } from "./usePlaybackEngine";
import { renderHook, act } from "@testing-library/react";
import type { TimelineSegment } from "@/lib/timeline";

import { toast } from "sonner";
import { parseTimeToDate } from "./usePlaybackEngine";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/lib/queries", () => ({
  useCameras: () => ({
    data: [
      { serial: "CAM1", name: "Front Door", is_online: true },
      { serial: "CAM2", name: "Backyard", is_online: false },
    ],
    isLoading: false,
  }),
  useRecordingStatus: () => ({
    data: [
      { camera_serial: "CAM1", mode: "continuous", retention_days: 14 },
      { camera_serial: "CAM2", mode: "motion", retention_days: 7 },
    ],
  }),
  useAuthStatus: () => ({
    data: {
      site_timezone: "Asia/Kolkata",
      authenticated: true,
      user: { username: "admin", role: "owner" },
    },
  }),
}));

describe("findCoveringOrNextSegment", () => {
  const segments: TimelineSegment[] = [
    {
      id: 1,
      start_time: "2026-11-05T10:00:00.000Z",
      end_time: "2026-11-05T10:10:00.000Z",
      is_protected: false,
      duration_seconds: 600,
    },
    {
      id: 2,
      start_time: "2026-11-05T10:20:00.000Z",
      end_time: "2026-11-05T10:30:00.000Z",
      is_protected: false,
      duration_seconds: 600,
    },
  ];

  it("finds covering segment when target falls within bounds", () => {
    const target = new Date("2026-11-05T10:05:00.000Z");
    const { covering, next } = findCoveringOrNextSegment(target, segments);
    expect(covering?.id).toBe(1);
    expect(next).toBeNull();
  });

  it("identifies next segment when target falls in an outage/empty gap", () => {
    const target = new Date("2026-11-05T10:15:00.000Z");
    const { covering, next } = findCoveringOrNextSegment(target, segments);
    expect(covering).toBeNull();
    expect(next?.id).toBe(2);
  });

  it("returns null for both when target is after all segments", () => {
    const target = new Date("2026-11-05T11:00:00.000Z");
    const { covering, next } = findCoveringOrNextSegment(target, segments);
    expect(covering).toBeNull();
    expect(next).toBeNull();
  });
});

describe("usePlaybackEngine", () => {
  let mockVideo: HTMLVideoElement;
  const segments: TimelineSegment[] = [
    {
      id: 1,
      start_time: "2026-11-05T10:00:00.000Z",
      end_time: "2026-11-05T10:10:00.000Z",
      is_protected: false,
      duration_seconds: 600,
    },
    {
      id: 2,
      start_time: "2026-11-05T10:20:00.000Z",
      end_time: "2026-11-05T10:30:00.000Z",
      is_protected: false,
      duration_seconds: 600,
    },
  ];

  beforeEach(() => {
    mockVideo = document.createElement("video");
    mockVideo.play = vi.fn().mockResolvedValue(undefined);
    mockVideo.pause = vi.fn();
  });

  it("syncs video src and offset when seeking into a covering segment", () => {
    const videoRef = { current: mockVideo };
    const { result } = renderHook(() =>
      usePlaybackEngine({
        videoRef,
        segments,
        initialTime: new Date("2026-11-05T10:05:00.000Z"),
      })
    );

    act(() => {
      result.current.seek(new Date("2026-11-05T10:05:00.000Z"));
    });

    expect(result.current.activeSegment?.id).toBe(1);
    expect(mockVideo.src).toContain("/api/v1/playback/segment/1");
    expect(mockVideo.currentTime).toBe(300); // 5 mins in
  });

  it("skips gap to next segment start when target falls in a gap", () => {
    const videoRef = { current: mockVideo };
    const { result } = renderHook(() =>
      usePlaybackEngine({
        videoRef,
        segments,
        initialTime: new Date("2026-11-05T10:00:00.000Z"),
      })
    );

    act(() => {
      result.current.seek(new Date("2026-11-05T10:15:00.000Z"));
    });

    expect(result.current.activeSegment?.id).toBe(2);
    expect(result.current.currentTime.toISOString()).toBe("2026-11-05T10:20:00.000Z");
    expect(mockVideo.src).toContain("/api/v1/playback/segment/2");
    expect(mockVideo.currentTime).toBe(0);
  });

  it("automatically advances to next segment when current segment ends", () => {
    const videoRef = { current: mockVideo };
    const { result } = renderHook(() =>
      usePlaybackEngine({
        videoRef,
        segments,
        initialTime: new Date("2026-11-05T10:05:00.000Z"),
      })
    );

    act(() => {
      result.current.seek(new Date("2026-11-05T10:05:00.000Z"));
    });

    act(() => {
      result.current.handleEnded();
    });

    expect(result.current.activeSegment?.id).toBe(2);
    expect(mockVideo.src).toContain("/api/v1/playback/segment/2");
  });

  it("handles play, pause, mute, rate, and skip controls", () => {
    const videoRef = { current: mockVideo };
    const { result } = renderHook(() =>
      usePlaybackEngine({
        videoRef,
        segments,
        initialTime: new Date("2026-11-05T10:05:00.000Z"),
      })
    );

    act(() => {
      result.current.seek(new Date("2026-11-05T10:05:00.000Z"));
    });

    act(() => {
      result.current.togglePlay();
    });
    expect(mockVideo.play).toHaveBeenCalled();

    act(() => {
      result.current.setPlaybackRate(2);
    });
    expect(result.current.playbackRate).toBe(2);
    expect(mockVideo.playbackRate).toBe(2);

    act(() => {
      result.current.toggleMute();
    });
    expect(result.current.isMuted).toBe(false);
    expect(mockVideo.muted).toBe(false);

    act(() => {
      result.current.skip(10);
    });
    expect(result.current.currentTime.toISOString()).toBe("2026-11-05T10:05:10.000Z");
  });
});

describe("PlaybackPage deep link and site-zone timeline query", () => {
  let queryClient: QueryClient;
  const originalFetch = global.fetch;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("queries timeline with site zone day bounds and sets video source", async () => {
    const requestedUrls: string[] = [];

    global.fetch = vi.fn().mockImplementation((url: string) => {
      requestedUrls.push(url);
      if (url.includes("/api/v1/playback/timeline")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            camera_serial: "CAM1",
            start_time: "2026-11-04T18:30:00.000Z",
            end_time: "2026-11-05T18:30:00.000Z",
            segments: [
              {
                id: 101,
                start_time: "2026-11-05T09:00:00.000Z",
                end_time: "2026-11-05T10:00:00.000Z",
                is_protected: false,
                duration_seconds: 3600,
              },
            ],
            outages: [],
            events: [],
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ days: ["2026-11-05"] }),
      });
    });

    // Deep link: ?camera=CAM1&t=2026-11-05T09:30:00Z
    // In Asia/Kolkata (+05:30), 2026-11-05 is from 2026-11-04T18:30:00.000Z to 2026-11-05T18:30:00.000Z
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/playback?camera=CAM1&t=2026-11-05T09:30:00Z"]}>
          <PlaybackPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(
        requestedUrls.some(
          (u) =>
            u.includes("/api/v1/playback/timeline") &&
            u.includes("camera_serial=CAM1") &&
            u.includes("2026-11-04T18%3A30%3A00.000Z") &&
            u.includes("2026-11-05T18%3A30%3A00.000Z")
        )
      ).toBe(true);
    });
  });

  it("shows error alert with Retry playback when timeline query fails", async () => {
    let callCount = 0;
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/playback/timeline")) {
        callCount++;
        if (callCount === 1) {
          return Promise.resolve({
            ok: false,
            status: 500,
            statusText: "Server Error",
            json: async () => ({ detail: "Database connection failed" }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            camera_serial: "CAM1",
            segments: [],
            outages: [],
            events: [],
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ days: [] }) });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/playback?camera=CAM1&t=2026-11-05T09:30:00Z"]}>
          <PlaybackPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const errorAlert = await screen.findByRole("alert");
    expect(errorAlert).toHaveTextContent("Couldn't load playback. Check your connection and try again.");

    const retryBtn = screen.getByRole("button", { name: "Retry playback" });
    await userEvent.click(retryBtn);

    await waitFor(() => {
      expect(callCount).toBeGreaterThan(1);
    });
  });

  it("shows empty day copy when no segments exist for the day", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/playback/timeline")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            camera_serial: "CAM1",
            segments: [],
            outages: [],
            events: [],
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ days: [] }) });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/playback?camera=CAM1&t=2026-11-05T09:30:00Z"]}>
          <PlaybackPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(
      await screen.findByText(
        "No footage on this day. Pick a day marked with a dot, or check that recording is on for this camera."
      )
    ).toBeInTheDocument();
  });
});

describe("parseTimeToDate", () => {
  it("parses valid HH:MM:SS string to exact Date in site timezone", () => {
    const res = parseTimeToDate("2026-11-05", "15:30:45", "Asia/Kolkata");
    expect(res).not.toBeNull();
    // 15:30:45 in Asia/Kolkata (+05:30) is 10:00:45 UTC
    expect(res?.toISOString()).toBe("2026-11-05T10:00:45.000Z");
  });

  it("returns null for invalid time strings", () => {
    expect(parseTimeToDate("2026-11-05", "25:00:00", "UTC")).toBeNull();
    expect(parseTimeToDate("2026-11-05", "invalid", "UTC")).toBeNull();
    expect(parseTimeToDate("2026-11-05", "12:65:00", "UTC")).toBeNull();
  });
});

describe("Playback Toolbar & TransportBar behavior", () => {
  let queryClient: QueryClient;
  const originalFetch = global.fetch;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    // Stub canvas for snapshot
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      drawImage: vi.fn(),
    }) as any;
    HTMLCanvasElement.prototype.toDataURL = vi.fn().mockReturnValue("data:image/jpeg;base64,mockdata");
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders toolbar controls, jump to time, and events deep link", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/playback/timeline")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            camera_serial: "CAM1",
            segments: [
              {
                id: 1,
                start_time: "2026-11-05T00:00:00.000Z",
                end_time: "2026-11-05T23:59:59.000Z",
                is_protected: false,
                duration_seconds: 86400,
              },
            ],
            outages: [],
            events: [],
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ days: ["2026-11-05"] }),
      });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/playback?camera=CAM1&t=2026-11-05T09:30:00Z"]}>
          <PlaybackPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Camera select trigger
    expect(await screen.findByRole("combobox", { name: "Select camera" })).toBeInTheDocument();

    // Events link
    const eventsLink = screen.getByRole("link", { name: /Alerts/i });
    expect(eventsLink).toHaveAttribute("href", "/events?camera=CAM1");

    // Jump to time input
    const jumpInput = screen.getByRole("textbox", { name: "Jump to time" });
    expect(jumpInput).toBeInTheDocument();

    // Export button initially disabled (in and out markers not set)
    const exportBtn = screen.getByRole("button", { name: "Export clip" });
    expect(exportBtn).toBeDisabled();

    // Mark in and Mark out buttons exist
    const markInBtn = screen.getByRole("button", { name: "Set clip start" });
    const markOutBtn = screen.getByRole("button", { name: "Set clip end" });
    expect(markInBtn).toBeInTheDocument();
    expect(markOutBtn).toBeInTheDocument();

    // Click Mark in then Mark out
    await userEvent.click(markInBtn);
    await userEvent.click(markOutBtn);

    // Export button is now enabled
    expect(exportBtn).toBeEnabled();
  });

  it("handles snapshot capture successfully and fires toast", async () => {
    let snapshotPayload: any = null;
    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/v1/playback/snapshot")) {
        snapshotPayload = JSON.parse(init?.body as string);
        return Promise.resolve({
          ok: true,
          json: async () => ({ id: 10, file_path: "/snapshots/10.jpg" }),
        });
      }
      if (url.includes("/api/v1/playback/timeline")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            camera_serial: "CAM1",
            segments: [
              {
                id: 1,
                start_time: "2026-11-05T00:00:00.000Z",
                end_time: "2026-11-05T23:59:59.000Z",
                is_protected: false,
                duration_seconds: 86400,
              },
            ],
            outages: [],
            events: [],
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ days: ["2026-11-05"] }),
      });
    });

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/playback?camera=CAM1&t=2026-11-05T09:30:00Z"]}>
          <PlaybackPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Mock video element readyState
    const video = container.querySelector("video");
    if (video) {
      Object.defineProperty(video, "readyState", { value: 4, configurable: true });
      Object.defineProperty(video, "videoWidth", { value: 1920, configurable: true });
      Object.defineProperty(video, "videoHeight", { value: 1080, configurable: true });
    }

    const snapshotBtn = await screen.findByRole("button", { name: "Take snapshot" });
    await userEvent.click(snapshotBtn);

    await waitFor(() => {
      expect(snapshotPayload).not.toBeNull();
      expect(snapshotPayload.camera_serial).toBe("CAM1");
      expect(snapshotPayload.image_base64).toBe("data:image/jpeg;base64,mockdata");
      expect(toast.success).toHaveBeenCalledWith("Snapshot saved");
    });
  });

  it("handles snapshot failure and displays inline alert with Retry save snapshot", async () => {
    let attempts = 0;
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/playback/snapshot")) {
        attempts++;
        return Promise.resolve({
          ok: false,
          status: 507,
          json: async () => ({ detail: "Storage full" }),
        });
      }
      if (url.includes("/api/v1/playback/timeline")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            camera_serial: "CAM1",
            segments: [
              {
                id: 1,
                start_time: "2026-11-05T00:00:00.000Z",
                end_time: "2026-11-05T23:59:59.000Z",
                is_protected: false,
                duration_seconds: 86400,
              },
            ],
            outages: [],
            events: [],
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ days: ["2026-11-05"] }),
      });
    });

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/playback?camera=CAM1&t=2026-11-05T09:30:00Z"]}>
          <PlaybackPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const video = container.querySelector("video");
    if (video) {
      Object.defineProperty(video, "readyState", { value: 4, configurable: true });
    }

    const snapshotBtn = await screen.findByRole("button", { name: "Take snapshot" });
    await userEvent.click(snapshotBtn);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Couldn't save the snapshot. Check your connection and that the NVR has free storage, then try again."
    );

    const retryBtn = screen.getByRole("button", { name: "Retry save snapshot" });
    await userEvent.click(retryBtn);

    await waitFor(() => {
      expect(attempts).toBe(2);
    });
  });

  it("supports digital zoom controls in single view and opens single view when clicking a multi-view sync tile", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/playback/timeline")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            camera_serial: "CAM1",
            segments: [
              {
                id: 1,
                start_time: "2026-11-05T00:00:00.000Z",
                end_time: "2026-11-05T23:59:59.000Z",
                is_protected: false,
                duration_seconds: 86400,
              },
            ],
            outages: [],
            events: [],
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ days: ["2026-11-05"] }),
      });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/playback?camera=CAM1&t=2026-11-05T09:30:00Z&mode=sync"]}>
          <PlaybackPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const backyardTile = await screen.findByRole("button", { name: "Open Backyard in single view" });
    await userEvent.click(backyardTile);

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Open Backyard in single view" })).toBeNull();
    });

    const zoomInBtn = await screen.findByRole("button", { name: "Zoom in" });
    expect(screen.getByRole("button", { name: "Zoom 1 times" })).toHaveTextContent("1.0×");

    await userEvent.click(zoomInBtn);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Zoom 1.5 times, reset zoom" })).toHaveTextContent("1.5×");
    });

    await userEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Zoom 1 times" })).toHaveTextContent("1.0×");
    });
  });
});
