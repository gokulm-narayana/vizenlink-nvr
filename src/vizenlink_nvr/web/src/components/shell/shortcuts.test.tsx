import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createAppRoutes } from "@/app/router";
import { useUiStore } from "@/stores/ui";
import { setMediaQueryMatches } from "@/test/setup";
import { RefetchBar } from "./RefetchBar";

function renderShellApp(initialEntries = ["/"]) {
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

describe("Shortcuts, Skip Link & RefetchBar", () => {
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

  it("pressing g then p within 1.5s navigates to /playback", async () => {
    const { router } = renderShellApp(["/"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live View" })).toBeInTheDocument();
    });

    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "p" });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/playback");
      expect(screen.getByRole("heading", { level: 1, name: "Playback" })).toBeInTheDocument();
    });
  });

  it("pressing g then e navigates to /events, and g then d to /dashboard", async () => {
    const { router } = renderShellApp(["/"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live View" })).toBeInTheDocument();
    });

    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "e" });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/events");
      expect(screen.getByRole("heading", { level: 1, name: "Events" })).toBeInTheDocument();
    });

    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "d" });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/dashboard");
      expect(screen.getByRole("heading", { level: 1, name: "System Health" })).toBeInTheDocument();
    });
  });

  it("shortcuts are ignored when typing in an input or holding modifier keys", async () => {
    const { router } = renderShellApp(["/"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live View" })).toBeInTheDocument();
    });

    // Modifiers held
    fireEvent.keyDown(window, { key: "g", ctrlKey: true });
    fireEvent.keyDown(window, { key: "p" });
    expect(router.state.location.pathname).toBe("/");

    // Inside input
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(input, { key: "g" });
    fireEvent.keyDown(input, { key: "p" });
    expect(router.state.location.pathname).toBe("/");

    document.body.removeChild(input);
  });

  it("skip to main content is the first link and focuses #main", async () => {
    const user = userEvent.setup();
    renderShellApp(["/"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live View" })).toBeInTheDocument();
    });

    const skipLink = screen.getByRole("link", { name: "Skip to main content" });
    expect(skipLink).toBeInTheDocument();
    expect(skipLink).toHaveAttribute("href", "#main");

    // First tab focuses the skip link
    await user.tab();
    expect(skipLink).toHaveFocus();
  });

  it("RefetchBar shows a 2px muted line when refetching after initial boot", async () => {
    const queryClient = new QueryClient();

    // Custom query that starts fetching
    let resolveQuery: (val: any) => void = () => {};
    const queryPromise = new Promise((res) => {
      resolveQuery = res;
    });

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <RefetchBar bootDelayMs={10} />
      </QueryClientProvider>
    );

    // Initial state: not booted / not fetching -> null
    expect(screen.queryByRole("progressbar")).toBeNull();

    // Fast-forward boot delay
    await waitFor(() => {
      // after 20ms, boot delay has passed
    }, { timeout: 50 });

    // Trigger a background refetch
    void queryClient.prefetchQuery({
      queryKey: ["testBackground"],
      queryFn: () => queryPromise,
    });

    rerender(
      <QueryClientProvider client={queryClient}>
        <RefetchBar bootDelayMs={10} />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const bar = screen.getByRole("progressbar");
      expect(bar).toBeInTheDocument();
      expect(bar).toHaveClass("h-0.5");
      expect(bar).toHaveClass("bg-muted-foreground");
    });

    // Resolve the query to stop fetching
    resolveQuery({ ok: true });
    await waitFor(() => {
      expect(screen.queryByRole("progressbar")).toBeNull();
    });
  });
});
