import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { AssistantPage } from "./AssistantPage";

vi.mock("@/lib/queries", () => ({ useCurrentUser: () => ({ id: 1, role: "owner" }) }));
function renderAssistant() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>
        <AssistantPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("Recorder assistant", () => {
  it("runs recorder commands without a model and presents review links", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => new Response(JSON.stringify(String(url).endsWith("/status") ? { model_configured: false, model: null } : { message: "1 camera needs attention.", mode: "recorder", checked_at: "2026-11-11T12:00:00Z", actions: [{ label: "Review camera status", href: "/" }] }), { status: 200 }));
    renderAssistant();
    await user.click(screen.getByRole("button", { name: /Find camera issues/ }));
    expect(await screen.findByText("1 camera needs attention.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review camera status" })).toHaveAttribute("href", "/");
    const request = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/chat"));
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({ message: "Which cameras are offline?", use_model: false });
    expect(screen.getByRole("option", { name: /Local AI.*not configured/ })).toBeDisabled();
  });
  it("surfaces a failed request without inventing a reply", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(async url => String(url).endsWith("/status") ? new Response(JSON.stringify({ model_configured: true, model: "local-model" }), { status: 200 }) : new Response(JSON.stringify({ detail: "Local model unavailable" }), { status: 503 }));
    renderAssistant();
    await user.click(screen.getByRole("button", { name: /Check my cameras/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Local model unavailable");
    expect(screen.getByRole("button", { name: "Try this question again" })).toBeInTheDocument();
  });
  it("renders inline markdown bold cleanly and displays live snapshot tool previews", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
      new Response(
        JSON.stringify(
          String(url).endsWith("/status")
            ? { model_configured: true, model: "gemini-3.5-flash-lite", active_provider: "gemini" }
            : {
                message: "Here is **Vizenlink Camera** on `floor 1`.",
                mode: "gemini",
                checked_at: "2026-11-11T12:00:00Z",
                actions: [{ label: "Open Vizenlink Camera (floor 1) Live", href: "/live?camera=VL01" }],
                tool_results: [
                  {
                    tool_name: "get_camera_snapshot",
                    status: "applied",
                    summary: "Fetched latest snapshot from Vizenlink Camera (floor 1).",
                    camera_serial: "VL01",
                    camera_name: "Vizenlink Camera (floor 1)",
                    snapshot_url: "/api/v1/cameras/VL01/snapshot?profile=medium&v=1",
                  },
                ],
              },
        ),
        { status: 200 },
      ),
    );
    renderAssistant();
    const input = await screen.findByLabelText("Ask the recorder assistant");
    await user.type(input, "show snapshot of floor 1 camera{Enter}");
    const boldEl = await screen.findByText("Vizenlink Camera", { selector: "strong" });
    expect(boldEl.tagName).toBe("STRONG");
    expect(screen.queryByText(/\*\*Vizenlink Camera\*\*/)).not.toBeInTheDocument();
    const previewImg = await screen.findByAltText("Live preview of Vizenlink Camera (floor 1)");
    expect(previewImg.getAttribute("src")).toContain("/api/v1/cameras/VL01/snapshot");
  });
  it("persists the active conversation when leaving and returning to the page", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
      new Response(
        JSON.stringify(
          String(url).endsWith("/status")
            ? { model_configured: false, model: null }
            : {
                message: "All 2 cameras are online and recording.",
                mode: "recorder",
                checked_at: "2026-11-16T12:00:00Z",
                actions: [],
              },
        ),
        { status: 200 },
      ),
    );
    const first = renderAssistant();
    await user.click(screen.getByRole("button", { name: /Check my cameras/ }));
    expect(await screen.findByText("All 2 cameras are online and recording.")).toBeInTheDocument();

    // Simulate navigating away and returning to /assistant
    first.unmount();
    renderAssistant();

    expect(screen.getByText("Camera status")).toBeInTheDocument();
    expect(screen.getByText("All 2 cameras are online and recording.")).toBeInTheDocument();
  });
  it("allows starting a new chat and switching back to previous conversations", async () => {
    const user = userEvent.setup();
    let count = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).endsWith("/status")) {
        return new Response(JSON.stringify({ model_configured: false, model: null }), { status: 200 });
      }
      count += 1;
      return new Response(
        JSON.stringify({
          message: count === 1 ? "First chat reply." : "Second chat reply.",
          mode: "recorder",
          checked_at: "2026-11-16T12:00:00Z",
          actions: [],
        }),
        { status: 200 },
      );
    });

    renderAssistant();
    await user.click(screen.getByRole("button", { name: /Check my cameras/ }));
    expect(await screen.findByText("First chat reply.")).toBeInTheDocument();

    // Start a new chat while preserving the previous conversation
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByText("First chat reply.")).not.toBeInTheDocument();
    expect(screen.getByText("Previous conversations")).toBeInTheDocument();

    // Ask a question in the second conversation
    await user.click(screen.getByRole("button", { name: /Find camera issues/ }));
    expect(await screen.findByText("Second chat reply.")).toBeInTheDocument();

    // Open Conversations history and switch back to the first conversation
    await user.click(screen.getByRole("button", { name: /Conversations \(2\)/ }));
    await user.click(screen.getByRole("button", { name: /^Camera status/ }));

    expect(screen.getByText("First chat reply.")).toBeInTheDocument();
    expect(screen.queryByText("Second chat reply.")).not.toBeInTheDocument();
  });
});
