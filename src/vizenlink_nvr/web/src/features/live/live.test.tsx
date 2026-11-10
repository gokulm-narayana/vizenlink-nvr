import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach, onTestFinished } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LivePage, swapChannels } from "./LivePage";
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
      screen.getByText(/Connect your first camera/i)
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

  it("offers all layouts in both view modes", async () => {
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
    expect(screen.queryByRole("radio", { name: "4 by 4 grid" })).toBeInTheDocument();
  });

  it("preserves a saved 4x4 layout in everyday view", async () => {
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
    const recording = [{ camera_serial: "CAM1", mode: "continuous", is_recording: true }];

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
  it("filters cameras, saves a view, and restores its cameras and layout", async () => {
    const user = userEvent.setup();
    const cameras = [
      { id: 1, serial: "CAM1", name: "Entrance", location: "Ground floor", state: "online" },
      { id: 2, serial: "CAM2", name: "Warehouse", location: "Back", state: "online" },
    ];
    renderLivePage(cameras, "owner");
    await screen.findByText("Entrance");
    await user.type(screen.getByRole("textbox", { name: "Search cameras" }), "Ground");
    expect(screen.queryByText("Warehouse")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save current view" }));
    await user.type(screen.getByRole("textbox", { name: "View name" }), "Entrances");
    await user.click(screen.getByRole("button", { name: "Save view" }));
    await user.click(screen.getByRole("button", { name: "Show all" }));
    expect(screen.getByText("Warehouse")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Saved views"), "Entrances");
    expect(screen.queryByText("Warehouse")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Playback" })).toHaveAttribute("href", "/playback?camera=CAM1");
    const stored = JSON.parse(localStorage.getItem("vizenlink_live_preferences_1") || "{}");
    expect(stored.views[0].serials).toEqual(["CAM1"]);
  });

  it("favorites are selectable and recording policy alone never shows REC", async () => {
    const user = userEvent.setup();
    renderLivePage([{ id: 1, serial: "CAM1", name: "Entrance", state: "online" }], "owner", [{ camera_serial: "CAM1", mode: "scheduled" }]);
    await screen.findByText("Entrance");
    expect(screen.queryByText("REC")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Favorites" }));
    expect(screen.getByText("No cameras in this view")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Favorites" }));
    await user.click(screen.getByRole("button", { name: "Add Entrance to favorites" }));
    await user.click(screen.getByRole("button", { name: "Favorites" }));
    expect(screen.getByText("Entrance")).toBeInTheDocument();
  });

  it("swapChannels swaps two cameras and ignores unknown serials", () => {
    expect(swapChannels(["A", "B", "C"], "A", "C")).toEqual(["C", "B", "A"]);
    expect(swapChannels(["A", "B"], "A", "Z")).toEqual(["A", "B"]);
  });

  it("numbers tiles as channels, shows empty channels, and moves a camera via the right-click menu", async () => {
    const user = userEvent.setup();
    GridStorage.save({ dimension: 2, page: 0, slotAssignments: {} });
    // Landscape desktop: fit-to-screen grid with empty channel slots.
    const original = window.matchMedia;
    window.matchMedia = ((q: string) => ({
      matches: q.includes("landscape"),
      media: q,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    onTestFinished(() => {
      window.matchMedia = original;
    });
    renderLivePage(
      [
        { id: 1, serial: "CAM1", name: "Gate", state: "online" },
        { id: 2, serial: "CAM2", name: "Yard", state: "online" },
        { id: 3, serial: "CAM3", name: "Lobby", state: "online" },
      ],
      "owner"
    );
    await screen.findByText("Gate");
    expect(screen.getByText("CH 1")).toBeInTheDocument();
    expect(screen.getByText("CH 3")).toBeInTheDocument();
    // 2x2 grid with 3 cameras leaves CH 4 empty, like the old VMS.
    expect(screen.getByText("Empty channel")).toBeInTheDocument();

    fireEvent.contextMenu(screen.getByRole("group", { name: /Gate/ }));
    const menu = await screen.findByRole("menu", { name: "Gate actions" });
    expect(menu).toHaveTextContent("Full screen");
    expect(menu).toHaveTextContent("Take snapshot");
    expect(menu).toHaveTextContent("Replay last 5 minutes");

    await user.click(screen.getByRole("menuitem", { name: /Move to channel/ }));
    // Keyboard selection (Radix sub-menu items ignore synthetic pointer clicks in jsdom).
    const target = await screen.findByRole("menuitem", { name: "CH 3 · Lobby" });
    target.focus();
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem("vizenlink_live_order_1") || "[]")).toEqual(["CAM3", "CAM2", "CAM1"]);
    });
  });

  it("offers a whole-grid full screen button", async () => {
    renderLivePage([{ id: 1, serial: "CAM1", name: "Gate", state: "online" }], "viewer");
    await screen.findByText("Gate");
    expect(screen.getByRole("button", { name: "Full screen grid" })).toBeInTheDocument();
  });
});
