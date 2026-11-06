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
}));

vi.mock("./api", () => ({
  useStorageStatus: () => ({
    data: {
      storage_path: "/var/lib/vizenlink-nvr/recordings",
      allow_system_disk: false,
      reserve_bytes: 21474836480, // 20 GiB
      health_state: "ok",
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
}));

describe("Dashboard Feature", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  describe("Row 1 Metric Cards", () => {
    it("renders recorder status in display size and other metrics in heading size", () => {
      renderWithProviders(<DashboardPage />);

      // Recorder status displays Healthy
      expect(screen.getByText("Recorder status")).toBeInTheDocument();
      expect(screen.getByText("Healthy", { selector: ".text-display" })).toBeInTheDocument();

      // Cameras online (CAM-01 is online, CAM-02 has open outage so offline)
      expect(screen.getByText("Cameras online")).toBeInTheDocument();
      expect(screen.getByText("1 / 2")).toHaveClass("text-xl");

      // Recording now (CAM-01 is continuous, CAM-02 is off)
      expect(screen.getByText("Recording now")).toBeInTheDocument();
      const recordingCard = screen.getByText("Recording now").closest('[data-slot="card"]');
      expect(within(recordingCard! as HTMLElement).getByText("1")).toHaveClass("text-xl");

      // Storage used (70%)
      expect(screen.getByText("Storage used")).toBeInTheDocument();
      expect(screen.getByText("70%")).toBeInTheDocument();

      // Active alerts
      expect(screen.getByText("Active alerts")).toBeInTheDocument();
      const alertsCard = screen.getByText("Active alerts").closest('[data-slot="card"]');
      expect(within(alertsCard! as HTMLElement).getByText("1")).toHaveClass("text-xl");
      expect(screen.getByText("Camera outage history")).toBeInTheDocument();
    });
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
      expect(screen.getByText("20.0 GiB")).toBeInTheDocument();

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
      expect(screen.getByText("critical")).toBeInTheDocument();
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

  describe("Advanced Diagnostic View", () => {
    it("shows subsystem health and uptime only in advanced mode", () => {
      useUiStore.setState({ viewMode: "simple" });
      const { rerender } = renderWithProviders(<DashboardPage />);

      expect(screen.queryByText("Subsystem health")).not.toBeInTheDocument();
      expect(screen.queryByText("MediaMTX")).not.toBeInTheDocument();

      // Switch to Advanced
      useUiStore.setState({ viewMode: "advanced" });
      rerender(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter>
            <DashboardPage />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.getByText("Subsystem health")).toBeInTheDocument();
      expect(screen.getByText("MediaMTX")).toBeInTheDocument();
      expect(screen.getByText("Database")).toBeInTheDocument();
      expect(screen.getAllByText("Storage")).toHaveLength(2);
      expect(screen.getByText("Recorder uptime:")).toBeInTheDocument();
      expect(screen.getByText("Raw health details")).toBeInTheDocument();
    });
  });
});
