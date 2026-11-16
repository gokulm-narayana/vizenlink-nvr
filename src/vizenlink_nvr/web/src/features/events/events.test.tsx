import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { EventsPage } from "./EventsPage";
import { EventCard } from "./EventCard";
import { EventSheet } from "./EventSheet";
import type { EventItem } from "./api";
import { useUiStore } from "@/stores/ui";

const mockNavigate = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual("react-router");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock camera query
vi.mock("@/lib/queries", () => ({
  useCameras: () => ({
    data: [
      { serial: "CAM-01", name: "Front Door" },
      { serial: "CAM-02", name: "Backyard" },
    ],
  }),
  useAuthStatus: () => ({
    data: { site_timezone: "UTC" },
  }),
  useCurrentUser: () => ({ id: 1, username: "op", role: "operator", permissions: ["*"] }),
}));

describe("Events Feature", () => {
  const mockEvent1: EventItem = {
    id: 101,
    camera_serial: "CAM-01",
    event_type: "motion",
    source: "onvif",
    start_time: "2026-06-15T12:00:00Z",
    end_time: "2026-06-15T12:01:00Z",
    snapshot_path: "/snapshots/101.jpg",
    is_locked: false,
    clock_sync_state: "synced",
    raw_topic: "tns1:RuleEngine/CellMotionDetector/Motion",
    details: { motion_score: 85 },
    created_at: "2026-06-15T12:00:05Z",
  };

  const mockEvent2: EventItem = {
    id: 102,
    camera_serial: "CAM-02",
    event_type: "tamper",
    source: "onvif",
    start_time: "2026-06-15T13:00:00Z",
    end_time: null,
    snapshot_path: null,
    is_locked: true,
    clock_sync_state: "drift_uncertain",
    raw_topic: "tns1:Device/Trigger/Tamper",
    details: { reason: "covered" },
    created_at: "2026-06-15T13:00:05Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useUiStore.setState({
      viewMode: "simple",
      readEventIds: new Set<number>(),
    });
  });

  const renderWithProviders = (
    ui: React.ReactElement,
    initialEntries = ["/events"]
  ) => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/events" element={ui} />
            <Route path="*" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("EventCard", () => {
    it("renders card with snapshot, type badge, camera name, and relative time", () => {
      const onClick = vi.fn();
      renderWithProviders(
        <EventCard
          event={mockEvent1}
          cameraName="Front Door"
          isRead={false}
          onClick={onClick}
          zone="UTC"
        />
      );

      expect(screen.getByText("Motion")).toBeInTheDocument();
      expect(screen.getByText("Front Door")).toBeInTheDocument();
      expect(screen.getByText("Unread")).toBeInTheDocument();
      expect(screen.getByRole("button")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button"));
      expect(onClick).toHaveBeenCalledWith(mockEvent1);
    });

    it("renders locked icon when event is locked, and placeholder when no snapshot", () => {
      renderWithProviders(
        <EventCard
          event={mockEvent2}
          cameraName="Backyard"
          isRead={true}
          onClick={vi.fn()}
          zone="UTC"
        />
      );

      expect(screen.getByText("Tamper")).toBeInTheDocument();
      expect(screen.getByText("No snapshot available")).toBeInTheDocument();
      expect(screen.queryByText("Unread")).not.toBeInTheDocument();
      expect(screen.getByTitle("Locked")).toBeInTheDocument();
    });
  });

  describe("EventSheet", () => {
    it("renders details and navigates to playback on Play footage click", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();

      renderWithProviders(
        <EventSheet
          event={mockEvent1}
          cameraName="Front Door"
          isOpen={true}
          onClose={onClose}
          zone="UTC"
        />
      );

      expect(screen.getByText("Alert type: Motion")).toBeInTheDocument();
      expect(screen.getByText("Front Door")).toBeInTheDocument();
      expect(screen.getByText("101")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Close alert details" })
      ).toBeInTheDocument();

      const playBtn = screen.getByRole("button", { name: "Play footage" });
      await user.click(playBtn);

      expect(onClose).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith(
        "/playback?camera=CAM-01&t=2026-06-15T12%3A00%3A00Z"
      );
    });

    it("displays Advanced metadata only in advanced view mode", () => {
      useUiStore.setState({ viewMode: "simple" });
      const { rerender } = renderWithProviders(
        <EventSheet
          event={mockEvent1}
          cameraName="Front Door"
          isOpen={true}
          onClose={vi.fn()}
          zone="UTC"
        />
      );

      expect(screen.queryByText("Advanced Metadata")).not.toBeInTheDocument();
      expect(screen.queryByText("Camera clock synced")).not.toBeInTheDocument();

      // Switch to Advanced
      useUiStore.setState({ viewMode: "advanced" });
      rerender(
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <MemoryRouter initialEntries={["/events"]}>
            <EventSheet
              event={mockEvent1}
              cameraName="Front Door"
              isOpen={true}
              onClose={vi.fn()}
              zone="UTC"
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(screen.getByText("Advanced Metadata")).toBeInTheDocument();
      expect(screen.getByText("Camera clock synced")).toBeInTheDocument();
      expect(
        screen.getByText("tns1:RuleEngine/CellMotionDetector/Motion")
      ).toBeInTheDocument();
    });

    it("handles lock mutation failure by reverting switch and showing inline error", async () => {
      const user = userEvent.setup();
      // Mock fetch failure for /api/v1/events/101/lock
      global.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes("/lock")) {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: async () => ({ detail: "Database error" }),
          });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });

      renderWithProviders(
        <EventSheet
          event={mockEvent1}
          cameraName="Front Door"
          isOpen={true}
          onClose={vi.fn()}
          zone="UTC"
        />
      );

      const lockSwitch = screen.getByRole("switch", { name: "Lock alert" });
      expect(lockSwitch).not.toBeChecked();

      await user.click(lockSwitch);

      await waitFor(() => {
        expect(
          screen.getByText("Couldn't lock the alert. Check your connection and try again.")
        ).toBeInTheDocument();
      });

      // Switch reverted to unchecked
      expect(lockSwitch).not.toBeChecked();
      expect(screen.getByRole("button", { name: "Retry lock alert" })).toBeInTheDocument();
    });
  });

  describe("EventsPage", () => {
    it("renders empty state when there are no events", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
      });

      renderWithProviders(<EventsPage />);

      await waitFor(() => {
        expect(screen.getByText("No alerts yet")).toBeInTheDocument();
      });
      expect(
        screen.getByText("No alerts yet. Alerts from your cameras show up here as they happen.")
      ).toBeInTheDocument();
    });

    it("renders cards and marks event read on click", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          items: [mockEvent1, mockEvent2],
          total: 2,
          limit: 50,
          offset: 0,
        }),
      });

      renderWithProviders(<EventsPage />);

      await waitFor(() => {
        expect(screen.getByText("Total events:")).toBeInTheDocument();
      });

      expect(screen.getByText("Front Door")).toBeInTheDocument();
      expect(screen.getByText("Backyard")).toBeInTheDocument();

      // Unread dot present on both unread events
      expect(screen.getAllByText("Unread")).toHaveLength(2);

      // Click card to open sheet and mark read
      fireEvent.click(screen.getByText("Front Door"));

      await waitFor(() => {
        expect(screen.getByRole("dialog")).toBeInTheDocument();
      });

      expect(useUiStore.getState().readEventIds.has(101)).toBe(true);
    });

    it("filters unread client-side in advanced view mode", async () => {
      useUiStore.setState({
        viewMode: "advanced",
        readEventIds: new Set([101]),
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          items: [mockEvent1, mockEvent2],
          total: 2,
          limit: 50,
          offset: 0,
        }),
      });

      const user = userEvent.setup();
      renderWithProviders(<EventsPage />);

      await waitFor(() => {
        expect(screen.getByText("Front Door")).toBeInTheDocument();
      });

      const unreadSwitch = screen.getByRole("switch", { name: "Unread only" });
      await user.click(unreadSwitch);

      // Event 101 is read, so only Event 102 (Backyard) remains
      expect(screen.queryByText("Front Door")).not.toBeInTheDocument();
      expect(screen.getByText("Backyard")).toBeInTheDocument();
    });
  });

  describe("Alert review (Phase 10)", () => {
    it("shows severity and status, and acknowledges / resolves from the alert panel", async () => {
      const user = userEvent.setup();
      const fetchMock = vi.fn().mockImplementation(async (url: string) => ({
        ok: true,
        status: 200,
        json: async () => ({ ...mockEvent2, review_state: url.endsWith("acknowledge") ? "acknowledged" : "resolved" }),
      }));
      global.fetch = fetchMock as unknown as typeof fetch;

      renderWithProviders(
        <EventSheet
          event={{ ...mockEvent2, severity: "critical", review_state: "new" }}
          cameraName="Backyard"
          isOpen={true}
          onClose={() => {}}
          zone="UTC"
        />
      );

      expect(screen.getByText("Critical")).toBeInTheDocument();
      expect(screen.getByText("New")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Open alert details" })).toHaveAttribute("href", "/events/102");

      await user.click(screen.getByRole("button", { name: "Acknowledge" }));
      await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/events/102/acknowledge", { method: "POST" }));
      await user.click(screen.getByRole("button", { name: "Resolve" }));
      await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/events/102/resolve", { method: "POST" }));
    });

    it("removes an alert only after confirming, explaining that footage is kept", async () => {
      const user = userEvent.setup();
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ hidden: true }) });
      global.fetch = fetchMock as unknown as typeof fetch;
      const onClose = vi.fn();

      renderWithProviders(
        <EventSheet event={{ ...mockEvent1, review_state: "acknowledged" }} cameraName="Front Door" isOpen={true} onClose={onClose} zone="UTC" />
      );
      await user.click(screen.getByRole("button", { name: "Remove alert" }));
      expect(screen.getByText(/recorded footage is not deleted/i)).toBeInTheDocument();
      const removeButtons = screen.getAllByRole("button", { name: "Remove alert" });
      await user.click(removeButtons[removeButtons.length - 1]);
      await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/events/101/hide", { method: "POST" }));
      await waitFor(() => expect(onClose).toHaveBeenCalled());
    });

    it("sends search, severity and open-status filters, and acknowledges all", async () => {
      const user = userEvent.setup();
      const fetchMock = vi.fn().mockImplementation(async (url: string) => ({
        ok: true,
        status: 200,
        json: async () =>
          url.includes("acknowledge-all") ? { acknowledged: 2 } : { items: [mockEvent1, mockEvent2], total: 2, limit: 50, offset: 0 },
      }));
      global.fetch = fetchMock as unknown as typeof fetch;

      renderWithProviders(<EventsPage />, ["/events?severity=critical"]);
      await screen.findByText("Front Door");
      const listUrl = String(fetchMock.mock.calls[0][0]);
      expect(listUrl).toContain("severity=critical");
      expect(listUrl).toContain("review_state=open");

      await user.type(screen.getByRole("textbox", { name: "Search alerts" }), "gate");
      await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("q=gate"))).toBe(true));

      await user.click(screen.getByRole("button", { name: "Acknowledge all" }));
      await waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/v1/events/acknowledge-all",
          expect.objectContaining({ method: "POST", body: JSON.stringify({ severity: "critical" }) })
        )
      );
    });
  });
});
