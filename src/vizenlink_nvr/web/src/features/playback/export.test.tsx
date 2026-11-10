import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ClipExportDialog } from "./ClipExportDialog";
import { toast } from "sonner";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe("ClipExportDialog", () => {
  let queryClient: QueryClient;
  const originalFetch = global.fetch;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders prefilled title, start, end, duration caption, and format MP4", () => {
    const inMarker = new Date("2026-11-05T10:00:00.000Z");
    const outMarker = new Date("2026-11-05T10:01:30.000Z"); // 90 sec

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ClipExportDialog
            open={true}
            onOpenChange={vi.fn()}
            cameraSerial="CAM1"
            cameraName="Front Door"
            inMarker={inMarker}
            outMarker={outMarker}
            zone="Asia/Kolkata"
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByRole("heading", { name: "Export clip" })).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("Clip Front Door 15:30:00");
    expect(screen.getByLabelText("Start time")).toHaveValue("2026-11-05T15:30:00");
    expect(screen.getByLabelText("End time")).toHaveValue("2026-11-05T15:31:30");
    expect(screen.getByText("1m 30s")).toBeInTheDocument();
    expect(screen.getByText("MP4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep editing clip" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export clip" })).toBeInTheDocument();
  });

  it("prevents submission and displays field error when End time is before Start time", async () => {
    const inMarker = new Date("2026-11-05T10:00:00.000Z");
    const outMarker = new Date("2026-11-05T09:00:00.000Z"); // Invalid: end before start

    const fetchMock = vi.fn();
    global.fetch = fetchMock;

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ClipExportDialog
            open={true}
            onOpenChange={vi.fn()}
            cameraSerial="CAM1"
            cameraName="Front Door"
            inMarker={inMarker}
            outMarker={outMarker}
            zone="Asia/Kolkata"
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const exportBtn = screen.getByRole("button", { name: "Export clip" });
    await userEvent.click(exportBtn);

    expect(await screen.findByText("End time must be after start time")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts ISO UTC instants, closes on success, and fires toast with Open in Gallery action", async () => {
    let postBody: any = null;
    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/v1/playback/export")) {
        postBody = JSON.parse(init?.body as string);
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 42,
            camera_serial: "CAM1",
            start_time: postBody.start_time,
            end_time: postBody.end_time,
            file_path: "/clips/42.mp4",
            file_size_bytes: 1048576,
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    const onOpenChange = vi.fn();
    const onExportSuccess = vi.fn();
    const inMarker = new Date("2026-11-05T10:00:00.000Z");
    const outMarker = new Date("2026-11-05T10:05:00.000Z");

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ClipExportDialog
            open={true}
            onOpenChange={onOpenChange}
            cameraSerial="CAM1"
            cameraName="Front Door"
            inMarker={inMarker}
            outMarker={outMarker}
            zone="Asia/Kolkata"
            onExportSuccess={onExportSuccess}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const exportBtn = screen.getByRole("button", { name: "Export clip" });
    await userEvent.click(exportBtn);

    await waitFor(() => {
      expect(postBody).not.toBeNull();
      expect(postBody.camera_serial).toBe("CAM1");
      expect(postBody.start_time).toBe("2026-11-05T10:00:00.000Z");
      expect(postBody.end_time).toBe("2026-11-05T10:05:00.000Z");
      expect(onOpenChange).toHaveBeenCalledWith(false);
      expect(onExportSuccess).toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalledWith(
        "Clip exported",
        expect.objectContaining({
          action: expect.objectContaining({ label: "Open in Saved Media" }),
        })
      );
    });
  });

  it("keeps dialog open on failure, displays inline error, and re-labels primary button to Retry export clip", async () => {
    let callCount = 0;
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/playback/export")) {
        callCount++;
        return Promise.resolve({
          ok: false,
          status: 400,
          json: async () => ({ detail: "No recorded footage found in range" }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    const onOpenChange = vi.fn();
    const inMarker = new Date("2026-11-05T10:00:00.000Z");
    const outMarker = new Date("2026-11-05T10:05:00.000Z");

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ClipExportDialog
            open={true}
            onOpenChange={onOpenChange}
            cameraSerial="CAM1"
            cameraName="Front Door"
            inMarker={inMarker}
            outMarker={outMarker}
            zone="Asia/Kolkata"
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const exportBtn = screen.getByRole("button", { name: "Export clip" });
    await userEvent.click(exportBtn);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Couldn't export the clip. Check your connection and that the time range has footage, then try again."
    );

    // Dialog remains open
    expect(onOpenChange).not.toHaveBeenCalledWith(false);

    // Button renamed to "Retry export clip"
    const retryBtn = screen.getByRole("button", { name: "Retry export clip" });
    expect(retryBtn).toBeInTheDocument();

    await userEvent.click(retryBtn);
    await waitFor(() => {
      expect(callCount).toBe(2);
    });
  });
});
