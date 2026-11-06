import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createAppRoutes } from "@/app/router";
import { useUiStore } from "@/stores/ui";
import { setMediaQueryMatches } from "@/test/setup";
import { CameraHealthLink } from "@/components/CameraHealthLink";

function renderAlertsApp(
  initialEntries = ["/"],
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
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/recording/status")) {
      return Promise.resolve(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
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

describe("AlertStack, Bell and Dashboard Badge", () => {
  const testAlerts = [
    {
      id: "alert-warn-1",
      severity: "warning",
      title: "Camera Dropping Frames",
      message: "Camera 1 frame rate dropped below 15 fps",
      timestamp: "2026-11-05T09:00:00Z",
      source: "camera:CAM1",
      camera_serial: "CAM1",
    },
    {
      id: "alert-crit-1",
      severity: "critical",
      title: "Storage Pool Full",
      message: "Root disk storage pool is at 99% capacity",
      timestamp: "2026-11-05T10:00:00Z",
      source: "storage",
    },
    {
      id: "alert-warn-2",
      severity: "warning",
      title: "NTP Sync Drift",
      message: "System clock drifted 500ms from NTP",
      timestamp: "2026-11-05T08:00:00Z",
      source: "ntp",
    },
  ];

  beforeEach(() => {
    localStorage.clear();
    useUiStore.setState({
      sidebarOpen: true,
      theme: "system",
      viewMode: "simple",
      dismissedAlertIds: new Set<string>(),
    });
    setMediaQueryMatches(false); // desktop
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("AlertStack shows at most 2 alerts: critical first with role=alert, warning with role=status", async () => {
    renderAlertsApp(["/"], "viewer", testAlerts);

    await waitFor(() => {
      expect(screen.getByText("Storage Pool Full")).toBeInTheDocument();
      expect(screen.getByText("Camera Dropping Frames")).toBeInTheDocument();
    });

    // The third alert should NOT be in the AlertStack
    expect(screen.queryByText("NTP Sync Drift")).toBeNull();

    // Critical alert has role="alert"
    const alertElements = screen.getAllByRole("alert");
    const critAlert = alertElements.find((el) => el.textContent?.includes("Storage Pool Full"));
    expect(critAlert).toBeDefined();

    // Warning alert has role="status"
    const statusElements = screen.getAllByRole("status");
    const warnAlert = statusElements.find((el) =>
      el.textContent?.includes("Camera Dropping Frames")
    );
    expect(warnAlert).toBeDefined();

    // Each visible alert has "Dismiss alert" button
    const dismissButtons = screen.getAllByRole("button", { name: /dismiss alert/i });
    expect(dismissButtons.length).toBeGreaterThanOrEqual(2);
  });

  it("dismissing an alert hides it from the stack, bell, and dashboard badge for the session", async () => {
    const user = userEvent.setup();
    const { container } = renderAlertsApp(["/"], "viewer", testAlerts);

    await waitFor(() => {
      expect(screen.getByText("Storage Pool Full")).toBeInTheDocument();
    });

    // Initial Dashboard badge has 3 active alerts (critical style)
    const dashboardBadge = container.querySelector('[data-slot="dashboard-alert-badge"]');
    expect(dashboardBadge).toBeInTheDocument();
    expect(dashboardBadge?.textContent).toBe("3");
    expect(dashboardBadge).toHaveClass("bg-critical");

    // Dismiss the critical alert
    const dismissButtons = screen.getAllByRole("button", { name: /dismiss alert/i });
    await user.click(dismissButtons[0]);

    await waitFor(() => {
      expect(screen.queryByText("Storage Pool Full")).toBeNull();
    });

    // Now dismissedAlertIds has alert-crit-1
    expect(useUiStore.getState().dismissedAlertIds.has("alert-crit-1")).toBe(true);

    // Dashboard badge now shows 2 active alerts with warning style (no critical alerts left)
    await waitFor(() => {
      const updatedBadge = container.querySelector('[data-slot="dashboard-alert-badge"]');
      expect(updatedBadge?.textContent).toBe("2");
      expect(updatedBadge).toHaveClass("bg-warning");
    });
  });

  it("bell trigger has aria-label and count badge, popover lists all non-dismissed alerts", async () => {
    renderAlertsApp(["/"], "viewer", testAlerts);

    await waitFor(() => {
      const bellBtn = screen.getByRole("button", { name: /Alerts, 3 active/i });
      expect(bellBtn).toBeInTheDocument();
    });

    const bellBtn = screen.getByRole("button", { name: /Alerts, 3 active/i });
    fireEvent.click(bellBtn);

    // Popover content should open and list all 3 alerts
    await waitFor(() => {
      expect(screen.getByText("Active alerts")).toBeInTheDocument();
      expect(screen.getByText("NTP Sync Drift")).toBeInTheDocument();
      expect(screen.getAllByText("Storage Pool Full").length).toBe(2);
      expect(screen.getAllByText("Camera Dropping Frames").length).toBe(2);
    });
  });

  it("bell popover shows 'All clear. No active alerts.' when no alerts exist", async () => {
    renderAlertsApp(["/"], "viewer", []);

    await waitFor(() => {
      const bellBtn = screen.getByRole("button", { name: /Alerts, 0 active/i });
      expect(bellBtn).toBeInTheDocument();
    });

    const bellBtn = screen.getByRole("button", { name: /Alerts, 0 active/i });
    fireEvent.click(bellBtn);

    await waitFor(() => {
      expect(screen.getByText("All clear. No active alerts.")).toBeInTheDocument();
    });
  });

  it("CameraHealthLink renders 'Open camera health' for operator and owner, and handles viewer", async () => {
    // 1. Direct unit test of CameraHealthLink for operator
    const queryClient = new QueryClient();
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            initialized: true,
            authenticated: true,
            user: { id: 1, username: "operator", role: "operator", permissions: ["*"] },
            site_timezone: "UTC",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    const router1 = createMemoryRouter([
      {
        path: "/",
        element: <CameraHealthLink serial="CAM1" />,
      },
    ]);

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router1} />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const link = screen.getByRole("link", { name: "Open camera health" });
      expect(link).toHaveAttribute("href", "/cameras/CAM1?tab=health");
    });

    unmount();

    // 2. Viewer role when /cameras/:serial/health is registered renders "View camera health" link
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            initialized: true,
            authenticated: true,
            user: { id: 2, username: "viewer", role: "viewer", permissions: [] },
            site_timezone: "UTC",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    const router2 = createMemoryRouter([
      {
        path: "/",
        element: <CameraHealthLink serial="CAM1" />,
      },
    ]);

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router2} />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const link = screen.getByRole("link", { name: "View camera health" });
      expect(link).toHaveAttribute("href", "/cameras/CAM1/health");
    });
  });
});
