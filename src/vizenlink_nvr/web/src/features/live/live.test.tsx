import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LivePage } from "./LivePage";
import { useUiStore } from "@/stores/ui";
import { GridStorage } from "@/services/grid_storage";

// Stub TilePlayer
const mockSwitchStream = vi.fn();
const mockRetryNow = vi.fn();
const mockCleanup = vi.fn();
const mockAttach = vi.fn();

vi.mock("@/services/player", () => {
  return {
    TilePlayer: class MockTilePlayer {
      serial: string;
      stream: string;
      onStateChange?: (state: string) => void;

      constructor(config: any) {
        this.serial = config.serial;
        this.stream = config.stream;
        this.onStateChange = config.onStateChange;
        // Default trigger connecting state
        setTimeout(() => {
          this.onStateChange?.("live");
        }, 10);
      }

      attach(video: any) {
        mockAttach(video);
        return Promise.resolve();
      }

      switchStream(stream: string) {
        this.stream = stream;
        mockSwitchStream(stream);
        return Promise.resolve();
      }

      retryNow() {
        mockRetryNow();
      }

      cleanup() {
        mockCleanup();
      }

      getState() {
        return "live";
      }
    },
  };
});

function renderLivePage(
  camerasData: any[] = [],
  role: "viewer" | "operator" | "owner" = "viewer",
  recordingData: any[] = []
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
    const urlStr = url.toString();
    if (urlStr.includes("/api/v1/auth/status")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            initialized: true,
            authenticated: true,
            user: { id: 1, username: "testuser", role, permissions: ["*"] },
            site_timezone: "UTC",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    if (urlStr.includes("/api/v1/cameras")) {
      return Promise.resolve(
        new Response(JSON.stringify(camerasData), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/recording/status")) {
      return Promise.resolve(
        new Response(JSON.stringify(recordingData), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    return Promise.resolve(new Response(null, { status: 404 }));
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={0}>
        <MemoryRouter>
          <LivePage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

describe("LivePage & VideoTile", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    useUiStore.setState({ viewMode: "advanced" });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows operator/owner empty state with primary Add camera button when 0 cameras", async () => {
    renderLivePage([], "owner");

    await waitFor(() => {
      expect(screen.getByText("No cameras yet")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Add a camera by entering its details/i)
    ).toBeInTheDocument();
    const addLink = screen.getByRole("link", { name: "Add camera" });
    expect(addLink).toHaveAttribute("href", "/cameras/add");
  });

  it("shows viewer empty state without Add button when 0 cameras", async () => {
    renderLivePage([], "viewer");

    await waitFor(() => {
      expect(screen.getByText("No cameras assigned")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Ask the NVR owner to give you access to a camera.")
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Add camera" })).not.toBeInTheDocument();
  });

  it("defaults to 1x1 grid when exactly 1 camera and no stored preference exists", async () => {
    const singleCam = [{ id: 1, serial: "CAM1", name: "Front Door", state: "online" }];
    renderLivePage(singleCam, "owner");

    await waitFor(() => {
      expect(screen.getByText("Front Door")).toBeInTheDocument();
    });

    const activeToggle = screen.getByRole("radio", { name: "1 by 1 grid" });
    expect(activeToggle).toHaveAttribute("data-state", "on");
  });

  it("offers 1x1 to 4x4 in advanced view and limits to 3x3 in simple view", async () => {
    const cameras = Array.from({ length: 5 }, (_, i) => ({
      id: i + 1,
      serial: `CAM${i + 1}`,
      name: `Camera ${i + 1}`,
      state: "online",
    }));

    useUiStore.setState({ viewMode: "advanced" });
    const { unmount } = renderLivePage(cameras, "owner");

    await waitFor(() => {
      expect(screen.getByRole("radio", { name: "4 by 4 grid" })).toBeInTheDocument();
    });

    unmount();

    useUiStore.setState({ viewMode: "simple" });
    renderLivePage(cameras, "owner");

    await waitFor(() => {
      expect(screen.getByRole("radio", { name: "3 by 3 grid" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("radio", { name: "4 by 4 grid" })).not.toBeInTheDocument();
  });

  it("stored 4x4 renders as 3x3 in simple view without overwriting stored preference", async () => {
    GridStorage.save({ dimension: 4, page: 0, slotAssignments: {} });
    useUiStore.setState({ viewMode: "simple" });

    const cameras = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      serial: `CAM${i + 1}`,
      name: `Camera ${i + 1}`,
      state: "online",
    }));

    renderLivePage(cameras, "owner");

    await waitFor(() => {
      expect(screen.getByText("Camera 1")).toBeInTheDocument();
    });

    // Stored preference is still 4
    const raw = GridStorage.load();
    expect(raw.dimension).toBe(4);
  });

  it("renders REC indicator when camera is actively recording", async () => {
    const cameras = [{ id: 1, serial: "CAM1", name: "Driveway", state: "online" }];
    const recording = [{ camera_serial: "CAM1", mode: "continuous" }];

    renderLivePage(cameras, "owner", recording);

    await waitFor(() => {
      expect(screen.getByText("REC")).toBeInTheDocument();
    });
  });

  it("handles maximize and switches stream to main, restoring on close", async () => {
    const user = userEvent.setup();
    const cameras = [{ id: 1, serial: "CAM1", name: "Driveway", state: "online" }];

    renderLivePage(cameras, "owner");

    await waitFor(() => {
      expect(screen.getByText("Driveway")).toBeInTheDocument();
    });

    const maxBtn = screen.getByRole("button", { name: "Maximize tile" });
    await user.click(maxBtn);

    expect(mockSwitchStream).toHaveBeenCalledWith("main");

    const minBtn = screen.getByRole("button", { name: "Close maximized tile" });
    await user.click(minBtn);

    expect(mockSwitchStream).toHaveBeenCalledWith("sub");
  });

  it("maximizes tile on Enter key and un-maximizes on Escape", async () => {
    const cameras = [{ id: 1, serial: "CAM1", name: "Driveway", state: "online" }];

    renderLivePage(cameras, "owner");

    await waitFor(() => {
      expect(screen.getByText("Driveway")).toBeInTheDocument();
    });

    const tile = screen.getByRole("group", { name: /Driveway/i });
    fireEvent.keyDown(tile, { key: "Enter" });

    expect(mockSwitchStream).toHaveBeenCalledWith("main");

    const maxTile = screen.getByRole("group", { name: /Driveway/i });
    fireEvent.keyDown(maxTile, { key: "Escape" });

    expect(mockSwitchStream).toHaveBeenCalledWith("sub");
  });
});
