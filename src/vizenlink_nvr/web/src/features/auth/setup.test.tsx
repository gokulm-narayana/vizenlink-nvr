import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SetupPage } from "./SetupPage";
import { AUTH_COPY } from "./copy";

function renderSetupPage(initialEntries = ["/setup"]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false, gcTime: 0 },
    },
  });

  const routes = [
    {
      path: "/setup",
      element: <SetupPage />,
    },
    {
      path: "/",
      element: <div data-testid="home-page">Home Page</div>,
    },
  ];

  const router = createMemoryRouter(routes, {
    initialEntries,
  });

  const utils = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );

  return { ...utils, router, queryClient };
}

describe("SetupPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("submits exactly the five required keys and allow_system_disk is false by default", async () => {
    let capturedBody: any = null;
    vi.spyOn(globalThis, "fetch").mockImplementation((url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/v1/auth/setup")) {
        capturedBody = JSON.parse(init?.body as string);
        return Promise.resolve(
          new Response(JSON.stringify({ user: { id: 1, username: "admin" } }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      return Promise.resolve(new Response(JSON.stringify({})));
    });

    const user = userEvent.setup();
    const { router } = renderSetupPage();

    await user.type(screen.getByLabelText("Owner username"), "myadmin");
    await user.type(screen.getByLabelText("Password", { selector: "#password" }), "secret1234");
    await user.type(screen.getByLabelText("Confirm password"), "secret1234");

    const submitBtn = screen.getByRole("button", { name: AUTH_COPY.CREATE_OWNER_ACCOUNT });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });

    expect(capturedBody).not.toBeNull();
    expect(Object.keys(capturedBody).sort()).toEqual([
      "allow_system_disk",
      "owner_password",
      "owner_username",
      "storage_path",
      "timezone",
    ]);
    expect(capturedBody).toEqual({
      owner_username: "myadmin",
      owner_password: "secret1234",
      timezone: expect.any(String),
      storage_path: "/var/lib/vizenlink-nvr/recordings",
      allow_system_disk: false,
    });
  });

  it("sends allow_system_disk as true when checkbox is checked", async () => {
    let capturedBody: any = null;
    vi.spyOn(globalThis, "fetch").mockImplementation((url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/v1/auth/setup")) {
        capturedBody = JSON.parse(init?.body as string);
        return Promise.resolve(
          new Response(JSON.stringify({ user: { id: 1, username: "admin" } }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      return Promise.resolve(new Response(JSON.stringify({})));
    });

    const user = userEvent.setup();
    renderSetupPage();

    await user.type(screen.getByLabelText("Owner username"), "myadmin");
    await user.type(screen.getByLabelText("Password", { selector: "#password" }), "secret1234");
    await user.type(screen.getByLabelText("Confirm password"), "secret1234");

    const checkbox = screen.getByRole("checkbox", {
      name: /Allow recordings on the system disk/i,
    });
    await user.click(checkbox);

    const submitBtn = screen.getByRole("button", { name: AUTH_COPY.CREATE_OWNER_ACCOUNT });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });
    expect(capturedBody.allow_system_disk).toBe(true);
  });

  it("validates password length and shows error if shorter than 8", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    renderSetupPage();

    await user.type(screen.getByLabelText("Owner username"), "myadmin");
    await user.type(screen.getByLabelText("Password", { selector: "#password" }), "short");
    await user.type(screen.getByLabelText("Confirm password"), "short");

    const submitBtn = screen.getByRole("button", { name: AUTH_COPY.CREATE_OWNER_ACCOUNT });
    await user.click(submitBtn);

    expect(await screen.findByText(AUTH_COPY.PASSWORD_TOO_SHORT)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("validates password matching and shows error when mismatched", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    renderSetupPage();

    await user.type(screen.getByLabelText("Owner username"), "myadmin");
    await user.type(screen.getByLabelText("Password", { selector: "#password" }), "password123");
    await user.type(screen.getByLabelText("Confirm password"), "mismatched123");

    const submitBtn = screen.getByRole("button", { name: AUTH_COPY.CREATE_OWNER_ACCOUNT });
    await user.click(submitBtn);

    expect(await screen.findByText(AUTH_COPY.PASSWORD_MISMATCH)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("on 400 failure shows setup failure alert, keeps entered values, and provides retry button", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ detail: "Directory /var/lib/recordings does not exist" }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          }
        )
      )
    );

    const user = userEvent.setup();
    renderSetupPage();

    await user.type(screen.getByLabelText("Owner username"), "myadmin");
    await user.type(screen.getByLabelText("Password", { selector: "#password" }), "secret1234");
    await user.type(screen.getByLabelText("Confirm password"), "secret1234");

    const submitBtn = screen.getByRole("button", { name: AUTH_COPY.CREATE_OWNER_ACCOUNT });
    await user.click(submitBtn);

    expect(await screen.findByText(AUTH_COPY.SETUP_FAILURE)).toBeInTheDocument();
    expect(
      screen.getByText("Directory /var/lib/recordings does not exist")
    ).toBeInTheDocument();

    // Check that entered values remain
    expect(screen.getByLabelText("Owner username")).toHaveValue("myadmin");
    expect(screen.getByLabelText("Password", { selector: "#password" })).toHaveValue("secret1234");
    expect(screen.getByLabelText("Confirm password")).toHaveValue("secret1234");

    // Check retry button in alert and primary button label
    expect(
      screen.getByRole("button", { name: AUTH_COPY.RETRY_SETUP })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: AUTH_COPY.CREATE_OWNER_ACCOUNT })
    ).toBeInTheDocument();
  });
});
