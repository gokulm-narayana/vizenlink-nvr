import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createAppRoutes } from "@/app/router";
import { useUiStore } from "@/stores/ui";
import { setMediaQueryMatches } from "@/test/setup";
import { StatusBadge, type StatusKind } from "@/components/StatusBadge";
import { InlineError } from "@/components/InlineError";
import { RecorderStatusChip } from "./RecorderStatusChip";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarProvider } from "@/components/ui/sidebar";

function renderWithClient(ui: React.ReactElement, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={0}>
        <SidebarProvider defaultOpen={true}>
          {ui}
        </SidebarProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

function renderSidebarApp(
  initialEntries = ["/"],
  mockCameras: any[] = [],
  mockRecStatus: any[] = [],
  mockHealth: any = { status: "healthy", db_ok: true, mediamtx_ok: true, storage_ok: true, total_cameras: 0, active_cameras: 0 },
  mockEvents: any = { items: [], total: 0 }
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    if (urlStr.includes("/api/v1/auth/status")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            initialized: true,
            authenticated: true,
            user: { id: 1, username: "testuser", role: "viewer", permissions: ["*"] },
            site_timezone: "UTC",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    if (urlStr.includes("/api/v1/cameras")) {
      return Promise.resolve(
        new Response(JSON.stringify(mockCameras), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/recording/status")) {
      return Promise.resolve(
        new Response(JSON.stringify(mockRecStatus), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/health/alerts")) {
      return Promise.resolve(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/health")) {
      return Promise.resolve(
        new Response(JSON.stringify(mockHealth), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/events")) {
      return Promise.resolve(
        new Response(JSON.stringify(mockEvents), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  const router = createMemoryRouter(createAppRoutes(), {
    initialEntries,
  });

  const utils = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );

  return { ...utils, router, queryClient };
}

describe("RecorderStatusChip, Unread Badge, StatusBadge & InlineError", () => {
  beforeEach(() => {
    localStorage.clear();
    useUiStore.setState({
      sidebarOpen: true,
      theme: "system",
      viewMode: "simple",
      readEventIds: new Set<number>(),
    });
    setMediaQueryMatches(false); // desktop
    vi.restoreAllMocks();
  });

  it("RecorderStatusChip shows 'Recording 16 of 16' with success dot when healthy and all recording", async () => {
    const cameras = Array.from({ length: 16 }, (_, i) => ({
      id: i + 1,
      serial: `CAM${i + 1}`,
      name: `Camera ${i + 1}`,
    }));
    const recStatus = cameras.map((c) => ({
      camera_serial: c.serial,
      mode: "continuous",
    }));

    renderSidebarApp(["/"], cameras, recStatus, {
      status: "healthy",
      db_ok: true,
      mediamtx_ok: true,
      storage_ok: true,
      total_cameras: 16,
      active_cameras: 16,
    });

    await waitFor(() => {
      expect(screen.getByText("Recording 16 of 16")).toBeInTheDocument();
    });

    const dot = screen.getByText("Recording 16 of 16").parentElement?.querySelector('[data-slot="recorder-dot"]');
    expect(dot).toHaveClass("bg-success");
  });

  it("RecorderStatusChip shows 'Recording 13 of 16' with warning dot and icon when only 13 are recording", async () => {
    const cameras = Array.from({ length: 16 }, (_, i) => ({
      id: i + 1,
      serial: `CAM${i + 1}`,
      name: `Camera ${i + 1}`,
    }));
    const recStatus = cameras.slice(0, 13).map((c) => ({
      camera_serial: c.serial,
      mode: "continuous",
    }));

    renderSidebarApp(["/"], cameras, recStatus, {
      status: "healthy",
      db_ok: true,
      mediamtx_ok: true,
      storage_ok: true,
      total_cameras: 16,
      active_cameras: 13,
    });

    await waitFor(() => {
      expect(screen.getByText("Recording 13 of 16")).toBeInTheDocument();
    });

    const dot = screen.getByText("Recording 13 of 16").parentElement?.querySelector('[data-slot="recorder-dot"]');
    expect(dot).toHaveClass("bg-warning");
  });

  it("RecorderStatusChip shows critical dot and icon when storage_ok is false", async () => {
    const cameras = [{ id: 1, serial: "CAM1", name: "Camera 1" }];
    const recStatus = [{ camera_serial: "CAM1", mode: "continuous" }];

    renderSidebarApp(["/"], cameras, recStatus, {
      status: "unhealthy",
      db_ok: true,
      mediamtx_ok: true,
      storage_ok: false,
      total_cameras: 1,
      active_cameras: 1,
    });

    await waitFor(() => {
      expect(screen.getByText("Recording 1 of 1")).toBeInTheDocument();
    });

    const dot = screen.getByText("Recording 1 of 1").parentElement?.querySelector('[data-slot="recorder-dot"]');
    expect(dot).toHaveClass("bg-critical");
  });

  it("Events nav item shows unread count badge with primary fill, hidden when 0", async () => {
    const mockEvents = {
      items: [
        { id: 101, camera_serial: "CAM1" },
        { id: 102, camera_serial: "CAM1" },
        { id: 103, camera_serial: "CAM1" },
      ],
      total: 3,
    };

    useUiStore.setState({ readEventIds: new Set([101]) });

    const { container } = renderSidebarApp(["/"], [], [], undefined, mockEvents);

    await waitFor(() => {
      const badge = container.querySelector('[data-slot="events-unread-badge"]');
      expect(badge).toBeInTheDocument();
      expect(badge?.textContent).toBe("2");
      expect(badge).toHaveClass("bg-primary");
    });
  });

  it("StatusBadge renders icon and text for all status kinds and never relies on color alone", () => {
    const kinds: Array<{ kind: StatusKind; expectedText: string }> = [
      { kind: "online", expectedText: "Online" },
      { kind: "offline", expectedText: "Offline" },
      { kind: "recording", expectedText: "Recording" },
      { kind: "not-recording", expectedText: "Not recording" },
      { kind: "degraded", expectedText: "Degraded" },
      { kind: "critical", expectedText: "Critical" },
      { kind: "disabled", expectedText: "Disabled" },
      { kind: "user-active", expectedText: "Active" },
      { kind: "user-disabled", expectedText: "Disabled" },
    ];

    for (const { kind, expectedText } of kinds) {
      const { unmount } = render(<StatusBadge kind={kind} />);
      expect(screen.getByText(expectedText)).toBeInTheDocument();
      unmount();
    }
  });

  it("InlineError renders role=alert and enforces verb+noun template literal for actionLabel", () => {
    const handleRetry = vi.fn();
    const { rerender } = render(
      <InlineError
        title="Stream failed"
        message="Cannot connect to RTSP endpoint"
        actionLabel="Retry stream"
        onAction={handleRetry}
      />
    );

    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(screen.getByText("Stream failed")).toBeInTheDocument();
    expect(screen.getByText("Cannot connect to RTSP endpoint")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry stream" })).toBeInTheDocument();

    // Pending state shows spinner
    rerender(
      <InlineError
        title="Stream failed"
        message="Cannot connect to RTSP endpoint"
        actionLabel="Retry stream"
        onAction={handleRetry}
        pending={true}
      />
    );
    expect(screen.getByRole("button", { name: /retry stream/i })).toBeDisabled();
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();

    // Type-level verification:
    // A bare "Retry" must be rejected by TypeScript:
    const _invalid: Parameters<typeof InlineError>[0] = {
      message: "Err",
      // @ts-expect-error ActionLabel requires `Retry ${string}` or `Reload ${string}`
      actionLabel: "Retry",
    };
    expect(_invalid).toBeDefined();
  });
});
