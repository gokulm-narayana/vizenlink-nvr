import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CameraFeaturesTab } from "./CameraFeaturesTab";
import { PrivacyZones, ZonePreview, polygonToRect, rectToPolygon } from "./PrivacyZones";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn() }));
let role = "operator";
vi.mock("@/lib/queries", () => ({ useCurrentUser: () => ({ role }) }));
const api = vi.mocked(apiFetch);

function renderFeature(element = <CameraFeaturesTab serial="CAM-1" cameraName="Front Door" group="network" />) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>{element}</QueryClientProvider>);
}

const detection = {
  title: "Detection & alerts", description: "Choose events", capabilities: { supported_event_types: ["PersonDetected"] },
  values: { getEventPreferences: { PersonDetected: true } }, errors: {},
  operations: [
    { id: "getEventPreferences", method: "GET", path: "/preferences", schema: { type: "object" }, query: {}, read_only: true },
    { id: "setEventPreferences", method: "POST", path: "/preferences", schema: { type: "object", additionalProperties: { type: "boolean" } }, query: {}, read_only: false },
  ],
};

beforeEach(() => { vi.clearAllMocks(); role = "operator"; });

describe("Camera API integration", () => {
  it("previews detection changes without sending any camera request", async () => {
    renderFeature(<CameraFeaturesTab serial="CAM-1" cameraName="Front Door" group="detection" preview />);
    expect(screen.getByRole("heading", { name: "Detection & alerts preview" })).toBeVisible();
    const person = screen.getByRole("checkbox", { name: "Person Detected" });
    expect(person).toBeChecked();
    await userEvent.click(person);
    await userEvent.click(screen.getByRole("button", { name: "Preview event detection change" }));
    expect(person).not.toBeChecked();
    expect(screen.getByText("Preview updated for this session.")).toBeVisible();
    expect(api).not.toHaveBeenCalled();
  });

  it("reads actual event state and sends the changed camera payload", async () => {
    api.mockImplementation(async (_path, init) => init?.method ? { output: {} } : detection);
    renderFeature();
    const person = await screen.findByRole("checkbox", { name: "Person Detected" });
    expect(person).toBeChecked();
    await userEvent.click(person);
    await userEvent.click(screen.getByRole("button", { name: "Apply event detection" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/v1/cameras/CAM-1/features/actions/setEventPreferences", {
      method: "POST", body: { payload: { PersonDetected: false }, query: {}, confirmation: undefined },
    }));
    expect(await screen.findByText("Camera confirmed the change")).toBeVisible();
  });

  it("does not present failed reads as camera values", async () => {
    api.mockRejectedValue(new Error("Camera authentication failed"));
    renderFeature();
    expect(await screen.findByText("Camera authentication failed")).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByText("Camera confirmed the change")).not.toBeInTheDocument();
  });

  it("shows a save rejection without a success message", async () => {
    api.mockImplementation(async (_path, init) => { if (init?.method) throw new Error("Camera rejected this setting"); return detection; });
    renderFeature();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Person Detected" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply event detection" }));
    expect(await screen.findByText("Camera rejected this setting")).toBeVisible();
    expect(screen.queryByText("Camera confirmed the change")).not.toBeInTheDocument();
  });

  it("keeps viewer controls read only", async () => {
    role = "viewer"; api.mockResolvedValue(detection);
    renderFeature();
    expect(await screen.findByRole("button", { name: "Apply event detection" })).toBeDisabled();
  });

  it("hides features the camera does not support", async () => {
    api.mockResolvedValue({ ...detection, capabilities: {}, operations: [{ ...detection.operations[1], capability: "local_storage_capable" }] });
    renderFeature();
    expect(await screen.findByText("This camera does not report support for this feature.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Apply event detection" })).not.toBeInTheDocument();
  });

  it("confirms disruptive actions before making a camera request", async () => {
    api.mockImplementation(async (_path, init) => init?.method ? { output: {} } : {
      ...detection, values: { getPrivacyMode: { mode: "None" } }, operations: [
        { id: "setPrivacyMode", method: "POST", path: "/privacy", schema: { type: "object", properties: { mode: { type: "string", enum: ["Full", "None"] } } }, query: {}, read_only: false, confirmation_required: true },
      ],
    });
    renderFeature();
    await userEvent.selectOptions(await screen.findByLabelText("Mode"), "Full");
    await userEvent.click(screen.getByRole("button", { name: "Apply privacy mode" }));
    const dialog = await screen.findByRole("dialog");
    expect(api.mock.calls.filter(([, init]) => init?.method)).toHaveLength(0);
    await userEvent.type(within(dialog).getByLabelText("Confirm camera name"), "Front Door");
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm camera action" }));
    await waitFor(() => expect(api.mock.calls.some(([, init]) => (init?.body as any)?.confirmation === "CAM-1")).toBe(true));
  });
});

describe("Privacy zones", () => {
  it.each(["privacy", "person"] as const)("edits %s preview zones without requesting camera data", async kind => {
    renderFeature(<ZonePreview kind={kind} />);
    const name = kind === "person" ? "person detection zone" : "privacy zone";
    const zones = screen.getByRole("group", { name: `Selected ${name}` });
    expect(screen.queryByRole("img", { name: "Camera reference for privacy zones" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save preview zone" }));
    // The saved zone stays selected, so it can be changed straight away.
    expect(await within(zones).findByRole("button", { name: "Zone 1", pressed: true })).toBeVisible();
    await userEvent.click(screen.getByRole("checkbox", { name: "Zone enabled" }));
    await userEvent.click(screen.getByRole("button", { name: "Save preview zone" }));
    expect(await within(zones).findByRole("button", { name: "Zone 1 (off)", pressed: true })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Delete zone" }));
    expect(await screen.findByText("0 of 4 preview zones used")).toBeVisible();
    expect(api).not.toHaveBeenCalled();
  });

  const zoneState = (masks: unknown[], max = 4) => ({ options: { max_masks: max, types: ["Color"], rectangle_only: true }, masks });
  const zone = (token: string) => ({ token, polygon: rectToPolygon({ x: 10, y: 20, width: 30, height: 40 }), type: "Color", enabled: true });
  function mockCamera(mode: string) {
    const masks: unknown[] = [];
    api.mockImplementation(async (path, init) => {
      if (init?.method === "POST" && path.endsWith("/masks")) { masks.push(zone("Mask_1")); return { token: "Mask_1" }; }
      if (init?.method) return { output: {} };
      return path.endsWith("/masks") ? zoneState([...masks]) : { values: { getPrivacyMode: { mode } } };
    });
  }
  const snapshot = () => screen.getByRole("img", { name: "Camera reference for privacy zones" }).getAttribute("src");

  it("keeps a new zone selected after saving and reloads the camera picture", async () => {
    mockCamera("Zone");
    renderFeature(<PrivacyZones serial="CAM-1" cameraName="Front Door" />);
    expect(await screen.findByText("Drag on the picture to draw your first zone")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Save zone to camera" })).not.toBeInTheDocument();
    const before = snapshot();
    await userEvent.click(screen.getByRole("button", { name: "Add zone" }));
    await userEvent.click(screen.getByRole("button", { name: "Save zone to camera" }));
    expect(await screen.findByRole("button", { name: "Zone 1", pressed: true })).toBeVisible();
    expect(screen.getByText("Saved to the camera.")).toBeVisible();
    expect(snapshot()).not.toBe(before);
    // Nothing left to save, so a second click cannot create a duplicate zone.
    expect(screen.getByRole("button", { name: "Save zone to camera" })).toBeDisabled();
    expect(api.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("says when zones are not hiding anything and can turn on Zone mode", async () => {
    mockCamera("None");
    renderFeature(<PrivacyZones serial="CAM-1" cameraName="Front Door" />);
    expect(await screen.findByText(/Zones only black out the video when privacy mode is Zone/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Turn on Zone mode" }));
    const dialog = await screen.findByRole("dialog");
    expect(api.mock.calls.filter(([, init]) => init?.method)).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Turn on Zone mode" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/v1/cameras/CAM-1/features/actions/setPrivacyMode", {
      method: "POST", body: { payload: { mode: "Zone" }, query: {}, confirmation: "CAM-1" },
    }));
  });

  it("does not warn about the mode when Zone mode is already on", async () => {
    mockCamera("Zone");
    renderFeature(<PrivacyZones serial="CAM-1" cameraName="Front Door" />);
    expect(await screen.findByText(/Zone mode is on/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Turn on Zone mode" })).not.toBeInTheDocument();
  });

  it("uses the SDK coordinate system with Y increasing upwards", () => {
    const rect = { x: 10, y: 20, width: 30, height: 40 };
    const polygon = rectToPolygon(rect);
    expect(polygon[0]).toEqual({ x: -0.8, y: 0.6 });
    const restored = polygonToRect(polygon);
    for (const key of ["x", "y", "width", "height"] as const) expect(restored[key]).toBeCloseTo(rect[key]);
    expect(rectToPolygon({ x: 0, y: 0, width: 100, height: 100 })).toEqual([{ x: -1, y: 1 }, { x: 1, y: 1 }, { x: 1, y: -1 }, { x: -1, y: -1 }]);
  });

  it("loads a real zone then saves the edited polygon using its camera token", async () => {
    const polygon = rectToPolygon({ x: 10, y: 20, width: 30, height: 40 });
    api.mockImplementation(async (_path, init) => init?.method ? { token: "Mask_42" } : {
      options: { max_masks: 2, types: ["Color"], rectangle_only: true }, masks: [{ token: "Mask_42", polygon, type: "Color", enabled: true }],
    });
    renderFeature(<PrivacyZones serial="CAM-1" cameraName="Front Door" />);
    // The camera's first zone is selected when the editor opens.
    expect(await screen.findByRole("button", { name: "Zone 1", pressed: true })).toBeVisible();
    const left = screen.getByLabelText("Zone x");
    await userEvent.clear(left); await userEvent.type(left, "15");
    await userEvent.click(screen.getByRole("button", { name: "Save zone to camera" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/v1/cameras/CAM-1/features/privacy/masks/Mask_42", {
      method: "PUT", body: { polygon: rectToPolygon({ x: 15, y: 20, width: 30, height: 40 }), type: "Color", enabled: true },
    }));
  });
});
