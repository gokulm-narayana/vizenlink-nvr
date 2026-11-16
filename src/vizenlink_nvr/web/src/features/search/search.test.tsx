import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { SearchPage } from "./SearchPage";
import { searchWindow } from "./filters";

vi.mock("@/lib/queries", () => ({
  useCurrentUser: () => ({ id: 7, username: "operator", role: "operator" }),
  useAuthStatus: () => ({ data: { site_timezone: "Asia/Kolkata" } }),
  useCameras: () => ({ data: [{ serial: "GATE", name: "Front Gate" }, { serial: "LOBBY", name: "Lobby" }] }),
}));

function renderSearch(entry = "/search") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[entry]}><SearchPage /></MemoryRouter></QueryClientProvider>);
}

function lastSearchParams() {
  const calls = vi.mocked(fetch).mock.calls;
  return new URL(String(calls[calls.length - 1]?.[0]), "http://localhost").searchParams;
}

describe("Footage search", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ items: [{ id: 1, kind: "events", camera_serial: "GATE", camera_name: "Front Gate", location: "Entrance", title: "Person", timestamp: "2026-11-11T08:00:00Z", href: "/playback?camera=GATE&t=2026-11-11T08:00:00Z", is_protected: true }], total: 1, offset: 0, limit: 24 }), { status: 200, headers: { "Content-Type": "application/json" } }));
    // Return a fresh response for every filter request.
    const body = { items: [{ id: 1, kind: "events", camera_serial: "GATE", camera_name: "Front Gate", location: "Entrance", title: "Person", timestamp: "2026-11-11T08:00:00Z", href: "/playback?camera=GATE&t=2026-11-11T08:00:00Z", is_protected: true }], total: 1, offset: 0, limit: 24 };
    vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify(body), { status: 200 }));
  });
  afterEach(() => vi.restoreAllMocks());

  it("links a result to its camera and timestamp and applies server-side filters", async () => {
    const user = userEvent.setup();
    renderSearch();
    const link = await screen.findByRole("link", { name: /Front Gate.*Open playback/i });
    expect(link).toHaveAttribute("href", "/playback?camera=GATE&t=2026-11-11T08:00:00Z");
    expect(screen.queryByRole("complementary", { name: "Search filters" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.click(screen.getByRole("button", { name: "Person" }));
    await user.click(screen.getByRole("checkbox", { name: "Front Gate" }));
    await user.click(screen.getByRole("checkbox", { name: "Lobby" }));
    await user.selectOptions(screen.getByLabelText("Search time range"), "exact");
    fireEvent.input(screen.getByLabelText("Start time"), { target: { value: "2026-11-11T13:30" } });
    fireEvent.input(screen.getByLabelText("End time"), { target: { value: "2026-11-11T14:30" } });
    await waitFor(() => {
      const params = lastSearchParams();
      expect(params.getAll("camera_serials")).toEqual(["GATE", "LOBBY"]);
      expect(params.get("event_type")).toBe("person");
      expect(params.get("start_time")).toBe("2026-11-11T08:00:00.000Z");
      expect(params.get("end_time")).toBe("2026-11-11T09:00:00.000Z");
    });
    await user.click(screen.getByRole("button", { name: "Show results" }));
    expect(screen.queryByRole("complementary", { name: "Search filters" })).not.toBeInTheDocument();
  });

  it("saves and restores filter state for the signed-in account", async () => {
    const user = userEvent.setup();
    renderSearch("/search?event_type=person&range=week");
    await user.click(screen.getByRole("button", { name: "Save search" }));
    await user.type(screen.getByRole("textbox", { name: "Search name" }), "Entrance activity");
    await user.click(screen.getByRole("button", { name: "Save search filters" }));
    const stored = JSON.parse(localStorage.getItem("vizenlink_searches_7") || "[]");
    expect(stored[0]).toEqual({ name: "Entrance activity", params: "event_type=person&range=week" });
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await user.click(screen.getByRole("button", { name: "Entrance activity" }));
    expect(screen.getByRole("button", { name: "Person" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Search time range")).toHaveValue("week");
  });

  it("does not query with reversed custom dates", async () => {
    renderSearch("/search?range=custom&from=2026-11-12&to=2026-11-11");
    expect(await screen.findByRole("alert")).toHaveTextContent("End date must be on or after start date");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("widens only the time range and opens events without footage in alert details", async () => {
    vi.mocked(fetch).mockImplementation(async (url) => {
      const params = new URL(String(url), "http://localhost").searchParams;
      const items = params.has("start_time") ? [] : [{
        id: 42, kind: "events", camera_serial: "GATE", camera_name: "Front Gate", location: "Entrance",
        title: "Person", timestamp: "2026-11-11T08:00:00Z", href: "/events/42", is_protected: false,
      }];
      return new Response(JSON.stringify({ items, total: items.length, offset: 0, limit: 24 }), { status: 200 });
    });
    renderSearch("/search?q=gate&camera=GATE&camera=LOBBY&event_type=person");
    await userEvent.click(await screen.findByRole("button", { name: "Search all available history" }));
    expect(await screen.findByRole("link", { name: /Front Gate.*View event/i })).toHaveAttribute("href", "/events/42");
    const params = lastSearchParams();
    expect(params.getAll("camera_serials")).toEqual(["GATE", "LOBBY"]);
    expect(params.get("q")).toBe("gate");
    expect(params.get("event_type")).toBe("person");
  });

  it("filters synthetic object detections without querying the recorder or losing the footage search", async () => {
    const user = userEvent.setup();
    renderSearch("/search?event_type=line_crossing");
    const previewLink = screen.getByRole("link", { name: "Object Search preview" });
    expect(previewLink).toHaveAttribute("href", "/search?event_type=line_crossing&mode=objects");
    vi.mocked(fetch).mockClear();
    await user.click(previewLink);
    expect(screen.getByRole("heading", { name: "Object Search" })).toBeInTheDocument();
    expect(screen.getByText(/results below are synthetic/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "People" }));
    await user.selectOptions(screen.getByLabelText("Clothing"), "Shirt");
    await user.click(screen.getByRole("button", { name: "Red" }));
    expect(screen.getByText("1 sample detection")).toBeInTheDocument();
    expect(screen.getByText("Red shirt")).toBeInTheDocument();
    expect(screen.queryByText("Blue shirt")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Vehicles" }));
    await user.click(screen.getByRole("button", { name: "Any" }));
    await user.type(screen.getByLabelText("License plate"), "demo-042");
    expect(screen.getByText("1 sample detection")).toBeInTheDocument();
    expect(screen.getByText("DEMO 042")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Back to footage search" })).toHaveAttribute("href", "/search?event_type=line_crossing");
  });
});

describe("Timezone-aware search windows", () => {
  it("uses site-local midnight for today and yesterday", () => {
    const now = new Date("2026-11-11T20:00:00Z");
    expect(searchWindow("today", "Asia/Kolkata", undefined, undefined, now)).toEqual({ start: "2026-11-11T18:30:00.000Z", end: "2026-11-12T18:30:00.000Z" });
    expect(searchWindow("yesterday", "Asia/Kolkata", undefined, undefined, now)).toEqual({ start: "2026-11-10T18:30:00.000Z", end: "2026-11-11T18:30:00.000Z" });
  });
  it("handles DST and rejects malformed dates without crashing", () => {
    const span = searchWindow("custom", "America/New_York", "2026-03-08", "2026-03-08");
    expect(Date.parse(span.end!) - Date.parse(span.start!)).toBe(23 * 3600000);
    expect(searchWindow("custom", "UTC", "bad-date", "bad-date").error).toBeTruthy();
    expect(searchWindow("custom", "UTC", "2026-02-30", "2026-03-01").error).toBeTruthy();
  });
  it("rejects skipped exact local times and resolves repeated times to the first occurrence", () => {
    expect(searchWindow("exact", "America/New_York", "2026-03-08T02:30", "2026-03-08T03:30").error).toBeTruthy();
    expect(searchWindow("exact", "America/New_York", "2026-11-01T01:30", "2026-11-01T02:30")).toEqual({
      start: "2026-11-01T05:30:00.000Z", end: "2026-11-01T07:30:00.000Z",
    });
  });
});
