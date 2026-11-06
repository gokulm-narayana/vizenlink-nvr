import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LoginPage } from "./LoginPage";
import { PasswordField } from "@/components/PasswordField";
import { useSignOut } from "./api";
import { AUTH_COPY } from "./copy";

function renderLoginPage(initialEntries = ["/login"], initialLocationState?: any) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false, gcTime: 0 },
    },
  });

  const routes = [
    {
      path: "/login",
      element: <LoginPage />,
    },
    {
      path: "/playback",
      element: <div data-testid="playback-page">Playback Page</div>,
    },
    {
      path: "/",
      element: <div data-testid="home-page">Home Page</div>,
    },
  ];

  const router = createMemoryRouter(routes, {
    initialEntries: [
      typeof initialEntries[0] === "string"
        ? { pathname: initialEntries[0].split("?")[0], search: initialEntries[0].includes("?") ? `?${initialEntries[0].split("?")[1]}` : "", state: initialLocationState }
        : initialEntries[0],
    ],
  });

  const utils = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );

  return { ...utils, router, queryClient };
}

describe("PasswordField", () => {
  it("toggles password visibility, flips type and updates aria attributes", async () => {
    const user = userEvent.setup();
    render(<PasswordField id="test-pass" placeholder="Enter password" />);

    const input = screen.getByPlaceholderText("Enter password") as HTMLInputElement;
    const toggle = screen.getByRole("button", { name: "Show password" });

    expect(input.type).toBe("password");
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    await user.click(toggle);

    expect(input.type).toBe("text");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();

    await user.click(toggle);

    expect(input.type).toBe("password");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Show password" })).toBeInTheDocument();
  });
});

describe("LoginPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("submitting empty fields shows validation errors, focuses username, and sends nothing", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();

    renderLoginPage(["/login"]);

    const submitBtn = screen.getByRole("button", { name: AUTH_COPY.SIGN_IN });
    await user.click(submitBtn);

    expect(await screen.findByText("Username is required")).toBeInTheDocument();
    expect(await screen.findByText("Password is required")).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toHaveFocus();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("handles 401 invalid credentials error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Incorrect password" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const user = userEvent.setup();
    renderLoginPage(["/login"]);

    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "wrongpass");
    await user.click(screen.getByRole("button", { name: AUTH_COPY.SIGN_IN }));

    expect(await screen.findByText(AUTH_COPY.LOGIN_ERROR)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("handles 429 lockout error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Too many attempts" }), {
          status: 429,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const user = userEvent.setup();
    renderLoginPage(["/login"]);

    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "wrongpass");
    await user.click(screen.getByRole("button", { name: AUTH_COPY.SIGN_IN }));

    expect(await screen.findByText(AUTH_COPY.LOCKOUT_ERROR)).toBeInTheDocument();
  });

  it("successful login navigates to valid next target (replace)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ user: { id: 1, username: "admin" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const user = userEvent.setup();
    const { router } = renderLoginPage(["/login?next=%2Fplayback"]);

    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "correctpassword");
    await user.click(screen.getByRole("button", { name: AUTH_COPY.SIGN_IN }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/playback");
    });
  });

  it("successful login with invalid next target navigates to /", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ user: { id: 1, username: "admin" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const user = userEvent.setup();
    const { router } = renderLoginPage(["/login?next=%2F%2Fevil.example"]);

    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "correctpassword");
    await user.click(screen.getByRole("button", { name: AUTH_COPY.SIGN_IN }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
  });

  it("displays sessionEnded informational status alert when passed in router state", () => {
    renderLoginPage(["/login"], { sessionEnded: true });

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(AUTH_COPY.SESSION_ENDED)).toBeInTheDocument();
  });

  it("displays signOutFailed alert and retries sign-out request", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    );

    const user = userEvent.setup();
    renderLoginPage(["/login"], { signOutFailed: true });

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(AUTH_COPY.SIGN_OUT_FAILURE)).toBeInTheDocument();

    const retryBtn = screen.getByRole("button", { name: AUTH_COPY.RETRY_SIGN_OUT });
    await user.click(retryBtn);

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/auth/logout",
      expect.objectContaining({ method: "POST" })
    );

    await waitFor(() => {
      expect(screen.queryByText(AUTH_COPY.SIGN_OUT_FAILURE)).not.toBeInTheDocument();
    });
  });
});

describe("useSignOut", () => {
  it("clears queryClient and navigates to /login with no next on logout", async () => {
    let testSignOut: () => Promise<void>;
    const queryClient = new QueryClient();
    const clearSpy = vi.spyOn(queryClient, "clear");

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );

    function TestComponent() {
      testSignOut = useSignOut();
      return <div>Test</div>;
    }

    const router = createMemoryRouter(
      [
        { path: "/playback", element: <TestComponent /> },
        { path: "/login", element: <div>Login</div> },
      ],
      { initialEntries: ["/playback?camera=1"] }
    );

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    );

    await testSignOut!();

    expect(clearSpy).toHaveBeenCalled();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("");
  });
});
