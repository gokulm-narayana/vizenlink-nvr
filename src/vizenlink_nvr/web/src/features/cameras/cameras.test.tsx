import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router";
import { CamerasPage } from "./CamerasPage";
import { useUiStore } from "@/stores/ui";
import { ApiError } from "@/lib/api";
import { toast } from "sonner";

vi.mock("sonner", () => ({
  toast: vi.fn(),
}));

let mockCamerasData: any[] = [];
let mockSettingsData: any = null;
let mockSettingsError: Error | null = null;
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
    error: mockSettingsError,
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
    mockSettingsError = null;
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
          ir_cut_filter_modes: ["AUTO", "ON", "OFF"],
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
    it("renders the overview with camera-specific live, playback and settings links", () => {
      renderWithRouter(["/cameras"]);

      // Master list shows both cameras
      expect(screen.getAllByText("Front Door").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Back Alley")).toBeInTheDocument();

      // The overview opens settings only after the user chooses a camera.
      const detailHeader = screen.getByRole("heading", { level: 2, name: "Front Door" });
      expect(detailHeader).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Details" })).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Watch Front Door" })).toHaveAttribute("href", "/live?camera=CAM-01");
      expect(screen.getAllByRole("link", { name: "Settings" })[0]).toHaveAttribute("href", "/cameras/CAM-01");
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
    it("shows saved details when a camera marked active cannot return live settings", () => {
      mockSettingsData = null;
      mockSettingsError = new ApiError(502, "Camera unavailable");
      renderWithRouter(["/cameras/CAM-01"]);

      expect(screen.getByText("Live settings unavailable")).toBeInTheDocument();
      expect(screen.getByText("Settings unavailable")).toBeVisible();
      expect(screen.getByRole("region", { name: "Saved camera details" })).toHaveTextContent("Main Entrance");
      expect(screen.queryByLabelText("Camera name")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Reload settings" })).toBeEnabled();
      // Developer sample-data previews are not offered to real users.
      expect(screen.queryByRole("link", { name: "Preview detection settings" })).not.toBeInTheDocument();
    });

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

  describe("Settings menu", () => {
    it("lists every section once, grouped, and opens the chosen one", async () => {
      const user = userEvent.setup();
      renderWithRouter(["/cameras/CAM-01"]);
      const menu = screen.getByRole("navigation", { name: "Camera settings" });
      for (const group of ["Picture", "Detection & safety", "Sound", "Device"]) {
        expect(within(menu).getByText(group)).toBeInTheDocument();
      }
      expect(within(menu).getAllByRole("tab")).toHaveLength(15);
      await user.click(within(menu).getByRole("tab", { name: "Image & night mode" }));
      expect(within(menu).getByRole("tab", { name: "Image & night mode" })).toHaveAttribute("aria-selected", "true");
      expect(screen.getByRole("tabpanel", { name: "Image & night mode" })).toBeInTheDocument();
      // One menu only: the old duplicate dropdown is gone.
      expect(screen.queryByLabelText("Camera settings section")).not.toBeInTheDocument();
    });

    it("says plainly whether the camera is recording", () => {
      renderWithRouter(["/cameras/CAM-02"]);
      expect(screen.getByText("Recording off")).toBeInTheDocument();
      expect(screen.queryByText(/Recording policy/)).not.toBeInTheDocument();
    });
  });

  describe("Simple vs Advanced View Mode", () => {
    it("exposes everyday camera settings in Simple mode", () => {
      useUiStore.setState({ viewMode: "simple" });
      renderWithRouter(["/cameras/CAM-01"]);

      expect(screen.getByRole("tab", { name: "Details" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Health" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Video quality" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Image & night mode" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "On-screen text" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Reboot & reset" })).toBeInTheDocument();
    });

    it("shows all tabs in Advanced mode", () => {
      useUiStore.setState({ viewMode: "advanced" });
      renderWithRouter(["/cameras/CAM-01"]);

      expect(screen.getByRole("tab", { name: "Details" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Video quality" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Image & night mode" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "On-screen text" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Health" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Reboot & reset" })).toBeInTheDocument();
    });

    it("opens the requested video settings in everyday view", () => {
      useUiStore.setState({ viewMode: "simple" });
      renderWithRouter(["/cameras/CAM-01?tab=video"]);

      expect(screen.getByRole("tab", { name: "Video quality" })).toHaveAttribute("data-state", "active");
    });
  });

  describe("Maintenance Tab", () => {
    it("renders reboot and factory reset buttons when Maintenance tab is selected in advanced mode", async () => {
      const user = userEvent.setup();
      useUiStore.setState({ viewMode: "advanced" });
      renderWithRouter(["/cameras/CAM-01"]);

      const maintTab = screen.getByRole("tab", { name: "Reboot & reset" });
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
    it("previews unsaved edits locally and refreshes the camera image after saving", async () => {
      const user = userEvent.setup();
      mockSaveImagingFn.mockClear();
      renderWithRouter(["/cameras/CAM-01?tab=image"]);

      const snapshot = screen.getByRole("img", { name: /camera snapshot/i });
      const originalSource = snapshot.getAttribute("src");
      fireEvent.change(screen.getByLabelText("Brightness"), { target: { value: "80" } });
      expect(screen.getByRole("img", { name: /estimated image preview/i })).toBe(snapshot);
      expect(snapshot.style.filter).toContain("brightness(1.25)");
      expect(mockSaveImagingFn).not.toHaveBeenCalled();

      await user.click(screen.getByRole("button", { name: "Show saved image" }));
      expect(snapshot.style.filter).toBe("");
      await user.click(screen.getByRole("button", { name: "Save changes" }));
      await waitFor(() => {
        expect(screen.getByRole("img", { name: /camera snapshot/i })).not.toHaveAttribute("src", originalSource);
      });
      expect(mockSaveImagingFn).toHaveBeenCalledWith(expect.objectContaining({ brightness: 80 }));

      fireEvent.error(screen.getByRole("img", { name: /camera snapshot/i }));
      expect(screen.getByText(/camera snapshot unavailable/i)).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Refresh snapshot" }));
      expect(screen.getByRole("img", { name: /camera snapshot/i })).toBeInTheDocument();
    });

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

  describe("Day / night mode (ONVIF IrCutFilter)", () => {
    it("names the modes in plain words and shows the camera's live state", () => {
      const original = structuredClone(mockSettingsData.imaging);
      mockSettingsData.imaging.current.day_night_now = "night";
      try {
        renderWithRouter(["/cameras/CAM-01?tab=image"]);
        const select = screen.getByLabelText("Day / night mode");
        expect(Array.from((select as HTMLSelectElement).options).map(o => [o.value, o.text])).toEqual([
          ["AUTO", "Auto (switches with light)"],
          ["ON", "Day (colour)"],
          ["OFF", "Night (infrared, black & white)"],
        ]);
        expect(screen.getByText("Right now: Night (infrared)")).toBeInTheDocument();
      } finally {
        mockSettingsData.imaging = original;
      }
    });

    it("offers nothing and sends nothing when the camera reports no day/night choices", async () => {
      const user = userEvent.setup();
      const original = structuredClone(mockSettingsData.imaging);
      mockSettingsData.imaging.options.ir_cut_filter_modes = [];
      try {
        mockSaveImagingFn.mockClear();
        renderWithRouter(["/cameras/CAM-01?tab=image"]);
        expect(screen.queryByLabelText("Day / night mode")).not.toBeInTheDocument();
        expect(screen.getByText("Not available on this camera.")).toBeInTheDocument();
        await user.selectOptions(screen.getByLabelText("Night Vision Mode"), "grey");
        await user.click(screen.getByRole("button", { name: "Save changes" }));
        await waitFor(() => expect(mockSaveImagingFn).toHaveBeenCalled());
        expect(mockSaveImagingFn.mock.calls[0][0]).not.toHaveProperty("ir_cut_filter");
      } finally {
        mockSettingsData.imaging = original;
      }
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
