import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createAppRoutes } from "@/app/router";
import { apiFetch, ApiError, setUnauthorizedHandler } from "@/lib/api";
import type { AuthStatus } from "@/lib/queries";

function renderWithRouter(initialEntries: string[], statusResponse?: Partial<AuthStatus> | null, statusFail?: boolean) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
    },
  });

  if (statusFail) {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.reject(new Error("Network connection error"))
    );
  } else if (statusResponse !== undefined) {
    vi.spyOn(globalThis, "fetch").mockImplementation((url: string | URL | Request) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/v1/auth/status")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              initialized: true,
              authenticated: false,
              user: null,
              site_timezone: "UTC",
              ...statusResponse,
            }),
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
  }

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

describe("apiFetch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setUnauthorizedHandler(null);
  });

  it("sends application/json and serializes plain object bodies", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const res = await apiFetch<{ ok: boolean }>("/api/v1/test", {
      method: "POST",
      body: { hello: "world" } as any,
    });

    expect(res).toEqual({ ok: true });
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/test",
      expect.objectContaining({
        body: JSON.stringify({ hello: "world" }),
        credentials: "same-origin",
      })
    );
  });

  it("returns undefined for 204 No Content", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(new Response(null, { status: 204 }))
    );

    const res = await apiFetch("/api/v1/test", { method: "DELETE" });
    expect(res).toBeUndefined();
  });

  it("throws ApiError with status and detail on non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Camera not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    await expect(apiFetch("/api/v1/cameras/abc")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      detail: "Camera not found",
    });
  });

  it("triggers unauthorizedHandler on 401 for non-auth endpoints", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    await expect(apiFetch("/api/v1/cameras")).rejects.toThrow(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not trigger unauthorizedHandler on 401 for auth endpoints", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Bad credentials" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    await expect(apiFetch("/api/v1/auth/login", { method: "POST" })).rejects.toThrow(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("AuthGate routing", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("Row 1: renders full-page skeleton while status is pending", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {}));

    renderWithRouter(["/"]);

    expect(screen.getByTestId("auth-loading-skeleton")).toBeInTheDocument();
    expect(screen.queryByText(/Sign In/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Live Multiview/i)).not.toBeInTheDocument();
  });

  it("Row 2: renders NVR unreachable error with Retry connection on failure", async () => {
    const { router } = renderWithRouter(["/"], null, true);

    await waitFor(() => {
      expect(screen.getByTestId("auth-unreachable")).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Can't reach the NVR. Check that the NVR service is running/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry connection" })).toBeInTheDocument();
    // No redirect on error
    expect(router.state.location.pathname).toBe("/");
  });

  it("Row 3: uninitialized routes /playback?camera=X and /login to /setup", async () => {
    const { router: r1 } = renderWithRouter(["/playback?camera=cam1"], {
      initialized: false,
      authenticated: false,
    });
    await waitFor(() => {
      expect(r1.state.location.pathname).toBe("/setup");
    });

    const { router: r2 } = renderWithRouter(["/login"], {
      initialized: false,
      authenticated: false,
    });
    await waitFor(() => {
      expect(r2.state.location.pathname).toBe("/setup");
    });
  });

  it("Rows 4 to 6: signed out stays at /login, /setup redirects to /login, /playback redirects with next", async () => {
    const { router: r1 } = renderWithRouter(["/login"], {
      initialized: true,
      authenticated: false,
    });
    await waitFor(() => {
      expect(r1.state.location.pathname).toBe("/login");
    });

    const { router: r2 } = renderWithRouter(["/setup"], {
      initialized: true,
      authenticated: false,
    });
    await waitFor(() => {
      expect(r2.state.location.pathname).toBe("/login");
    });

    const { router: r3 } = renderWithRouter(["/playback?camera=X&t=T"], {
      initialized: true,
      authenticated: false,
    });
    await waitFor(() => {
      expect(r3.state.location.pathname).toBe("/login");
      expect(r3.state.location.search).toBe("?next=%2Fplayback%3Fcamera%3DX%26t%3DT");
    });
  });

  it("Row 10: signed in at /login or /setup redirects to /", async () => {
    const user = { id: 1, username: "admin", role: "owner", permissions: ["*"] };
    const { router: r1 } = renderWithRouter(["/login"], {
      initialized: true,
      authenticated: true,
      user,
    });
    await waitFor(() => {
      expect(r1.state.location.pathname).toBe("/");
    });

    const { router: r2 } = renderWithRouter(["/setup"], {
      initialized: true,
      authenticated: true,
      user,
    });
    await waitFor(() => {
      expect(r2.state.location.pathname).toBe("/");
    });
  });

  it("Signed in at / renders the shell Live page", async () => {
    const user = { id: 1, username: "admin", role: "owner", permissions: ["*"] };
    renderWithRouter(["/"], {
      initialized: true,
      authenticated: true,
      user,
    });

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Account menu for admin" })
      ).toBeInTheDocument();
    });
  });
});
