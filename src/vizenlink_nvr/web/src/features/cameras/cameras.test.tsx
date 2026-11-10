import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router";
import { CamerasPage } from "./CamerasPage";
import { useUiStore } from "@/stores/ui";
import { toast } from "sonner";

vi.mock("sonner", () => ({
  toast: vi.fn(),
}));

let mockCamerasData: any[] = [];
let mockSettingsData: any = null;
let mockHealthData: any = null;
let mockSaveIdentityReject = false;

vi.mock("@/lib/queries", () => ({
  useCameras: () => ({
    data: mockCamerasData,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useCurrentUser: () => ({
    id: 1,
    username: "operator1",
    role: "operator",
    permissions: ["*"],
  }),
  useRecordingStatus: () => ({
    data: [
      { camera_serial: "CAM-01", is_recording: true, mode: "continuous" },
      { camera_serial: "CAM-02", is_recording: false, mode: "off" },
    ],
  }),
}));

const { mockSaveImagingFn } = vi.hoisted(() => ({ mockSaveImagingFn: vi.fn() }));

vi.mock("./api", () => ({
  useCameraSettings: (serial: string) => ({
    data: mockSettingsData,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useCameraHealth: (serial: string) => ({
    data: mockHealthData,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useSaveIdentity: (serial: string) => ({
    mutateAsync: vi.fn().mockImplementation(async (payload) => {
      if (mockSaveIdentityReject) {
        throw new Error("Failed to save identity");
      }
      return { ok: true };
    }),
    isPending: false,
  }),
  useSaveEncoder: (serial: string) => ({
    mutateAsync: vi.fn().mockResolvedValue({ ok: true }),
    isPending: false,
  }),
  useSaveImaging: (serial: string) => ({
    mutateAsync: mockSaveImagingFn.mockResolvedValue({ ok: true }),
    isPending: false,
  }),
  useSaveOsd: (serial: string) => ({
    mutateAsync: vi.fn().mockResolvedValue({ ok: true }),
    isPending: false,
  }),
  useReboot: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ ok: true }),
    isPending: false,
  }),
  useFactoryReset: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ ok: true }),
    isPending: false,
  }),
}));

describe("Cameras Feature", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSaveIdentityReject = false;
    useUiStore.setState({ viewMode: "advanced" });

    mockCamerasData = [
      {
        id: 1,
        serial: "CAM-01",
        name: "Front Door",
        location: "Main Entrance",
        is_online: true,
        state: "active",
        last_error: null,
      },
      {
        id: 2,
        serial: "CAM-02",
        name: "Back Alley",
        location: "Rear Exit",
        is_online: false,
        state: "error",
        last_error: "RTSP connection timeout (port 554)",
      },
    ];

    mockSettingsData = {
      identity: {
        name: "Front Door",
        location: "Main Entrance",
        timezone: "America/New_York",
        supported_timezones: [
          { code: "UTC", label: "UTC" },
          { code: "America/New_York", label: "Eastern Time" },
        ],
      },
      device_info: {
        manufacturer: "VizenCam",
        model: "VC-400-PRO",
        firmware_version: "v2.4.1",
        serial_number: "CAM-01",
        hardware_id: "HW-REV-3",
      },
      encoders: [
        {
          profile_token: "prof_main",
          profile_name: "Main Stream",
          venc_token: "venc_1",
          current: {
            encoding: "H265",
            width: 2560,
            height: 1440,
            quality: 80,
            frame_rate_limit: 30,
            bitrate_limit_kbps: 4096,
            gov_length: 60,
            profile: "Main",
          },
          options: {
            encodings: ["H264", "H265"],
            resolutions: [
              { width: 2560, height: 1440 },
              { width: 1920, height: 1080 },
            ],
            quality_range: [1, 100],
            frame_rate_range: [1, 30],
            bitrate_range_kbps: [256, 8192],
            gov_length_range: [10, 120],
          },
        },
      ],
      imaging: {
        current: {
          brightness: 55,
          contrast: 50,
          color_saturation: 50,
          sharpness: 50,
          ir_cut_filter: "AUTO",
          wdr_mode: "ON",
          wdr_level: 25,
          night_vision_type: "smart",
          mirror_flip: "off",
          anti_flicker: "60Hz",
        },
        options: {
          brightness_range: [0, 100],
          contrast_range: [0, 100],
          color_saturation_range: [0, 100],
          sharpness_range: [0, 100],
          ir_cut_filter_modes: ["AUTO", "DAY", "NIGHT"],
          wdr_supported: true,
          wdr_level_range: [0, 100],
          night_vision_color_capable: true,
          night_vision_smart_capable: true,
        },
      },
      osd: [
        {
          token: "OSD_Text",
          video_source_token: "VideoSource_1",
          osd_type: "Plain",
          position: "BottomRight",
          plain_text: "Front Door",
          date_format: "",
          time_format: "",
        },
        {
          token: "OSD_Time",
          video_source_token: "VideoSource_1",
          osd_type: "DateAndTime",
          position: "UpperLeft",
          plain_text: "",
          date_format: "YYYY/MM/DD",
          time_format: "HH:mm:ss",
        },
      ],
    };
  });

  const renderWithRouter = (initialEntries: string[] = ["/cameras"]) => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/cameras" element={<CamerasPage />} />
            <Route path="/cameras/:serial" element={<CamerasPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("Master-Detail & Navigation", () => {
    it("renders camera list and selects first camera by default on /cameras", () => {
      renderWithRouter(["/cameras"]);

      // Master list shows both cameras
      expect(screen.getAllByText("Front Door").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Back Alley")).toBeInTheDocument();

      // Detail header shows selected camera name and serial
      const detailHeader = screen.getByRole("heading", { level: 2, name: "Front Door" });
      expect(detailHeader).toBeInTheDocument();
      expect(screen.getAllByText("CAM-01").length).toBeGreaterThanOrEqual(1);
    });

    it("selects specific camera when route is /cameras/:serial", () => {
      renderWithRouter(["/cameras/CAM-02"]);

      const detailHeader = screen.getByRole("heading", { level: 2, name: "Back Alley" });
      expect(detailHeader).toBeInTheDocument();
      expect(screen.getByText("CAM-02")).toBeInTheDocument();
    });

    it("renders zero cameras empty state when camera list is empty", () => {
      mockCamerasData = [];
      renderWithRouter(["/cameras"]);

      expect(screen.getByText("No cameras yet")).toBeInTheDocument();
      expect(screen.getByText(/Connect your first camera/i)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Add camera" })).toHaveAttribute("href", "/cameras/add");
    });
  });

  describe("Not-Connected & Error Warning", () => {
    it("shows warning alert with last_error verbatim when camera is inactive or has error", async () => {
      const user = userEvent.setup();
      renderWithRouter(["/cameras/CAM-02"]);

      // Shows warning alert
      expect(screen.getByText("Back Alley hasn't connected yet")).toBeInTheDocument();
      expect(screen.getByText("RTSP connection timeout (port 554)")).toBeInTheDocument();

      // Action button selects Identity tab
      const editBtn = screen.getByRole("button", { name: "Edit camera details" });
      await user.click(editBtn);

      // Camera details are active
      expect(screen.getByRole("tab", { name: "Details" })).toHaveAttribute("data-state", "active");
    });
  });

  describe("Identity Tab & Form Persistence", () => {
    it("renders identity and hardware info; saves changes with toast", async () => {
      const user = userEvent.setup();
      renderWithRouter(["/cameras/CAM-01"]);

      const nameInput = screen.getByLabelText("Camera name") as HTMLInputElement;
      expect(nameInput.value).toBe("Front Door");

      // Hardware info is visible
      expect(screen.getByText("VizenCam")).toBeInTheDocument();
      expect(screen.getByText("VC-400-PRO")).toBeInTheDocument();
      expect(screen.getByText("v2.4.1")).toBeInTheDocument();

      // Sticky save bar is not visible initially
      expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();

      // Edit name
      await user.clear(nameInput);
      await user.type(nameInput, "Front Gate");

      // Sticky save bar is now visible
      const saveBtn = screen.getByRole("button", { name: "Save changes" });
      expect(saveBtn).toBeInTheDocument();

      // Save changes
      await user.click(saveBtn);

      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith("Settings saved");
      });
    });

    it("shows failure inline error and keeps form dirty when save fails", async () => {
      mockSaveIdentityReject = true;
      const user = userEvent.setup();
      renderWithRouter(["/cameras/CAM-01"]);

      const nameInput = screen.getByLabelText("Camera name");
      await user.type(nameInput, " Updated");

      const saveBtn = screen.getByRole("button", { name: "Save changes" });
      await user.click(saveBtn);

      await waitFor(() => {
        expect(
          screen.getByText(/Couldn't save settings for Front Door/i)
        ).toBeInTheDocument();
      });

      // Retry button is available
      expect(screen.getByRole("button", { name: "Retry save settings" })).toBeInTheDocument();
    });

    it("discards changes on clicking Discard changes", async () => {
      const user = userEvent.setup();
      renderWithRouter(["/cameras/CAM-01"]);

      const nameInput = screen.getByLabelText("Camera name") as HTMLInputElement;
      await user.type(nameInput, " Extra");
      expect(nameInput.value).toBe("Front Door Extra");

      const discardBtn = screen.getByRole("button", { name: "Discard changes" });
      await user.click(discardBtn);

      expect(nameInput.value).toBe("Front Door");
      expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    });
  });

  describe("Simple vs Advanced View Mode", () => {
    it("exposes everyday camera settings in Simple mode", () => {
      useUiStore.setState({ viewMode: "simple" });
      renderWithRouter(["/cameras/CAM-01"]);

      expect(screen.getByRole("tab", { name: "Details" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Health" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Video" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Image" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "On-screen text" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Maintenance" })).toBeInTheDocument();
    });

    it("shows all tabs in Advanced mode", () => {
      useUiStore.setState({ viewMode: "advanced" });
      renderWithRouter(["/cameras/CAM-01"]);

      expect(screen.getByRole("tab", { name: "Details" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Video" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Image" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "On-screen text" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Health" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Maintenance" })).toBeInTheDocument();
    });

    it("opens the requested video settings in everyday view", () => {
      useUiStore.setState({ viewMode: "simple" });
      renderWithRouter(["/cameras/CAM-01?tab=video"]);

      expect(screen.getByRole("tab", { name: "Video" })).toHaveAttribute("data-state", "active");
    });
  });

  describe("Maintenance Tab", () => {
    it("renders reboot and factory reset buttons when Maintenance tab is selected in advanced mode", async () => {
      const user = userEvent.setup();
      useUiStore.setState({ viewMode: "advanced" });
      renderWithRouter(["/cameras/CAM-01"]);

      const maintTab = screen.getByRole("tab", { name: "Maintenance" });
      await user.click(maintTab);

      expect(screen.getByRole("button", { name: "Reboot camera" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Factory reset camera" })).toBeInTheDocument();
    });

    it("renders maintenance tab directly when route has ?tab=maintenance", () => {
      useUiStore.setState({ viewMode: "advanced" });
      renderWithRouter(["/cameras/CAM-01?tab=maintenance"]);
      expect(screen.getByRole("button", { name: "Reboot camera" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Factory reset camera" })).toBeInTheDocument();
    });
  });

  describe("Capability Gating in Image Tab", () => {
    it("shows WDR card and warning when wdr_supported is true", async () => {
      const user = userEvent.setup();
      renderWithRouter(["/cameras/CAM-01?tab=image"]);

      expect(screen.getByText("Wide Dynamic Range (WDR)")).toBeInTheDocument();
      expect(
        screen.getByText("Changing WDR switches the sensor mode and may restart the camera briefly.")
      ).toBeInTheDocument();
    });

    it("hides WDR card when wdr_supported is false", () => {
      mockSettingsData.imaging.options.wdr_supported = false;
      renderWithRouter(["/cameras/CAM-01?tab=image"]);

      expect(screen.queryByText("Wide Dynamic Range (WDR)")).not.toBeInTheDocument();
      expect(
        screen.queryByText("Changing WDR switches the sensor mode and may restart the camera briefly.")
      ).not.toBeInTheDocument();
    });
  });

  describe("Exposure & White Balance (old VMS parity)", () => {
    it("is hidden when the camera reports no exposure or white balance options", () => {
      renderWithRouter(["/cameras/CAM-01?tab=image"]);
      expect(screen.queryByText("Exposure & White Balance")).not.toBeInTheDocument();
    });

    it("offers only the camera's modes, shows time/gain in manual, and saves them", async () => {
      const user = userEvent.setup();
      const original = structuredClone(mockSettingsData.imaging);
      Object.assign(mockSettingsData.imaging.current, {
        exposure_mode: "AUTO",
        exposure_time: 10000,
        exposure_gain: 5,
        white_balance_mode: "AUTO",
      });
      Object.assign(mockSettingsData.imaging.options, {
        exposure_modes: ["AUTO", "MANUAL"],
        exposure_time_range: [10, 40000],
        exposure_gain_range: [0, 100],
        white_balance_modes: ["AUTO", "MANUAL"],
      });
      try {
        mockSaveImagingFn.mockClear();
        renderWithRouter(["/cameras/CAM-01?tab=image"]);
        expect(screen.getByText("Exposure & White Balance")).toBeInTheDocument();
        expect(screen.queryByLabelText("Exposure Time (µs)")).not.toBeInTheDocument();

        await user.selectOptions(screen.getByLabelText("Exposure Control"), "MANUAL");
        expect(screen.getByLabelText("Exposure Time (µs)")).toBeInTheDocument();
        expect(screen.getByLabelText("Gain")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Save changes" }));
        await waitFor(() => expect(mockSaveImagingFn).toHaveBeenCalled());
        expect(mockSaveImagingFn.mock.calls[0][0]).toMatchObject({
          exposure_mode: "MANUAL",
          exposure_time: 10000,
          exposure_gain: 5,
          white_balance_mode: "AUTO",
        });
      } finally {
        mockSettingsData.imaging = original;
      }
    });
  });
});
