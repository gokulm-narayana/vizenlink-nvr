import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { encode } from "uqr";
import { QrCode } from "./QrCode";
import { PairingDialog } from "./PairingDialog";
import { DevicesPage } from "./DevicesPage";
import { toast } from "sonner";

vi.mock("sonner", () => ({
  toast: vi.fn(),
}));

let mockDevicesData: any[] = [];
let mockQrInitData: any = null;
let mockQrInitReject = false;
let mockRevokeReject = false;
let lastRevokedId: string | null = null;

vi.mock("./api", () => ({
  useQrInit: () => ({
    mutateAsync: vi.fn().mockImplementation(async () => {
      if (mockQrInitReject) {
        throw new Error("Failed to initialize QR session");
      }
      return mockQrInitData;
    }),
    isPending: false,
  }),
  useDevices: () => ({
    data: mockDevicesData,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useRevokeDevice: () => ({
    mutateAsync: vi.fn().mockImplementation(async (id: string) => {
      if (mockRevokeReject) {
        throw new Error("Failed to revoke device");
      }
      lastRevokedId = id;
      mockDevicesData = mockDevicesData.map((d) =>
        d.device_id === id || d.id === id ? { ...d, is_revoked: true } : d
      );
      return { revoked: true };
    }),
    isPending: false,
  }),
}));

describe("Devices Feature", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockQrInitReject = false;
    mockRevokeReject = false;
    lastRevokedId = null;

    mockQrInitData = {
      pairing_code: "VIZEN-7890",
      qr_payload: "vizenlink://pair?code=VIZEN-7890&server=192.168.1.100",
      server_url: "http://192.168.1.100:8000",
      expires_at: new Date(Date.now() + 300000).toISOString(), // 5 mins in future
    };

    mockDevicesData = [
      {
        id: "pk-dev-1",
        device_id: "physical-dev-1",
        device_name: "Operator iPhone",
        platform: "ios",
        user_id: 1,
        username: "operator1",
        paired_at: "2026-06-15T10:00:00Z",
        last_seen_at: "2026-06-15T10:45:00Z",
        is_revoked: false,
      },
      {
        id: "pk-dev-2",
        device_id: "physical-dev-2",
        device_name: "Security Pixel",
        platform: "android",
        user_id: 2,
        username: "guard2",
        paired_at: "2026-06-14T08:00:00Z",
        last_seen_at: "2026-06-15T11:00:00Z",
        is_revoked: false,
      },
    ];
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("QrCode Component", () => {
    it("renders SVG with role=img and exact dark cell rect count from uqr", () => {
      const payload = "vizenlink://pair?code=TEST-123";
      const expectedQr = encode(payload, { ecc: "M", border: 2 });

      let expectedDarkCount = 0;
      for (let y = 0; y < expectedQr.size; y++) {
        for (let x = 0; x < expectedQr.size; x++) {
          if (expectedQr.data[y]?.[x]) {
            expectedDarkCount++;
          }
        }
      }

      const { container } = render(<QrCode payload={payload} />);

      const svg = screen.getByRole("img", { name: "Pairing QR code" });
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute("viewBox", `0 0 ${expectedQr.size} ${expectedQr.size}`);

      // Count black module rects
      const blackRects = container.querySelectorAll('rect[fill="black"]');
      expect(blackRects.length).toBe(expectedDarkCount);

      // White background rect
      const whiteRect = container.querySelector('rect[fill="white"]');
      expect(whiteRect).toBeInTheDocument();
    });

    it("applies dimmed styling when dimmed prop is true", () => {
      const { container } = render(
        <QrCode payload="vizenlink://test" dimmed={true} />
      );
      expect(container.firstChild).toHaveClass("opacity-30");
    });
  });

  describe("PairingDialog", () => {
    it("renders QR, pairing code, expiry countdown, and handles copy to clipboard", async () => {
      const user = userEvent.setup();
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", {
        value: { writeText: writeTextMock },
        writable: true,
        configurable: true,
      });

      renderWithProviders(<PairingDialog isOpen={true} onClose={vi.fn()} />);

      // Wait for QR code and pairing code to appear
      await waitFor(() => {
        expect(screen.getByText("VIZEN-7890")).toBeInTheDocument();
      });

      expect(screen.getByRole("img", { name: "Pairing QR code" })).toBeInTheDocument();
      expect(screen.getByText(/Expires in/i)).toBeInTheDocument();
      expect(screen.getByText("NVR address")).toBeInTheDocument();
      expect(screen.getByText("http://192.168.1.100:8000")).toBeInTheDocument();

      // Numbered instructions
      expect(screen.getByText(/Open VizenLink on your mobile device/i)).toBeInTheDocument();

      // Click copy button
      const copyBtn = screen.getByRole("button", { name: "Copy pairing code" });
      await user.click(copyBtn);

      expect(writeTextMock).toHaveBeenCalledWith("VIZEN-7890");
      expect(toast).toHaveBeenCalledWith("Code copied");
    });

    it("shows plain-HTTP fallback caption when navigator.clipboard is unavailable", async () => {
      const user = userEvent.setup();
      Object.defineProperty(navigator, "clipboard", {
        value: undefined,
        writable: true,
        configurable: true,
      });

      renderWithProviders(<PairingDialog isOpen={true} onClose={vi.fn()} />);

      await waitFor(() => {
        expect(screen.getByText("VIZEN-7890")).toBeInTheDocument();
      });

      const copyBtn = screen.getByRole("button", { name: "Copy pairing code" });
      await user.click(copyBtn);

      expect(screen.getByText("Press Ctrl+C or Cmd+C to copy.")).toBeInTheDocument();
    });

    it("displays error with retry button when init fails", async () => {
      mockQrInitReject = true;
      renderWithProviders(<PairingDialog isOpen={true} onClose={vi.fn()} />);

      await waitFor(() => {
        expect(
          screen.getByText(/Couldn't generate a pairing code/i)
        ).toBeInTheDocument();
      });

      expect(screen.getByRole("button", { name: "Retry generate pairing code" })).toBeInTheDocument();
    });
  });

  describe("DevicesPage & Revoke Flow", () => {
    it("renders paired devices table and cards", () => {
      renderWithProviders(<DevicesPage />);

      expect(screen.getAllByText("Operator iPhone").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Security Pixel").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Revoke device").length).toBeGreaterThanOrEqual(2);
    });

    it("opens alert-dialog and revokes device on confirmation", async () => {
      const user = userEvent.setup();
      const { rerender } = renderWithProviders(<DevicesPage />);

      const revokeBtns = screen.getAllByRole("button", { name: "Revoke device" });
      await user.click(revokeBtns[0]); // Click Operator iPhone revoke

      // Confirmation dialog opens
      const dialog = screen.getByRole("alertdialog");
      expect(dialog).toBeInTheDocument();
      expect(
        screen.getAllByText(/Revoke Operator iPhone\?/i).length
      ).toBeGreaterThanOrEqual(1);
      expect(
        screen.getByText(/It will be signed out and refused until it pairs again\./i)
      ).toBeInTheDocument();

      // Click Revoke device in alert dialog
      const confirmBtn = within(dialog).getByRole("button", { name: "Revoke device" });
      await user.click(confirmBtn);

      // Dialog closes and revokes by unique row PK (not shared physical device_id)
      await waitFor(() => {
        expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
      });
      expect(lastRevokedId).toBe("pk-dev-1");
    });

    it("shows empty state when no paired devices exist", () => {
      mockDevicesData = [];
      renderWithProviders(<DevicesPage />);

      expect(screen.getByText("No mobile devices paired")).toBeInTheDocument();
      expect(
        screen.getByText(/Open VizenLink on your phone, choose Add NVR/i)
      ).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: "Pair mobile device" }).length).toBeGreaterThanOrEqual(1);
    });
  });
});