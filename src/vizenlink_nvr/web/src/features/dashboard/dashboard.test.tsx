import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { DashboardPage } from "./DashboardPage";
import { StorageCard } from "./StorageCard";
import { AlertsCard } from "./AlertsCard";
import { CamerasTable } from "./CamerasTable";
import { OutageHistoryDialog } from "./OutageHistoryDialog";
import { useUiStore } from "@/stores/ui";

let mockStorageHealth = "ok";
let mockCurrentUser: { id: number; username: string; role: string; permissions: string[] } | null = {
  id: 1,
  username: "operator1",
  role: "operator",
  permissions: ["*"],
};

vi.mock("@/lib/queries", () => ({
  useCameras: () => ({
    data: [
      { serial: "CAM-01", name: "Front Door" },
      { serial: "CAM-02", name: "Backyard" },
    ],
    isLoading: false,
    refetch: vi.fn(),
  }),
  useRecordingStatus: () => ({
    data: [
      { camera_serial: "CAM-01", mode: "continuous" },
      { camera_serial: "CAM-02", mode: "off" },
    ],
    refetch: vi.fn(),
  }),
  useHealth: () => ({
    data: {
      status: "healthy",
      db_ok: true,
      mediamtx_ok: true,
      storage_ok: true,
      total_cameras: 2,
      active_cameras: 2,
      details: {
        uptime_seconds: 86400,
        version: "1.0.0",
      },
    },
    isLoading: false,
    refetch: vi.fn(),
  }),
  useAlerts: () => ({
    data: [
      {
        id: "alert-1",
        severity: "warning",
        message: "Camera Front Door not recording",
        camera_serial: "CAM-01",
        timestamp: "2026-06-15T12:00:00Z",
      },
    ],
    isLoading: false,
    refetch: vi.fn(),
  }),
  useAuthStatus: () => ({
    data: { site_timezone: "UTC", user: mockCurrentUser },
  }),
  useCurrentUser: () => mockCurrentUser,
  useUnreadCount: () => ({
    data: {
      items: [
        { id: 7, camera_serial: "CAM-01", event_type: "line_crossing", start_time: "2026-06-15T12:05:00Z" },
      ],
      total: 1,
    },
    unreadCount: 1,
  }),
}));

vi.mock("./api", () => ({
  useStorageStatus: () => ({
    data: {
      storage_path: "/var/lib/vizenlink-nvr/recordings",
      allow_system_disk: false,
      reserve_bytes: 21474836480, // 20 GiB
      health_state: mockStorageHealth,
      telemetry: {
        total_bytes: 107374182400, // 100 GiB
        used_bytes: 75161927680, // 70 GiB (70%)
        free_bytes: 32212254720, // 30 GiB
        reserve_bytes: 21474836480,
      },
      estimated_retention_days: 14,
    },
    isLoading: false,
    refetch: vi.fn(),
  }),
  useOutages: () => ({
    data: [
      {
        id: 1,
        camera_serial: "CAM-02",
        started_at: "2026-06-15T11:00:00Z",
        ended_at: null, // open outage
        duration_seconds: null,
        reason: "Network connection lost",
      },
      {
        id: 2,
        camera_serial: "CAM-01",
        started_at: "2026-06-15T08:00:00Z",
        ended_at: "2026-06-15T08:30:00Z",
        duration_seconds: 1800,
        reason: "Firmware reboot",
      },
    ],
    isLoading: false,
    refetch: vi.fn(),
  }),
  useSystemMetrics: () => ({
    data: {
      cpu_percent: 37.4,
      cpu_count: 8,
      memory_total_bytes: 17179869184,
      memory_used_bytes: 8589934592,
      memory_percent: 50,
      nvr_uptime_seconds: 90061,
      host_uptime_seconds: 200000,
      load_average: [1, 1, 1],
      platform: "Darwin arm64",
      version: "0.1.0",
    },
  }),
}));

describe("Dashboard Feature", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStorageHealth = "ok";
    localStorage.clear();
    mockCurrentUser = {
      id: 1,
      username: "operator1",
      role: "operator",
      permissions: ["*"],
    };
    useUiStore.setState({
      viewMode: "simple",
      dismissedAlertIds: new Set<string>(),
    });
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("Recommended dashboard layout", () => {
    it("shows key numbers, cameras with problems first, recent alerts, storage and system", () => {
      renderWithProviders(<DashboardPage />);

      const kpi = (label: string) => document.querySelector(`[data-kpi="${label}"]`) as HTMLElement;
      expect(kpi("Cameras online")).toHaveTextContent("1 / 2");
      expect(kpi("Recording")).toHaveTextContent("1 / 2");
      expect(kpi("Footage kept for")).toHaveTextContent("14 days");
      expect(kpi("Active alerts")).toHaveTextContent("1");

      // Backyard has an open outage, so it is listed first.
      const list = screen.getByRole("list", { name: "Camera status" });
      const items = within(list).getAllByRole("listitem");
      expect(items[0]).toHaveAttribute("data-state", "offline");
      expect(items[0]).toHaveTextContent("Backyard");
      expect(within(items[0]).getByRole("link", { name: /^Backyard/ })).toHaveAttribute("href", "/cameras/CAM-02/health");
      expect(within(items[0]).getByRole("link", { name: "Play back Backyard" })).toHaveAttribute("href", "/playback?camera=CAM-02");

      const alerts = screen.getByRole("list", { name: "Recent alerts" });
      expect(within(alerts).getByText("Camera Front Door not recording")).toBeInTheDocument();
      expect(within(alerts).getByText("line crossing")).toBeInTheDocument();

      expect(screen.getByText("Camera outage history")).toBeInTheDocument();
      expect(screen.getByText("37%")).toBeInTheDocument();
      expect(screen.getByText("50%")).toBeInTheDocument();
      expect(screen.getByText("Video service")).toBeInTheDocument();
      expect(screen.getByText("Up 1d 1h")).toBeInTheDocument();
    });
  });

  it("never reports Healthy when the configured storage folder is unavailable", () => {
    mockStorageHealth = "unmounted";
    renderWithProviders(<DashboardPage />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveAttribute("data-level", "critical");
    expect(within(banner).getByText("Not recording")).toBeInTheDocument();
    expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
    expect(screen.getByText(/0 days retention \(not saving\)/)).toBeInTheDocument();
    expect((document.querySelector('[data-kpi="Recording"]') as HTMLElement)).toHaveTextContent("0 / 2");
    expect(screen.getAllByRole("link", { name: /Review storage settings/ })[0]).toHaveAttribute("href", "/settings/recording");
  });

  describe("StorageCard", () => {
    it("renders storage path with copy button and formatted telemetry metrics", async () => {
      const user = userEvent.setup();
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", {
        value: { writeText: writeTextMock },
        writable: true,
        configurable: true,
      });

      renderWithProviders(
        <StorageCard
          storage={{
            storage_path: "/var/lib/vizenlink-nvr/recordings",
            allow_system_disk: false,
            reserve_bytes: 21474836480,
            health_state: "ok",
            telemetry: {
              total_bytes: 107374182400,
              used_bytes: 75161927680,
              free_bytes: 32212254720,
              reserve_bytes: 21474836480,
            },
            estimated_retention_days: 14,
          }}
        />
      );

      expect(screen.getByText("Storage")).toBeInTheDocument();
      expect(screen.getByText("30.0 GiB")).toBeInTheDocument();
      expect(screen.getByText("14 days")).toBeInTheDocument();
      expect(screen.getByText("Reserved space: 20.0 GiB")).toBeInTheDocument();
      await user.click(screen.getByText("Storage details"));

      const copyBtn = screen.getByRole("button", { name: "Copy storage path" });
      await user.click(copyBtn);
      expect(writeTextMock).toHaveBeenCalledWith("/var/lib/vizenlink-nvr/recordings");
    });

    it("displays critical badge and reason when storage health is degraded/critical", () => {
      renderWithProviders(
        <StorageCard
          storage={{
            storage_path: "/var/lib/vizenlink-nvr/recordings",
            allow_system_disk: false,
            reserve_bytes: 21474836480,
            health_state: "critical",
            health_reason: "Storage volume is read-only",
            telemetry: null,
            estimated_retention_days: null,
          }}
        />
      );

      expect(screen.getByText("Storage volume is read-only")).toBeInTheDocument();
      expect(screen.getByText("Action needed")).toBeInTheDocument();
    });
  });

  describe("AlertsCard", () => {
    it("renders active alerts, camera health link, and handles dismissal", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AlertsCard />);

      expect(screen.getByText("Camera Front Door not recording")).toBeInTheDocument();
      expect(screen.getByText("Open camera health")).toBeInTheDocument();

      const dismissBtn = screen.getByRole("button", { name: "Dismiss alert" });
      await user.click(dismissBtn);

      expect(useUiStore.getState().dismissedAlertIds.has("alert-1")).toBe(true);
    });
  });

  describe("CamerasTable", () => {
    it("renders table with independent online and recording statuses", () => {
      const openOutageMap = new Map([["CAM-02", "2026-06-15T11:00:00Z"]]);
      const recordingSerials = new Set(["CAM-01"]);
      const onViewOutage = vi.fn();

      renderWithProviders(
        <CamerasTable
          cameras={[
            { serial: "CAM-01", name: "Front Door" },
            { serial: "CAM-02", name: "Backyard" },
          ]}
          recordingSerials={recordingSerials}
          openOutageMap={openOutageMap}
          onViewOutage={onViewOutage}
          zone="UTC"
        />
      );

      // CAM-01: Online & Recording (present in desktop and mobile views)
      expect(screen.getAllByText("Front Door")).toHaveLength(2);
      // CAM-02: Offline & Not recording
      expect(screen.getAllByText("Backyard")).toHaveLength(2);

      const outageButtons = screen.getAllByRole("button", { name: "View outage history" });
      fireEvent.click(outageButtons[0]);
      expect(onViewOutage).toHaveBeenCalledWith("CAM-01", "Front Door");
    });

    it("renders role-specific empty state when no cameras exist", () => {
      // Operator empty state
      const { rerender } = renderWithProviders(
        <CamerasTable
          cameras={[]}
          recordingSerials={new Set()}
          openOutageMap={new Map()}
          onViewOutage={vi.fn()}
          zone="UTC"
        />
      );

      expect(screen.getByText("No cameras yet")).toBeInTheDocument();
      expect(screen.getByText("Add camera")).toBeInTheDocument();

      // Viewer empty state
      mockCurrentUser = {
        id: 2,
        username: "viewer1",
        role: "viewer",
        permissions: [],
      };

      rerender(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter>
            <CamerasTable
              cameras={[]}
              recordingSerials={new Set()}
              openOutageMap={new Map()}
              onViewOutage={vi.fn()}
              zone="UTC"
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.getByText("No cameras assigned")).toBeInTheDocument();
      expect(screen.queryByText("Add camera")).not.toBeInTheDocument();
    });
  });

  describe("OutageHistoryDialog", () => {
    it("renders global outage history and can close", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();

      renderWithProviders(
        <OutageHistoryDialog
          isOpen={true}
          onClose={onClose}
          zone="UTC"
        />
      );

      expect(screen.getByText("Camera outage history")).toBeInTheDocument();
      expect(screen.getByText("CAM-02")).toBeInTheDocument();
      expect(screen.getAllByText("Ongoing")).toHaveLength(2);
      expect(screen.getByText("30m 0s")).toBeInTheDocument();

      const closeBtns = screen.getAllByRole("button", { name: "Close outage history" });
      await user.click(closeBtns[0]);
      expect(onClose).toHaveBeenCalled();
    });

    it("filters to specific camera when filterCameraSerial is provided", () => {
      renderWithProviders(
        <OutageHistoryDialog
          isOpen={true}
          onClose={vi.fn()}
          filterCameraSerial="CAM-01"
          cameraName="Front Door"
          zone="UTC"
        />
      );

      expect(screen.getByText("Front Door outage history")).toBeInTheDocument();
      expect(screen.queryByText("CAM-02")).not.toBeInTheDocument();
      expect(screen.getByText("30m 0s")).toBeInTheDocument();
    });
  });

  it("shows Healthy only when storage, services and every camera are fine", () => {
    renderWithProviders(<DashboardPage />);
    // CAM-02 is offline and not recording, so the recorder needs attention.
    expect(within(screen.getByRole("status")).getByText("Needs attention")).toBeInTheDocument();
  });
});
