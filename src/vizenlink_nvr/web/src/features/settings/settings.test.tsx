import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RecordingPage } from "./RecordingPage";
import { SettingsPage } from "./SettingsPage";
import { AiProvidersSettings } from "./AiProvidersSettings";

function mount(role = "owner", recording = false, twoCameras = false) {
  const policy = { camera_serial: "CAM1", mode: "continuous", audio_enabled: false, retention_days: 14, retention_max_gb: null, schedule_json: JSON.stringify({ days: Array.from({ length: 7 }, () => Array(24).fill(true)) }) };
  let body: any;
  const clip = { clip_minutes: 1, clip_minutes_choices: [1, 5, 10, 15, 30, 60] };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    let data: unknown = [];
    if (path.endsWith("auth/status")) data = { authenticated: true, initialized: true, user: { id: 1, username: "Owner", role }, site_timezone: "UTC" };
    else if (path.endsWith("cameras")) data = [{ serial: "CAM1", name: "Entrance" }, ...(twoCameras ? [{ serial: "CAM2", name: "Yard" }] : [])];
    else if (path.endsWith("/system")) data = { recorder_name: "Recorder", site_timezone: "UTC", version: "0.1.0" };
    else if (path.endsWith("storage/status")) data = { storage_path: "/recordings", health_state: "ok", reserve_bytes: 0 };
    else if (path.endsWith("recording/status")) data = [policy, ...(twoCameras ? [{ ...policy, camera_serial: "CAM2" }] : [])];
    else if (path.endsWith("recording/options")) {
      if (init?.method === "PUT") clip.clip_minutes = JSON.parse(String(init.body)).clip_minutes;
      data = clip;
    }
    else if (path.endsWith("recording/apply")) { body = JSON.parse(String(init?.body)); data = { updated: 2 }; }
    else if (init?.method === "PATCH") { body = JSON.parse(String(init.body)); Object.assign(policy, body); data = policy; }
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  const router = createMemoryRouter([{ path: "/", element: recording ? <RecordingPage /> : <SettingsPage /> }, { path: "/settings", element: <SettingsPage /> }]);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RouterProvider router={router} /></QueryClientProvider>);
  return { getBody: () => body, clip };
}
afterEach(() => vi.restoreAllMocks());
describe("Settings workflows", () => {
  it("keeps administration links out of viewer settings", async () => {
    mount("viewer");
    await screen.findByRole("link", { name: /My Account/ });
    expect(screen.queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Recording" })).not.toBeInTheDocument();
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
  it("applies only the checked policy field to the selected cameras", async () => {
    const user = userEvent.setup();
    const { getBody } = mount("owner", true, true);
    await user.click(await screen.findByRole("checkbox", { name: "Select all cameras" }));
    await user.click(screen.getByRole("checkbox", { name: "Recording mode" }));
    await user.selectOptions(screen.getByLabelText("When to record"), "off");
    await user.click(screen.getByRole("button", { name: "Apply to selected (2)" }));
    await waitFor(() => expect(getBody()).toEqual({ serials: ["CAM1", "CAM2"], changes: { mode: "off" } }));
  });
  it("auto-detects compatible Gemini models when an API key is entered and connects without manual model selection", async () => {
    const user = userEvent.setup();
    let detectBody: any = null;
    let saveBody: any = null;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith("auth/status")) {
        return new Response(
          JSON.stringify({ authenticated: true, initialized: true, user: { id: 1, username: "Owner", role: "owner" }, site_timezone: "UTC" }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path.endsWith("/system")) {
        return new Response(
          JSON.stringify({ recorder_name: "Recorder", site_timezone: "UTC", version: "0.1.0" }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path.endsWith("assistant/status")) {
        return new Response(
          JSON.stringify({
            model_configured: false,
            model: null,
            active_provider: "ollama",
            managed_by_environment: false,
            providers: [
              { id: "openai", name: "OpenAI (ChatGPT)", models: ["gpt-4.1-mini"], selected_model: "gpt-4.1-mini", auto_model: true, has_api_key: false, requires_key: true, active: false },
              { id: "gemini", name: "Google Gemini", models: ["gemini-3.5-flash-lite"], selected_model: "gemini-3.5-flash-lite", auto_model: true, has_api_key: false, requires_key: true, active: false },
              { id: "claude", name: "Anthropic Claude", models: ["claude-sonnet-4-20250514"], selected_model: "claude-sonnet-4-20250514", auto_model: true, has_api_key: false, requires_key: true, active: false },
              { id: "ollama", name: "Local AI (Ollama)", models: [], selected_model: null, auto_model: false, has_api_key: false, requires_key: false, active: false },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path.endsWith("assistant/provider/detect")) {
        detectBody = JSON.parse(String(init?.body));
        return new Response(
          JSON.stringify({
            provider: "gemini",
            recommended_model: "gemini-3.5-flash-lite",
            models: ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
            verified: true,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path.endsWith("assistant/provider")) {
        saveBody = JSON.parse(String(init?.body));
        return new Response(
          JSON.stringify({
            model_configured: true,
            model: "gemini-3.5-flash-lite",
            active_provider: "gemini",
            managed_by_environment: false,
            providers: [
              { id: "openai", name: "OpenAI (ChatGPT)", models: ["gpt-4.1-mini"], selected_model: "gpt-4.1-mini", auto_model: true, has_api_key: false, requires_key: true, active: false },
              { id: "gemini", name: "Google Gemini", models: ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"], selected_model: "gemini-3.5-flash-lite", auto_model: true, has_api_key: true, api_key_masked: "fak••••7890", requires_key: true, active: true },
              { id: "claude", name: "Anthropic Claude", models: ["claude-sonnet-4-20250514"], selected_model: "claude-sonnet-4-20250514", auto_model: true, has_api_key: false, requires_key: true, active: false },
              { id: "ollama", name: "Local AI (Ollama)", models: [], selected_model: null, auto_model: false, has_api_key: false, requires_key: false, active: false },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    const router = createMemoryRouter([{ path: "/", element: <AiProvidersSettings /> }]);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole("tab", { name: "Gemini" }));
    await user.type(screen.getByLabelText("Provider API key"), "fake-gemini-key-1234567890");
    await screen.findByText(/Detected 2 compatible models/i);
    expect(detectBody).toEqual({ provider: "gemini", api_key: "fake-gemini-key-1234567890" });
    await user.click(screen.getByRole("button", { name: "Save & connect" }));
    await waitFor(() =>
      expect(saveBody).toEqual({
        provider: "gemini",
        model: "auto",
        api_key: "fake-gemini-key-1234567890",
      }),
    );
  });

  it("changes the clip length for the whole recorder and explains the trade-off", async () => {
    const user = userEvent.setup();
    const { clip } = mount("owner", true);
    const select = await screen.findByLabelText("Length of each clip");
    expect(select).toHaveValue("1");
    expect(screen.getByRole("button", { name: "Save clip length" })).toBeDisabled();
    await user.selectOptions(select, "30");
    expect(screen.getByText(/newest footage can take up to 30 minutes to appear/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save clip length" }));
    await waitFor(() => expect(clip.clip_minutes).toBe(30));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save clip length" })).toBeDisabled());
  });
});
