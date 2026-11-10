import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AddCameraPage } from "./AddCameraPage";
import { toCreateRequest, addCameraSchema } from "./schema";
import { ADD_CAMERA_COPY } from "./copy";
import { toast } from "sonner";
import { useUiStore } from "@/stores/ui";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/lib/queries", () => ({
  useCameras: () => ({ data: [] }),
  useCurrentUser: () => ({
    id: 1,
    username: "operator1",
    role: "operator",
  }),
}));

describe("Add Camera Feature", () => {
  let queryClient: QueryClient;
  const originalFetch = global.fetch;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    vi.clearAllMocks();
    useUiStore.setState({ viewMode: "advanced" });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  function renderWizard() {
    const router = createMemoryRouter(
      [
        {
          path: "/cameras/add",
          element: <AddCameraPage />,
        },
        {
          path: "/cameras/:serial",
          element: <div data-testid="camera-page">Camera Detail Page</div>,
        },
        {
          path: "/cameras",
          element: <div data-testid="cameras-list">Cameras List Page</div>,
        },
      ],
      { initialEntries: ["/cameras/add"] }
    );

    return render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    );
  }

  describe("toCreateRequest helper", () => {
    it("transforms minimal values with default name, location, group and 1 main stream", () => {
      const formValues = {
        serial: "CAM-01",
        host: "192.168.1.100",
        https_port: 443,
        username: "admin",
        password: "secretpassword",
        name: "",
        location: "",
        group_tag: "",
        main_scheme: "rtsp" as const,
        main_port: 554,
        main_path: "/stream1",
        main_codec: "H264",
        main_width: 1920,
        main_height: 1080,
        main_transport: "tcp",
        main_profile_token: "Profile_1",
        main_venc_token: "VideoEncoder_1",
        has_sub_stream: false,
        sub_scheme: "rtsp" as const,
        sub_port: 554,
        sub_path: "",
        sub_codec: "H264",
        sub_width: 1920,
        sub_height: 1080,
        sub_transport: "tcp",
        sub_profile_token: "Profile_2",
        sub_venc_token: "VideoEncoder_2",
      };

      const req = toCreateRequest(formValues);
      expect(req.serial).toBe("CAM-01");
      expect(req.host).toBe("192.168.1.100");
      expect(req.name).toBe("CAM-01"); // defaults to serial
      expect(req.location).toBe("Default"); // defaults to Default
      expect(req.group_tag).toBe("default"); // defaults to default
      expect(req.streams).toHaveLength(1);
      expect(req.streams[0].role).toBe("main");
      expect(req.streams[0].profile_token).toBe("Profile_1");
      expect(req.streams[0].venc_token).toBe("VideoEncoder_1");
    });

    it("includes sub stream with distinct tokens when has_sub_stream is true", () => {
      const formValues = {
        serial: "CAM-02",
        host: "10.0.0.5",
        https_port: 8443,
        username: "root",
        password: "pw",
        name: "Backyard",
        location: "Outdoor",
        group_tag: "perimeter",
        main_scheme: "rtsps" as const,
        main_port: 322,
        main_path: "/live/main",
        main_codec: "H264",
        main_width: 1920,
        main_height: 1080,
        main_transport: "tcp",
        main_profile_token: "Profile_1",
        main_venc_token: "VideoEncoder_1",
        has_sub_stream: true,
        sub_scheme: "rtsp" as const,
        sub_port: 554,
        sub_path: "/live/sub",
        sub_codec: "H264",
        sub_width: 640,
        sub_height: 360,
        sub_transport: "tcp",
        sub_profile_token: "Profile_2",
        sub_venc_token: "VideoEncoder_2",
      };

      const req = toCreateRequest(formValues);
      expect(req.name).toBe("Backyard");
      expect(req.location).toBe("Outdoor");
      expect(req.group_tag).toBe("perimeter");
      expect(req.streams).toHaveLength(2);
      expect(req.streams[0].role).toBe("main");
      expect(req.streams[1].role).toBe("sub");
      expect(req.streams[1].profile_token).toBe("Profile_2");
      expect(req.streams[1].venc_token).toBe("VideoEncoder_2");
      expect(req.streams[1].path).toBe("/live/sub");
    });
  });

  describe("Wizard step flow", () => {
    it("renders step 1 with page header and scan note", () => {
      renderWizard();

      expect(screen.getByRole("heading", { name: ADD_CAMERA_COPY.TITLE })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Find cameras" })).toBeInTheDocument();
      expect(screen.getByText(ADD_CAMERA_COPY.STEP_CAPTION(1, 3))).toBeInTheDocument();
      expect(screen.getByLabelText(ADD_CAMERA_COPY.SERIAL_LABEL)).toBeInTheDocument();
      expect(screen.getByLabelText(ADD_CAMERA_COPY.HOST_LABEL)).toBeInTheDocument();
      expect(screen.getByLabelText(ADD_CAMERA_COPY.PASSWORD_LABEL)).toBeInTheDocument();
    });

    it("validates required fields on Continue to details and focuses first invalid field", async () => {
      const user = userEvent.setup();
      renderWizard();

      const continueBtn = screen.getByRole("button", {
        name: ADD_CAMERA_COPY.CONTINUE_TO_DETAILS,
      });
      await user.click(continueBtn);

      expect(await screen.findByText(ADD_CAMERA_COPY.SERIAL_REQUIRED)).toBeInTheDocument();
      expect(screen.getByText(ADD_CAMERA_COPY.HOST_REQUIRED)).toBeInTheDocument();
      expect(screen.getByText(ADD_CAMERA_COPY.PASSWORD_REQUIRED)).toBeInTheDocument();

      // Serial should have focus
      expect(screen.getByLabelText(ADD_CAMERA_COPY.SERIAL_LABEL)).toHaveFocus();
    });

    it("advances through all 3 steps, reviews details, and submits successfully (201)", async () => {
      const user = userEvent.setup();
      let capturedBody: any = null;

      global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url.includes("/api/v1/cameras") && init?.method === "POST") {
          capturedBody = JSON.parse(init.body as string);
          return Promise.resolve({
            ok: true,
            status: 201,
            json: async () => ({
              serial: "CAM-01",
              name: "Front Yard",
              host: "192.168.1.50",
            }),
          });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });

      renderWizard();

      // Step 1: Fill Camera fields
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.SERIAL_LABEL), "CAM-01");
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.HOST_LABEL), "192.168.1.50");
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.PASSWORD_LABEL), "CameraPass123");

      await user.click(
        screen.getByRole("button", { name: ADD_CAMERA_COPY.CONTINUE_TO_DETAILS })
      );

      // Step 2: Details
      expect(screen.getByText(ADD_CAMERA_COPY.STEP_CAPTION(2, 3))).toBeInTheDocument();
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.NAME_LABEL), "Front Yard");
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.LOCATION_LABEL), "Gate");

      await user.click(
        screen.getByRole("button", { name: ADD_CAMERA_COPY.CONTINUE_TO_STREAMS })
      );

      // Step 3: Streams
      expect(screen.getByText(ADD_CAMERA_COPY.STEP_CAPTION(3, 3))).toBeInTheDocument();
      expect(screen.getByText(ADD_CAMERA_COPY.REVIEW_TITLE)).toBeInTheDocument();
      expect(screen.getByText("CAM-01")).toBeInTheDocument();
      expect(screen.getByText("Front Yard")).toBeInTheDocument();
      expect(screen.getByText("••••••••")).toBeInTheDocument();

      // Submit
      await user.click(
        screen.getByRole("button", { name: ADD_CAMERA_COPY.ADD_CAMERA_BUTTON })
      );

      await waitFor(() => {
        expect(capturedBody).not.toBeNull();
        expect(capturedBody.serial).toBe("CAM-01");
        expect(capturedBody.name).toBe("Front Yard");
        expect(capturedBody.location).toBe("Gate");
        expect(capturedBody.streams).toHaveLength(1);
        expect(toast.success).toHaveBeenCalledWith(
          ADD_CAMERA_COPY.SUCCESS_TOAST("Front Yard")
        );
        expect(screen.getByTestId("camera-page")).toBeInTheDocument();
      });
    });
  });

  describe("Error Mapping", () => {
    it("handles 409 conflict by returning to step 1 and showing link to existing camera", async () => {
      const user = userEvent.setup();

      global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url.includes("/api/v1/cameras") && init?.method === "POST") {
          return Promise.resolve({
            ok: false,
            status: 409,
            statusText: "Conflict",
            json: async () => ({
              detail: "Camera with serial 'CAM-01' already exists",
            }),
          });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });

      renderWizard();

      // Fill Step 1
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.SERIAL_LABEL), "CAM-01");
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.HOST_LABEL), "192.168.1.50");
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.PASSWORD_LABEL), "pass");

      await user.click(screen.getByRole("button", { name: ADD_CAMERA_COPY.CONTINUE_TO_DETAILS }));
      await user.click(screen.getByRole("button", { name: ADD_CAMERA_COPY.CONTINUE_TO_STREAMS }));

      // Submit on step 3
      await user.click(screen.getByRole("button", { name: ADD_CAMERA_COPY.ADD_CAMERA_BUTTON }));

      // Back on Step 1 with error and link
      await waitFor(() => {
        expect(screen.getByText(ADD_CAMERA_COPY.STEP_CAPTION(1, 3))).toBeInTheDocument();
        expect(
          screen.getByText(ADD_CAMERA_COPY.SERIAL_EXISTS("CAM-01"))
        ).toBeInTheDocument();
        const link = screen.getByRole("link", {
          name: ADD_CAMERA_COPY.OPEN_EXISTING_CAMERA("CAM-01"),
        });
        expect(link).toHaveAttribute("href", "/cameras/CAM-01");
      });
    });

    it("handles 503 vault unavailable with specific error and retry action", async () => {
      const user = userEvent.setup();

      global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url.includes("/api/v1/cameras") && init?.method === "POST") {
          return Promise.resolve({
            ok: false,
            status: 503,
            statusText: "Service Unavailable",
            json: async () => ({
              detail: "Camera credentials can't be stored because the NVR credential vault is unavailable.",
            }),
          });
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      });

      renderWizard();

      // Fill Step 1
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.SERIAL_LABEL), "CAM-01");
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.HOST_LABEL), "192.168.1.50");
      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.PASSWORD_LABEL), "pass");

      await user.click(screen.getByRole("button", { name: ADD_CAMERA_COPY.CONTINUE_TO_DETAILS }));
      await user.click(screen.getByRole("button", { name: ADD_CAMERA_COPY.CONTINUE_TO_STREAMS }));
      await user.click(screen.getByRole("button", { name: ADD_CAMERA_COPY.ADD_CAMERA_BUTTON }));

      await waitFor(() => {
        expect(
          screen.getByText(ADD_CAMERA_COPY.VAULT_UNAVAILABLE_ERROR)
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: ADD_CAMERA_COPY.RETRY_ADD })
        ).toBeInTheDocument();
      });
    });
  });

  describe("Leave protection", () => {
    it("leaves immediately when no input is entered", async () => {
      const user = userEvent.setup();
      renderWizard();

      const discardBtn = screen.getByRole("button", {
        name: ADD_CAMERA_COPY.DISCARD_BUTTON,
      });
      await user.click(discardBtn);

      expect(screen.getByTestId("cameras-list")).toBeInTheDocument();
    });

    it("shows confirmation dialog when input is dirty and cancels on keep editing", async () => {
      const user = userEvent.setup();
      renderWizard();

      await user.type(screen.getByLabelText(ADD_CAMERA_COPY.SERIAL_LABEL), "CAM-01");

      const discardBtn = screen.getByRole("button", {
        name: ADD_CAMERA_COPY.DISCARD_BUTTON,
      });
      await user.click(discardBtn);

      expect(screen.getByText(ADD_CAMERA_COPY.DISCARD_TITLE)).toBeInTheDocument();

      const keepBtn = screen.getByRole("button", {
        name: ADD_CAMERA_COPY.KEEP_EDITING_BUTTON,
      });
      await user.click(keepBtn);

      expect(screen.queryByText(ADD_CAMERA_COPY.DISCARD_TITLE)).not.toBeInTheDocument();
      expect(screen.getByLabelText(ADD_CAMERA_COPY.SERIAL_LABEL)).toHaveValue("CAM-01");
    });
  });
});
