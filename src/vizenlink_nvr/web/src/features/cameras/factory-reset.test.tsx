import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FactoryResetDialog } from "./FactoryResetDialog";
import { CAMERAS_COPY } from "./copy";
import { toast } from "sonner";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe("FactoryResetDialog", () => {
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

  it("renders step 1 with Soft reset preselected and displays mode description", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <FactoryResetDialog
          open={true}
          onOpenChange={vi.fn()}
          serial="CAM1"
          cameraName="Front Door"
        />
      </QueryClientProvider>
    );

    expect(screen.getByText(CAMERAS_COPY.FACTORY_RESET_BUTTON)).toBeInTheDocument();
    expect(screen.getByLabelText(CAMERAS_COPY.SOFT_RESET_TITLE)).toBeChecked();
    expect(
      screen.getAllByText(CAMERAS_COPY.SOFT_RESET_DESC("Front Door"))
    ).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: CAMERAS_COPY.CONTINUE_RESET_BUTTON })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: CAMERAS_COPY.KEEP_SETTINGS_BUTTON })
    ).toBeInTheDocument();
  });

  it("updates description when Hard reset is selected in step 1", async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={queryClient}>
        <FactoryResetDialog
          open={true}
          onOpenChange={vi.fn()}
          serial="CAM1"
          cameraName="Front Door"
        />
      </QueryClientProvider>
    );

    const hardRadio = screen.getByLabelText(CAMERAS_COPY.HARD_RESET_TITLE);
    await user.click(hardRadio);

    expect(hardRadio).toBeChecked();
    expect(
      screen.getAllByText(CAMERAS_COPY.HARD_RESET_DESC("Front Door"))
    ).toHaveLength(2);
  });

  it("advances to step 2 with Soft mode and allows returning to step 1", async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={queryClient}>
        <FactoryResetDialog
          open={true}
          onOpenChange={vi.fn()}
          serial="CAM1"
          cameraName="Front Door"
        />
      </QueryClientProvider>
    );

    await user.click(
      screen.getByRole("button", { name: CAMERAS_COPY.CONTINUE_RESET_BUTTON })
    );

    // Step 2 is shown
    expect(
      screen.getByText(CAMERAS_COPY.SOFT_RESET_CONFIRM("Front Door"))
    ).toBeInTheDocument();
    expect(screen.getByText(CAMERAS_COPY.TYPE_RESET_HELPER)).toBeInTheDocument();

    const destructiveBtn = screen.getByRole("button", {
      name: CAMERAS_COPY.SOFT_RESET_ACTION,
    });
    expect(destructiveBtn).toBeDisabled();

    // Click back to reset mode
    const backBtn = screen.getByRole("button", {
      name: CAMERAS_COPY.BACK_TO_RESET_MODE,
    });
    await user.click(backBtn);

    // Back on step 1
    expect(screen.getByLabelText(CAMERAS_COPY.SOFT_RESET_TITLE)).toBeChecked();
  });

  it("disables destructive button until RESET is typed (case-folded and trimmed)", async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={queryClient}>
        <FactoryResetDialog
          open={true}
          onOpenChange={vi.fn()}
          serial="CAM1"
          cameraName="Front Door"
        />
      </QueryClientProvider>
    );

    await user.click(
      screen.getByRole("button", { name: CAMERAS_COPY.CONTINUE_RESET_BUTTON })
    );

    const input = screen.getByLabelText(CAMERAS_COPY.TYPE_RESET_LABEL);
    const destructiveBtn = screen.getByRole("button", {
      name: CAMERAS_COPY.SOFT_RESET_ACTION,
    });

    expect(destructiveBtn).toBeDisabled();

    await user.type(input, "wrong");
    expect(destructiveBtn).toBeDisabled();

    await user.clear(input);
    await user.type(input, "  reset  ");
    expect(destructiveBtn).toBeEnabled();
  });

  it("sends exact body { mode: 'Soft', confirmation: 'RESET' } and never camera name (Acceptance 11)", async () => {
    const user = userEvent.setup();
    let capturedBody: any = null;
    let capturedUrl = "";

    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      capturedUrl = url;
      capturedBody = JSON.parse(init?.body as string);
      return Promise.resolve({
        ok: true,
        json: async () => ({ message: "Soft factory reset initiated successfully" }),
      });
    });

    const onOpenChange = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <FactoryResetDialog
          open={true}
          onOpenChange={onOpenChange}
          serial="CAM1"
          cameraName="Front Door"
        />
      </QueryClientProvider>
    );

    await user.click(
      screen.getByRole("button", { name: CAMERAS_COPY.CONTINUE_RESET_BUTTON })
    );

    const input = screen.getByLabelText(CAMERAS_COPY.TYPE_RESET_LABEL);
    await user.type(input, "RESET");

    const destructiveBtn = screen.getByRole("button", {
      name: CAMERAS_COPY.SOFT_RESET_ACTION,
    });
    await user.click(destructiveBtn);

    await waitFor(() => {
      expect(capturedUrl).toContain("/api/v1/cameras/CAM1/factory-reset");
      expect(capturedBody).toEqual({
        mode: "Soft",
        confirmation: "RESET",
      });
      // Explicitly assert camera name is NOT in the body
      expect(capturedBody.name).toBeUndefined();
      expect(capturedBody.cameraName).toBeUndefined();
      expect(toast.success).toHaveBeenCalledWith(
        CAMERAS_COPY.SOFT_RESET_STARTED("Front Door")
      );
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it("sends exact body { mode: 'Hard', confirmation: 'RESET' } for Hard reset (Acceptance 11)", async () => {
    const user = userEvent.setup();
    let capturedBody: any = null;
    let capturedUrl = "";

    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      capturedUrl = url;
      capturedBody = JSON.parse(init?.body as string);
      return Promise.resolve({
        ok: true,
        json: async () => ({ message: "Hard factory reset initiated successfully" }),
      });
    });

    const onOpenChange = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <FactoryResetDialog
          open={true}
          onOpenChange={onOpenChange}
          serial="CAM1"
          cameraName="Front Door"
        />
      </QueryClientProvider>
    );

    // Select Hard reset
    await user.click(screen.getByLabelText(CAMERAS_COPY.HARD_RESET_TITLE));
    await user.click(
      screen.getByRole("button", { name: CAMERAS_COPY.CONTINUE_RESET_BUTTON })
    );

    // Verify Hard reset confirm message
    expect(
      screen.getByText(CAMERAS_COPY.HARD_RESET_CONFIRM("Front Door"))
    ).toBeInTheDocument();

    const input = screen.getByLabelText(CAMERAS_COPY.TYPE_RESET_LABEL);
    await user.type(input, "RESET");

    const destructiveBtn = screen.getByRole("button", {
      name: CAMERAS_COPY.HARD_RESET_ACTION,
    });
    await user.click(destructiveBtn);

    await waitFor(() => {
      expect(capturedUrl).toContain("/api/v1/cameras/CAM1/factory-reset");
      expect(capturedBody).toEqual({
        mode: "Hard",
        confirmation: "RESET",
      });
      expect(toast.success).toHaveBeenCalledWith(
        CAMERAS_COPY.HARD_RESET_STARTED("Front Door")
      );
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it("shows InlineError on failure and keeps dialog open", async () => {
    const user = userEvent.setup();

    global.fetch = vi.fn().mockImplementation(() => {
      return Promise.resolve({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => ({ detail: "Camera unreachable" }),
      });
    });

    const onOpenChange = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <FactoryResetDialog
          open={true}
          onOpenChange={onOpenChange}
          serial="CAM1"
          cameraName="Front Door"
        />
      </QueryClientProvider>
    );

    await user.click(
      screen.getByRole("button", { name: CAMERAS_COPY.CONTINUE_RESET_BUTTON })
    );

    const input = screen.getByLabelText(CAMERAS_COPY.TYPE_RESET_LABEL);
    await user.type(input, "RESET");

    const destructiveBtn = screen.getByRole("button", {
      name: CAMERAS_COPY.SOFT_RESET_ACTION,
    });
    await user.click(destructiveBtn);

    await waitFor(() => {
      expect(
        screen.getByText(CAMERAS_COPY.RESET_FAILED("Front Door"))
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: CAMERAS_COPY.RETRY_RESET })
      ).toBeInTheDocument();
      expect(onOpenChange).not.toHaveBeenCalled();
    });
  });
});
