import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createAppRoutes } from "@/app/router";
import { RequireRole } from "@/app/routes";
import { useUiStore } from "@/stores/ui";
import { setMediaQueryMatches } from "@/test/setup";

function renderShellApp(initialEntries = ["/live"], role: "viewer" | "operator" | "owner" = "viewer") {
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
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (urlStr.includes("/api/v1/events")) {
      return Promise.resolve(
        new Response(JSON.stringify({ items: [] }), {
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

describe("AppShell tracer & navigation", () => {
  beforeEach(() => {
    localStorage.clear();
    useUiStore.setState({
      sidebarOpen: true,
      theme: "system",
      viewMode: "simple",
    });
    setMediaQueryMatches(false); // desktop
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the shell on /live with route h1 Live View and active page link", async () => {
    renderShellApp(["/live"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live View" })).toBeInTheDocument();
    });

    const activeLink = screen.getByRole("link", { name: "Live View" });
    expect(activeLink).toHaveAttribute("aria-current", "page");
  });

  it("sidebar is expanded by default with no saved choice; clicking toggle collapses and persists in nvr_sidebar", async () => {
    const user = userEvent.setup();
    renderShellApp(["/live"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live View" })).toBeInTheDocument();
    });

    const trigger = screen.getByRole("button", { name: /toggle sidebar/i });
    expect(screen.getByText("Monitor")).toBeVisible();
    await user.click(trigger);

    expect(localStorage.getItem("nvr_sidebar")).toBe("collapsed");
    expect(useUiStore.getState().sidebarOpen).toBe(false);
    expect(screen.queryByText("Monitor")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Live View" })).toHaveAttribute("aria-current", "page");
    await user.click(trigger);
    expect(screen.getByText("Monitor")).toBeVisible();
  });

  it("pressing [ toggles sidebar, but not when typing inside an input", async () => {
    renderShellApp(["/live"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live View" })).toBeInTheDocument();
    });

    expect(useUiStore.getState().sidebarOpen).toBe(true);

    // Press [ on window
    fireEvent.keyDown(window, { key: "[" });
    expect(useUiStore.getState().sidebarOpen).toBe(false);

    fireEvent.keyDown(window, { key: "[" });
    expect(useUiStore.getState().sidebarOpen).toBe(true);

    // Create an input in document and dispatch [ from it
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(input, { key: "[" });
    // Should NOT toggle because target is an input
    expect(useUiStore.getState().sidebarOpen).toBe(true);
    document.body.removeChild(input);
  });

  it("renders shell on / and /dashboard with Primary navigation", async () => {
    const { unmount } = renderShellApp(["/"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    });

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    unmount();

    renderShellApp(["/dashboard"]);
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    });
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("RequireRole shows 403 state when role is insufficient", async () => {
    const queryClient = new QueryClient();
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            initialized: true,
            authenticated: true,
            user: { id: 1, username: "viewer_user", role: "viewer", permissions: [] },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    const router = createMemoryRouter(
      [
        {
          path: "/restricted",
          element: (
            <RequireRole min="operator">
              <div>Secret operator content</div>
            </RequireRole>
          ),
        },
      ],
      { initialEntries: ["/restricted"] }
    );

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(
        screen.getByText(/You don't have access to this page/i)
      ).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: "Go to Dashboard" })).toBeInTheDocument();
    expect(screen.queryByText("Secret operator content")).not.toBeInTheDocument();
  });
});
