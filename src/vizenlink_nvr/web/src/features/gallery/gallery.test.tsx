import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { GalleryPage } from "./GalleryPage";
import { GalleryCard } from "./GalleryCard";
import { PreviewDialog } from "./PreviewDialog";
import type { GalleryItem } from "./api";
import { useUiStore } from "@/stores/ui";

const mockNavigate = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual("react-router");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

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
  }),
  useAuthStatus: () => ({
    data: { site_timezone: "UTC", user: mockCurrentUser },
  }),
  useCurrentUser: () => mockCurrentUser,
}));

describe("Gallery Feature", () => {
  const mockSnapshot: GalleryItem = {
    id: 10,
    camera_serial: "CAM-01",
    item_type: "snapshot",
    title: "Front Door Motion Snapshot",
    file_path: "snapshots/cam1_10.jpg",
    file_size_bytes: 1048576, // 1 MB
    captured_at: "2026-06-15T12:00:00Z",
    created_at: "2026-06-15T12:00:01Z",
    user_id: 1,
  };

  const mockClip: GalleryItem = {
    id: 11,
    camera_serial: "CAM-02",
    item_type: "export_clip",
    title: "Backyard Delivery Clip",
    file_path: "clips/cam2_11.mp4",
    file_size_bytes: 5242880, // 5 MB
    duration_seconds: 45,
    captured_at: "2026-06-15T13:00:00Z",
    created_at: "2026-06-15T13:00:05Z",
    user_id: 2,
  };

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
    });
  });

  const renderWithProviders = (
    ui: React.ReactElement,
    initialEntries = ["/gallery"]
  ) => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/gallery" element={ui} />
            <Route path="*" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("GalleryCard", () => {
    it("renders snapshot card with title, camera, time", () => {
      const onClick = vi.fn();
      renderWithProviders(
        <GalleryCard
          item={mockSnapshot}
          cameraName="Front Door"
          onClick={onClick}
          zone="UTC"
        />
      );

      expect(screen.getByText("Front Door Motion Snapshot")).toBeInTheDocument();
      expect(screen.getByText("Front Door")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button"));
      expect(onClick).toHaveBeenCalledWith(mockSnapshot);
    });

    it("renders clip card with duration chip", () => {
      renderWithProviders(
        <GalleryCard
          item={mockClip}
          cameraName="Backyard"
          onClick={vi.fn()}
          zone="UTC"
        />
      );

      expect(screen.getByText("Backyard Delivery Clip")).toBeInTheDocument();
      expect(screen.getByText("45s")).toBeInTheDocument();
    });
  });

  describe("PreviewDialog", () => {
    it("renders preview with metadata, download and open in playback", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();

      renderWithProviders(
        <PreviewDialog
          item={mockSnapshot}
          cameraName="Front Door"
          isOpen={true}
          onClose={onClose}
          zone="UTC"
        />
      );

      expect(screen.getByText("Front Door Motion Snapshot")).toBeInTheDocument();
      expect(screen.getByText("Front Door")).toBeInTheDocument();
      expect(screen.getByText("1.0 MB")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Close preview" })
      ).toBeInTheDocument();

      const openPlaybackBtn = screen.getByRole("button", { name: "Open in Playback" });
      await user.click(openPlaybackBtn);

      expect(onClose).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith(
        "/playback?camera=CAM-01&t=2026-06-15T12%3A00%3A00Z"
      );
    });

    it("hides delete button for viewer role, shows for operator", () => {
      // Operator sees delete
      const { rerender } = renderWithProviders(
        <PreviewDialog
          item={mockSnapshot}
          cameraName="Front Door"
          isOpen={true}
          onClose={vi.fn()}
          zone="UTC"
        />
      );

      expect(screen.getByRole("button", { name: "Delete snapshot" })).toBeInTheDocument();

      // Viewer does not see delete
      mockCurrentUser = {
        id: 3,
        username: "viewer1",
        role: "viewer",
        permissions: ["*"],
      };

      rerender(
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <MemoryRouter initialEntries={["/gallery"]}>
            <PreviewDialog
              item={mockSnapshot}
              cameraName="Front Door"
              isOpen={true}
              onClose={vi.fn()}
              zone="UTC"
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.queryByRole("button", { name: "Delete snapshot" })).not.toBeInTheDocument();
    });

    it("handles delete confirmation and error handling", async () => {
      const user = userEvent.setup();
      global.fetch = vi.fn().mockImplementation((url: string, opts?: any) => {
        if (opts?.method === "DELETE") {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: async () => ({ detail: "Disk error" }),
          });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });

      renderWithProviders(
        <PreviewDialog
          item={mockClip}
          cameraName="Backyard"
          isOpen={true}
          onClose={vi.fn()}
          zone="UTC"
        />
      );

      const deleteBtn = screen.getByRole("button", { name: "Delete clip" });
      await user.click(deleteBtn);

      // Confirm dialog appears
      expect(screen.getByText("Delete this clip?")).toBeInTheDocument();
      expect(
        screen.getByText("This permanently removes the file from the NVR and can't be undone.")
      ).toBeInTheDocument();

      const confirmBtn = screen.getByRole("button", { name: "Delete clip" });
      await user.click(confirmBtn);

      await waitFor(() => {
        expect(
          screen.getByText("Couldn't delete the clip. Check your connection and try again.")
        ).toBeInTheDocument();
      });

      expect(screen.getByRole("button", { name: "Retry delete clip" })).toBeInTheDocument();
    });
  });

  describe("GalleryPage", () => {
    it("renders empty state when no items exist", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
      });

      renderWithProviders(<GalleryPage />);

      await waitFor(() => {
        expect(screen.getByText("Nothing saved yet")).toBeInTheDocument();
      });
      expect(
        screen.getByText(
          "Nothing saved yet. Save a snapshot from Live or Playback, or export a clip, and it will appear here."
        )
      ).toBeInTheDocument();
    });

    it("switches tabs between snapshots and clips", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          items: [mockSnapshot, mockClip],
          total: 2,
          limit: 50,
          offset: 0,
        }),
      });

      const user = userEvent.setup();
      renderWithProviders(<GalleryPage />);

      await waitFor(() => {
        expect(screen.getByText("Front Door Motion Snapshot")).toBeInTheDocument();
      });

      // Default Snapshots tab shows snapshot, hides clip
      expect(screen.queryByText("Backyard Delivery Clip")).not.toBeInTheDocument();

      // Switch to Clips tab
      const clipsTab = screen.getByRole("tab", { name: "Clips" });
      await user.click(clipsTab);

      expect(screen.getByText("Backyard Delivery Clip")).toBeInTheDocument();
      expect(screen.queryByText("Front Door Motion Snapshot")).not.toBeInTheDocument();
    });

    it("filters by user in advanced view mode", async () => {
      useUiStore.setState({ viewMode: "advanced" });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          items: [mockSnapshot, mockClip],
          total: 2,
          limit: 50,
          offset: 0,
        }),
      });

      renderWithProviders(<GalleryPage />);

      await waitFor(() => {
        expect(screen.getByText("Front Door Motion Snapshot")).toBeInTheDocument();
      });

      // User filter is present in Advanced view
      expect(screen.getByText("Anyone")).toBeInTheDocument();
    });
  });
});
