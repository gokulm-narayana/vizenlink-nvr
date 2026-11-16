import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach, onTestFinished } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
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
  recordingData: any[] = [],
  initialEntries: string[] = ["/"]
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
    if (urlStr.includes("/api/v1/playback/manual-clip")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            id: 99,
            camera_serial: "CAM1",
            item_type: "manual_clip",
            title: "Manual clip",
            file_path: "gallery/clips/cam1/manual.mp4",
            file_size_bytes: 1024,
            duration_seconds: 60,
            captured_at: new Date().toISOString(),
            created_at: new Date().toISOString(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    return Promise.resolve(new Response(null, { status: 404 }));
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={0}>
        <MemoryRouter initialEntries={initialEntries}>
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

  describe("full screen", () => {
    const setFullscreenElement = (value: Element | null) => {
      Object.defineProperty(document, "fullscreenElement", { configurable: true, value });
      act(() => { document.dispatchEvent(new Event("fullscreenchange")); });
    };
    let request: ReturnType<typeof vi.fn>;
    const twoCameras = [
      { id: 1, serial: "CAM1", name: "Driveway", state: "online" },
      { id: 2, serial: "CAM2", name: "Yard", state: "online" },
    ];
    const root = () => document.querySelector("[data-live-fullscreen]") as HTMLElement;

    beforeEach(() => {
      request = vi.fn(function (this: HTMLElement) { setFullscreenElement(this); return Promise.resolve(); });
      HTMLElement.prototype.requestFullscreen = request as unknown as typeof HTMLElement.prototype.requestFullscreen;
    });
    afterEach(() => setFullscreenElement(null));

    it("corner button fills the screen with that camera on the main stream and undoes it", async () => {
      const user = userEvent.setup();
      GridStorage.save({ dimension: 2, page: 0, slotAssignments: {} });
      renderLivePage(twoCameras, "owner");
      await screen.findByText("Driveway");

      await user.click(screen.getAllByRole("button", { name: "Full screen camera" })[0]);
      // The whole page goes full screen, so menus and dialogs mounted on <body> stay visible.
      expect(request).toHaveBeenCalledTimes(1);
      expect(request.mock.contexts[0]).toBe(document.documentElement);
      expect(root()).toHaveAttribute("data-live-fullscreen", "true");
      expect(screen.queryByText("Yard")).not.toBeInTheDocument();
      await waitFor(() => expect(mockSwitchStream).toHaveBeenCalledWith("main"));

      await user.click(screen.getByRole("button", { name: "Exit full screen camera" }));
      expect(root()).toHaveAttribute("data-live-fullscreen", "false");
      expect(screen.getByText("Yard")).toBeInTheDocument();
      await waitFor(() => expect(mockSwitchStream).toHaveBeenCalledWith("sub"));
    });

    it("toolbar button shows every camera full screen and Esc in the browser leaves it", async () => {
      const user = userEvent.setup();
      GridStorage.save({ dimension: 2, page: 0, slotAssignments: {} });
      renderLivePage(twoCameras, "viewer");
      await screen.findByText("Driveway");

      await user.click(screen.getByRole("button", { name: "Full screen grid" }));
      expect(request.mock.contexts[0]).toBe(document.documentElement);
      expect(root()).toHaveAttribute("data-live-fullscreen", "true");
      expect(screen.getByText("Driveway")).toBeInTheDocument();
      expect(screen.getByText("Yard")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Exit full screen" })).toBeVisible();

      // The toolbar stays out of the picture until it is asked for, so it cannot cover the top row.
      const toolbar = document.querySelector(".live-toolbar") as HTMLElement;
      expect(toolbar).toHaveClass("opacity-0", "pointer-events-none");
      await user.click(screen.getByRole("button", { name: "Show toolbar" }));
      expect(toolbar).not.toHaveClass("opacity-0");
      expect(screen.queryByRole("button", { name: "Show toolbar" })).not.toBeInTheDocument();

      // The browser's own Esc only changes the fullscreen state; the page must follow it.
      setFullscreenElement(null);
      await waitFor(() => expect(root()).toHaveAttribute("data-live-fullscreen", "false"));
    });

    it("sidebar full screen view shows every camera, whatever grid and page were saved", async () => {
      const user = userEvent.setup();
      GridStorage.save({ dimension: 2, page: 1, slotAssignments: {} });
      const five = [1, 2, 3, 4, 5].map((i) => ({ id: i, serial: `CAM${i}`, name: `Camera ${i}`, state: "online" }));
      renderLivePage(five, "viewer", [], ["/live?wall=1&fit=all"]);
      for (const cam of five) expect(await screen.findByText(cam.name)).toBeInTheDocument();
      expect(root()).toHaveAttribute("data-live-fullscreen", "true");
      // Five cameras need a 3×3 grid; the saved 2×2 would have hidden one on a second page.
      expect(screen.getByRole("radio", { name: "3 by 3 grid" })).toBeChecked();

      // Leaving goes back to the saved grid.
      await user.click(screen.getByRole("button", { name: "Exit full screen" }));
      expect(screen.getByRole("radio", { name: "2 by 2 grid" })).toBeChecked();
    });

    it("still fills the window when the browser refuses full screen, and Esc leaves it", async () => {
      const user = userEvent.setup();
      HTMLElement.prototype.requestFullscreen = vi.fn(() => Promise.reject(new Error("denied"))) as unknown as typeof HTMLElement.prototype.requestFullscreen;
      renderLivePage(twoCameras, "viewer");
      await screen.findByText("Driveway");
      await user.click(screen.getByRole("button", { name: "Full screen grid" }));
      expect(root()).toHaveAttribute("data-live-fullscreen", "true");
      await user.keyboard("{Escape}");
      expect(root()).toHaveAttribute("data-live-fullscreen", "false");
    });
  });

  it("a double-click or a drag that starts on a tile button never moves or enlarges the tile", async () => {
    const user = userEvent.setup();
    GridStorage.save({ dimension: 2, page: 0, slotAssignments: {} });
    renderLivePage(
      [
        { id: 1, serial: "CAM1", name: "Driveway", state: "online" },
        { id: 2, serial: "CAM2", name: "Yard", state: "online" },
      ],
      "owner"
    );
    await screen.findByText("Driveway");
    const star = screen.getByRole("button", { name: "Add Driveway to favorites" });

    await user.dblClick(star);
    expect(screen.getByText("Yard")).toBeInTheDocument();

    // A drag from a button is cancelled, so the browser delivers the click instead.
    // The browser reports the tile, not the button, as the drag target.
    const tileEl = screen.getByRole("group", { name: /Driveway/i });
    fireEvent.pointerDown(star);
    expect(fireEvent.dragStart(tileEl)).toBe(false);
    fireEvent.pointerDown(tileEl);
    // A drag from the picture itself is still allowed (drag to swap channels).
    expect(fireEvent.dragStart(screen.getByRole("group", { name: /Driveway/i }), { dataTransfer: { setData: vi.fn(), effectAllowed: "" } })).toBe(true);

    await user.dblClick(screen.getByRole("group", { name: /Driveway/i }));
    expect(screen.queryByText("Yard")).not.toBeInTheDocument();
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

  it("switches back from maximized single camera to multi-camera grid when clicking 2x2", async () => {
    const user = userEvent.setup();
    GridStorage.save({ dimension: 2, page: 0, slotAssignments: {} });
    const cameras = [
      { id: 1, serial: "CAM1", name: "Gate", state: "online" },
      { id: 2, serial: "CAM2", name: "Yard", state: "online" },
    ];
    renderLivePage(cameras, "owner");
    await screen.findByText("Gate");
    expect(screen.getByText("Yard")).toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole("group", { name: /Gate/i }), { key: "Enter" });
    expect(screen.queryByText("Yard")).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "2 by 2 grid" }));
    expect(screen.getByText("Yard")).toBeInTheDocument();
  });

  it("records a manual clip, prompts at 30s to continue or stop, and saves on stop", async () => {
    renderLivePage([{ id: 1, serial: "CAM1", name: "Gate", state: "online" }], "owner");
    await screen.findByText("Gate");

    vi.useFakeTimers();
    onTestFinished(() => {
      vi.useRealTimers();
    });

    fireEvent.click(screen.getByRole("button", { name: "Record clip" }));
    expect(screen.getByText("CLIP 0:00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop clip recording" })).toBeInTheDocument();

    // Advance 30s to trigger continue/stop prompt
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(screen.getByText("Continue manual clip recording?")).toBeInTheDocument();
    expect(screen.getByText(/has reached 30s/i)).toBeInTheDocument();

    // Continue for another 30s
    fireEvent.click(screen.getByRole("button", { name: "Continue recording (+30s)" }));
    expect(screen.queryByText("Continue manual clip recording?")).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(screen.getByText("Continue manual clip recording?")).toBeInTheDocument();
    expect(screen.getByText(/has reached 60s/i)).toBeInTheDocument();

    // Stop & save clip
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Stop & save clip" }));
      await Promise.resolve();
    });

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const manualClipCall = fetchCalls.find(([u]) => u.toString().includes("/api/v1/playback/manual-clip"));
    expect(manualClipCall).toBeDefined();
    const requestInit = manualClipCall?.[1] as RequestInit;
    expect(requestInit.method).toBe("POST");
    expect(JSON.parse(String(requestInit.body))).toMatchObject({
      camera_serial: "CAM1",
    });
  });
});
