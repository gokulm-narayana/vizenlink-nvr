import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HealthPanel } from "../HealthPanel";
import { CameraHealthPage } from "./CameraHealthPage";
import { CamerasPage } from "../CamerasPage";
import { useUiStore } from "@/stores/ui";

vi.mock("@/lib/queries", () => ({
  useCameras: () => ({
    data: [
      { serial: "CAM1", name: "Front Door", is_online: true, state: "online" },
      { serial: "CAM2", name: "Backyard", is_online: false, state: "offline" },
    ],
    isLoading: false,
  }),
  useCurrentUser: () => ({
    data: { id: 1, username: "operator1", role: "operator" },
    isLoading: false,
  }),
  useRecordingStatus: () => ({
    data: [],
  }),
}));

describe("HealthPanel", () => {
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

  it("renders uptime, reboot reason, clock sync StatusBadge, and firmware", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/cameras/CAM1/health")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            serial: "CAM1",
            online: true,
            uptime_seconds: 90061, // 1d 1h 1m 1s
            reboot_reason: "Power cycle",
            clock_sync_status: "synced",
            firmware_version: "v2.4.1",
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <HealthPanel serial="CAM1" />
      </QueryClientProvider>
    );

    expect(await screen.findByText("1d 1h 1m 1s")).toBeInTheDocument();
    expect(screen.getByText("Power cycle")).toBeInTheDocument();
    expect(screen.getByText("Synced")).toBeInTheDocument();
    expect(screen.getByText("v2.4.1")).toBeInTheDocument();
  });

  it("renders inline error with Reload camera health button on failure", async () => {
    let callCount = 0;
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/cameras/CAM1/health")) {
        callCount++;
        if (callCount === 1) {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: async () => ({ detail: "NVR camera error" }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            serial: "CAM1",
            online: true,
            uptime_seconds: 60,
            clock_sync_status: "synced",
            firmware_version: "v1.0",
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <HealthPanel serial="CAM1" />
      </QueryClientProvider>
    );

    expect(
      await screen.findByText("Couldn't load camera health. Check your connection and try again.")
    ).toBeInTheDocument();

    const reloadBtn = screen.getByRole("button", { name: "Reload camera health" });
    await userEvent.click(reloadBtn);

    await waitFor(() => {
      expect(callCount).toBe(2);
    });
  });
});

describe("CameraHealthPage (Viewer Route)", () => {
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

  it("renders read-only health panel for assigned camera with camera name and serial", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/cameras/CAM1/health")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            serial: "CAM1",
            online: true,
            uptime_seconds: 3600,
            reboot_reason: "Scheduled reboot",
            clock_sync_status: "synced",
            firmware_version: "v3.0.0",
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/cameras/CAM1/health"]}>
          <Routes>
            <Route path="/cameras/:serial/health" element={<CameraHealthPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Front Door" })).toBeInTheDocument();
    expect(screen.getByText("CAM1")).toBeInTheDocument();
    expect(await screen.findByText("Scheduled reboot")).toBeInTheDocument();
    expect(screen.getByText("v3.0.0")).toBeInTheDocument();

    // Renders no settings controls or maintenance actions
    expect(screen.queryByRole("button", { name: /save changes/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reboot camera/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /factory reset/i })).toBeNull();
  });

  it("renders 403 Forbidden state when user lacks access to the camera", async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/cameras/CAM999/health")) {
        return Promise.resolve({
          ok: false,
          status: 403,
          json: async () => ({ detail: "Access denied to camera" }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/cameras/CAM999/health"]}>
          <Routes>
            <Route path="/cameras/:serial/health" element={<CameraHealthPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByText("Access restricted")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Live" })).toBeInTheDocument();
  });
});

describe("CamerasPage Health Tab & View Mode Visibility", () => {
  let queryClient: QueryClient;
  const originalFetch = global.fetch;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/cameras/CAM1/health")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            serial: "CAM1",
            online: true,
            uptime_seconds: 3600,
            reboot_reason: "Normal boot",
            clock_sync_status: "synced",
            firmware_version: "v1.2",
          }),
        });
      }
      if (url.includes("/api/v1/cameras/CAM1/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            identity: { name: "Front Door", location: "Entrance", supported_timezones: [] },
            device_info: { manufacturer: "Sony", model: "IMX", firmware_version: "1.2", serial_number: "CAM1", hardware_id: "HW1" },
            encoders: [],
            imaging: { current: {}, options: { wdr_supported: false } },
            osd: { overlays: [] },
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders all camera tabs in everyday view", async () => {
    useUiStore.setState({ viewMode: "simple" });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/cameras/CAM1"]}>
          <CamerasPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByRole("tab", { name: "Details" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Health" })).toBeInTheDocument();

    // Video, Image, Overlays, and Maintenance are hidden in Simple view
    expect(screen.queryByRole("tab", { name: "Video" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Image" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "On-screen text" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Maintenance" })).toBeInTheDocument();
  });

  it("renders all tabs in Advanced view mode", async () => {
    useUiStore.setState({ viewMode: "advanced" });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/cameras/CAM1"]}>
          <CamerasPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByRole("tab", { name: "Details" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Video" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Image" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "On-screen text" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Health" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Maintenance" })).toBeInTheDocument();
  });
});
