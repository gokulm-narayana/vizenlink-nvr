import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RecordingPage } from "./RecordingPage";
import { SettingsPage } from "./SettingsPage";

function mount(role = "owner", recording = false) {
  const policy = { camera_serial: "CAM1", mode: "continuous", audio_enabled: false, retention_days: 14, retention_max_gb: null, schedule_json: JSON.stringify({ days: Array.from({ length: 7 }, () => Array(24).fill(true)) }) };
  let body: any;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    let data: unknown = [];
    if (path.endsWith("auth/status")) data = { authenticated: true, initialized: true, user: { id: 1, username: "Owner", role }, site_timezone: "UTC" };
    else if (path.endsWith("cameras")) data = [{ serial: "CAM1", name: "Entrance" }];
    else if (path.endsWith("storage/status")) data = { storage_path: "/recordings", health_state: "ok", reserve_bytes: 0 };
    else if (path.endsWith("recording/status")) data = [policy];
    else if (init?.method === "PATCH") { body = JSON.parse(String(init.body)); Object.assign(policy, body); data = policy; }
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  const router = createMemoryRouter([{ path: "/", element: recording ? <RecordingPage /> : <SettingsPage /> }, { path: "/settings", element: <SettingsPage /> }]);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RouterProvider router={router} /></QueryClientProvider>);
  return { getBody: () => body };
}
afterEach(() => vi.restoreAllMocks());
describe("Settings workflows", () => {
  it("keeps administration links out of viewer settings", async () => {
    mount("viewer");
    await screen.findByRole("link", { name: /My Account/ });
    expect(screen.queryByRole("link", { name: /Users & Access/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Recording & Storage/ })).not.toBeInTheDocument();
  });
  it("saves a weekly schedule and explicitly clears a retention limit", async () => {
    const user = userEvent.setup(); const { getBody } = mount("owner", true);
    await screen.findByRole("heading", { name: "Entrance" });
    await user.selectOptions(screen.getByLabelText("When to record"), "scheduled");
    await user.click(screen.getByRole("button", { name: "Mon–Fri, 09:00–18:00" }));
    await user.clear(screen.getByRole("spinbutton", { name: "Keep footage for (days)" }));
    await user.click(screen.getByRole("button", { name: "Save recording settings" }));
    await waitFor(() => expect(getBody()?.mode).toBe("scheduled"));
    expect(getBody().retention_days).toBeNull();
    const days = JSON.parse(getBody().schedule_json).days;
    expect(days[0][9]).toBe(true); expect(days[0][18]).toBe(false); expect(days[6][9]).toBe(false);
  });
});
