import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, within, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UserMenu } from "./UserMenu";
import { ViewModeToggle } from "./ViewModeToggle";
import { ThemeSync } from "./ThemeSync";
import { useUiStore } from "@/stores/ui";

function renderUserMenu(role = "owner", username = "alice") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    if (urlStr.includes("/api/v1/auth/status")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            initialized: true,
            authenticated: true,
            user: { id: 1, username, role, permissions: ["*"] },
            site_timezone: "UTC",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    return Promise.resolve(new Response(JSON.stringify({})));
  });

  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <div>
            <ThemeSync />
            <ViewModeToggle />
            <UserMenu />
          </div>
        ),
      },
      {
        path: "/login",
        element: <div>Login Page</div>,
      },
    ],
    { initialEntries: ["/"] }
  );

  const utils = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );

  return { ...utils, router, queryClient };
}

describe("UserMenu and ThemeSync", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
    useUiStore.setState({
      theme: "system",
      viewMode: "simple",
      sidebarOpen: true,
    });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders trigger avatar with initial and opens menu with username and role badge", async () => {
    const user = userEvent.setup();
    renderUserMenu("owner", "alice");

    const trigger = await screen.findByRole("button", { name: "Account menu for alice" });
    expect(trigger).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();

    // Phase 10: the header trigger shows name and role like the old VMS.
    expect(within(trigger).getByText("alice")).toBeInTheDocument();
    expect(within(trigger).getByText("owner")).toBeInTheDocument();

    await user.click(trigger);

    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("alice")).toBeInTheDocument();
    expect(within(menu).getByText("owner")).toBeInTheDocument();
  });

  it("choosing Dark adds dark class and writes nvr_theme=dark", async () => {
    const user = userEvent.setup();
    renderUserMenu();

    const trigger = await screen.findByRole("button", { name: /account menu for/i });
    await user.click(trigger);

    const darkOption = screen.getByRole("menuitemradio", { name: "Dark" });
    await user.click(darkOption);

    expect(localStorage.getItem("nvr_theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("choosing Light removes dark class and writes nvr_theme=light", async () => {
    document.documentElement.classList.add("dark");
    const user = userEvent.setup();
    renderUserMenu();

    const trigger = await screen.findByRole("button", { name: /account menu for/i });
    await user.click(trigger);

    const lightOption = screen.getByRole("menuitemradio", { name: "Light" });
    await user.click(lightOption);

    expect(localStorage.getItem("nvr_theme")).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("sign out calls logout endpoint and routes to /login even if logout returns 500", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/v1/auth/logout")) {
        return Promise.resolve(new Response(null, { status: 500 }));
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            initialized: true,
            authenticated: true,
            user: { id: 1, username: "alice", role: "owner" },
          })
        )
      );
    });

    const user = userEvent.setup();
    const { router } = renderUserMenu();

    const trigger = await screen.findByRole("button", { name: /account menu for/i });
    await user.click(trigger);

    const signOutBtn = screen.getByRole("menuitem", { name: "Sign out" });
    await user.click(signOutBtn);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/auth/logout",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("ViewModeToggle toggles between simple and advanced and sets nvr_view_mode", async () => {
    const user = userEvent.setup();
    renderUserMenu();

    const advancedBtn = screen.getByRole("radio", { name: "Advanced view" });
    await user.click(advancedBtn);

    expect(localStorage.getItem("nvr_view_mode")).toBe("advanced");
    expect(useUiStore.getState().viewMode).toBe("advanced");
  });
});