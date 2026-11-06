import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createAppRoutes } from "./router";
import { useUiStore } from "@/stores/ui";
import { setMediaQueryMatches } from "@/test/setup";

function renderRoutesApp(
  initialEntries = ["/live"],
  role: "viewer" | "operator" | "owner" = "viewer",
  mockAlerts: any[] = []
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
            user: { id: 1, username: "testuser", role, permissions: ["*"] },
            site_timezone: "UTC",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    if (urlStr.includes("/api/v1/cameras")) {
      return Promise.resolve(
        new Response(
          JSON.stringify([
            { id: 1, serial: "CAM1", name: "Front Door", state: "online" },
            { id: 2, serial: "CAM2", name: "Back Yard", state: "online" },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    if (urlStr.includes("/api/v1/recording/status")) {
      return Promise.resolve(
        new Response(
          JSON.stringify([
            { camera_serial: "CAM1", mode: "continuous" },
            { camera_serial: "CAM2", mode: "continuous" },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        )
      );
    }
    if (urlStr.includes("/api/v1/health/alerts")) {
      return Promise.resolve(
        new Response(JSON.stringify(mockAlerts), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/events")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items: [
              {
                id: 42,
                camera_serial: "CAM1",
                event_type: "motion",
                start_time: "2026-11-05T10:00:00Z",
                end_time: "2026-11-05T10:01:00Z",
                is_locked: false,
              },
            ],
            total: 1,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        )
      );
    }
    if (urlStr.includes("/api/v1/playback/days")) {
      return Promise.resolve(
        new Response(JSON.stringify({ days: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/playback/timeline")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({ segments: [], outages: [], events: [] }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    if (urlStr.includes("/api/v1/gallery")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({ items: [], total: 0 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    if (urlStr.includes("/api/v1/devices")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({ devices: [] }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
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

describe("Feature Route Adapters", () => {
  beforeEach(() => {
    localStorage.clear();
    useUiStore.setState({
      sidebarOpen: true,
      theme: "system",
      viewMode: "simple",
      dismissedAlertIds: new Set<string>(),
      readEventIds: new Set<number>(),
    });
    setMediaQueryMatches(false); // desktop
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders Playback page inside shell with deep link parameters and top-bar h1 Playback", async () => {
    renderRoutesApp(["/playback?camera=CAM1&t=2026-11-05T10:00:00Z"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Playback" })).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: "Playback" })).toBeInTheDocument();

    await waitFor(() => {
      const select = screen.getByDisplayValue("Front Door (CAM1)") as HTMLSelectElement;
      expect(select).toBeInTheDocument();
    });
  });

  it("navigates to /gallery?tab=clips when open gallery is triggered from playback", async () => {
    const user = userEvent.setup();
    const { router } = renderRoutesApp(["/playback?camera=CAM1&t=2026-11-05T10:00:00Z"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Playback" })).toBeInTheDocument();
    });

    const openGalleryBtn = screen.getByRole("button", { name: /view media gallery/i });
    await user.click(openGalleryBtn);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/gallery");
      expect(router.state.location.search).toBe("?tab=clips");
    });
  });

  it("renders Events page with h1 Events and handles jump-to-playback", async () => {
    const user = userEvent.setup();
    const { router } = renderRoutesApp(["/events"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Events" })).toBeInTheDocument();
    });

    const playbackBtn = await screen.findByTitle("Jump to footage in 24h timeline");
    await user.click(playbackBtn);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/playback");
      expect(router.state.location.search).toContain("camera=CAM1");
      expect(router.state.location.search).toContain("t=2026-11-05T10%3A00%3A00Z");
    });
  });

  it("renders Gallery page with h1 Gallery", async () => {
    renderRoutesApp(["/gallery"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Gallery" })).toBeInTheDocument();
    });
  });

  it("renders Dashboard page with h1 Dashboard", async () => {
    renderRoutesApp(["/dashboard"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    });
  });

  it("shows 403 Forbidden when a viewer accesses /cameras", async () => {
    renderRoutesApp(["/cameras"], "viewer");

    await waitFor(() => {
      expect(screen.getByText("Access restricted")).toBeInTheDocument();
      expect(
        screen.getByText(/You don't have access to this page/i)
      ).toBeInTheDocument();
    });
  });

  it("renders Cameras page with h1 Cameras when user is operator", async () => {
    renderRoutesApp(["/cameras"], "operator");

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Cameras" })).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { level: 2, name: "Camera Settings" })).toBeInTheDocument();
  });

  it("hides Mobile devices in sidebar for viewer, shows for owner and renders /devices", async () => {
    const { unmount } = renderRoutesApp(["/live"], "viewer");

    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Mobile devices" })).toBeNull();
    });
    unmount();

    renderRoutesApp(["/devices"], "owner");

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Mobile devices" })).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Mobile devices" })).toBeInTheDocument();
    expect(screen.getByText(/Paired Mobile Devices/i)).toBeInTheDocument();
  });

  it("renders active alerts in AlertsBanner under top bar and dismisses them", async () => {
    const user = userEvent.setup();
    const testAlerts = [
      {
        id: "alert-disk",
        severity: "critical",
        title: "Disk Space Low",
        message: "Free space below 10%",
        timestamp: "2026-11-05T12:00:00Z",
        source: "storage",
      },
    ];

    renderRoutesApp(["/live"], "viewer", testAlerts);

    await waitFor(() => {
      expect(screen.getByText(/Disk Space Low:/i)).toBeInTheDocument();
      expect(screen.getByText(/Free space below 10%/i)).toBeInTheDocument();
    });

    const dismissBtn = screen.getByRole("button", { name: /✕/i });
    await user.click(dismissBtn);

    await waitFor(() => {
      expect(screen.queryByText(/Disk Space Low:/i)).toBeNull();
    });
    expect(useUiStore.getState().dismissedAlertIds.has("alert-disk")).toBe(true);
  });

  it("renders / as Live page with top-bar h1 Live and Live nav link has aria-current page", async () => {
    renderRoutesApp(["/"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    });

    const liveLink = screen.getByRole("link", { name: "Live" });
    expect(liveLink).toBeInTheDocument();
    expect(liveLink).toHaveAttribute("aria-current", "page");
  });

  it("redirects unknown routes to / with replace", async () => {
    const { router } = renderRoutesApp(["/nope"]);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
      expect(screen.getByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    });
  });
});
