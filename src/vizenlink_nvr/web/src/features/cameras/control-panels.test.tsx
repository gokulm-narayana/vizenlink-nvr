import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CameraFeaturesTab } from "./CameraFeaturesTab";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn() }));
let role = "operator";
vi.mock("@/lib/queries", () => ({ useCurrentUser: () => ({ role }) }));
const api = vi.mocked(apiFetch);

const op = (id: string, extra: Record<string, unknown> = {}) => ({ id, method: id.startsWith("get") ? "GET" : "POST", path: `/${id}`, schema: { type: "object" }, query: {}, read_only: id.startsWith("get") || id === "queryAlertRule", owner_only: false, confirmation_required: false, ...extra });

function show(group: string, state: Record<string, unknown>) {
  api.mockImplementation(async (_path, init) => (init?.method ? { output: {} } : state) as never);
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <CameraFeaturesTab serial="CAM-1" cameraName="Front Door" group={group} />
    </QueryClientProvider>,
  );
}
const sent = () => api.mock.calls.filter(([, init]) => init?.method).map(([path, init]) => [String(path).split("/").pop(), (init?.body as any)]);

const detection = {
  title: "Detection & alerts", description: "",
  capabilities: {
    supported_event_types: ["PersonDetected", "Loitering", "Tamper"],
    supported_event_deterrence_options: { PersonDetected: ["mobile_alert", "siren"], Loitering: ["mobile_alert"] },
    loitering_duration_min_seconds: 10, loitering_duration_max_seconds: 90, bbox_overlay_capable: true,
  },
  values: {
    getEventPreferences: { PersonDetected: true, Loitering: true, Tamper: false },
    getEventResponseActions: { PersonDetected: ["mobile_alert"], Loitering: [] },
    getLoiteringDuration: { loitering_duration_seconds: 30 },
    getBboxOverlay: { enabled: false },
  },
  errors: {},
  operations: ["getEventPreferences", "setEventPreferences", "getEventResponseActions", "setEventResponseActions", "getLoiteringDuration", "setLoiteringDuration", "getBboxOverlay", "setBboxOverlay", "queryAlertRule", "setAlertRule"].map(id => op(id)),
};

beforeEach(() => { vi.clearAllMocks(); role = "operator"; });

describe("Detection & alerts screen", () => {
  it("shows camera detections in plain words and saves complete maps as camera_api defines", async () => {
    show("detection", detection);
    const person = await screen.findByRole("switch", { name: "Person detected" });
    expect(person).toBeChecked();
    expect(screen.getByRole("switch", { name: "Camera tampering" })).not.toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Person detected: Siren" }));
    await userEvent.click(screen.getByRole("switch", { name: "Camera tampering" }));
    await userEvent.click(screen.getByRole("button", { name: "Save detection settings" }));
    await waitFor(() => expect(sent()).toHaveLength(2));
    expect(sent()[0]).toEqual(["setEventPreferences", { payload: { PersonDetected: true, Loitering: true, Tamper: true }, query: {}, confirmation: undefined }]);
    expect(sent()[1]).toEqual(["setEventResponseActions", { payload: { PersonDetected: ["mobile_alert", "siren"], Loitering: [] }, query: {}, confirmation: undefined }]);
    expect(await screen.findByText("Camera confirmed the change")).toBeVisible();
  });

  it("only offers response actions the camera reports for each event", async () => {
    show("detection", detection);
    await screen.findByRole("switch", { name: "Person detected" });
    expect(screen.queryByRole("checkbox", { name: "Loitering: Siren" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Loitering: Phone alert" })).toBeVisible();
  });

  it("saves loitering time within the camera's range and toggles detection boxes", async () => {
    show("detection", detection);
    const slider = await screen.findByRole("slider", { name: "Loitering time" });
    expect(slider).toHaveAttribute("min", "10");
    expect(slider).toHaveAttribute("max", "90");
    fireEvent.change(slider, { target: { value: "45" } });
    await userEvent.click(screen.getByRole("button", { name: "Save loitering time" }));
    await userEvent.click(screen.getByRole("switch", { name: "Show detection boxes" }));
    await waitFor(() => expect(sent().map(([id]) => id)).toEqual(["setLoiteringDuration", "setBboxOverlay"]));
    expect(sent()[0][1].payload).toEqual({ loitering_duration_seconds: 45 });
    expect(sent()[1][1].payload).toEqual({ enabled: true });
  });

  it("gives every contract event a plain name", async () => {
    show("detection", { ...detection, capabilities: { ...detection.capabilities, supported_event_types: ["VideoModeChanged", "PrivacyModeChanged", "PersonDetected", "Loitering", "Tamper"] } });
    for (const name of ["Day / night switch", "Privacy mode changed", "Person detected", "Loitering", "Camera tampering"]) {
      expect(await screen.findByRole("switch", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("Privacy mode is switched on or off on the camera.")).toBeVisible();
  });

  it("accepts an exact typed loitering time and keeps it within the camera's range", async () => {
    show("detection", { ...detection, capabilities: { ...detection.capabilities, loitering_duration_max_seconds: 1800 } });
    const box = await screen.findByRole("spinbutton", { name: "Loitering time value" });
    await userEvent.clear(box);
    await userEvent.type(box, "300{Enter}");
    expect(screen.getByRole("slider", { name: "Loitering time" })).toHaveValue("300");
    await userEvent.clear(box);
    await userEvent.type(box, "99999{Enter}");
    expect(box).toHaveValue(1800);
    await userEvent.click(screen.getByRole("button", { name: "Save loitering time" }));
    await waitFor(() => expect(sent()).toEqual([["setLoiteringDuration", { payload: { loitering_duration_seconds: 1800 }, query: {}, confirmation: undefined }]]));
  });

  it("does not present failed reads as camera values", async () => {
    show("detection", { ...detection, values: {}, errors: { getEventPreferences: "Camera timed out" } });
    expect(await screen.findByText(/Camera timed out/)).toBeVisible();
    expect(screen.queryByRole("switch", { name: "Person detected" })).not.toBeInTheDocument();
  });

  it("names what the camera does not support instead of hiding it silently", async () => {
    show("detection", { ...detection, capabilities: { ...detection.capabilities, bbox_overlay_capable: false, loitering_duration_min_seconds: undefined } });
    await screen.findByRole("switch", { name: "Person detected" });
    expect(screen.getByRole("note")).toHaveTextContent("Not available on this camera: Loitering time, Detection boxes.");
    expect(screen.queryByRole("slider", { name: "Loitering time" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("switch", { name: "Camera tampering" }));
    expect(screen.getByText("This camera has no automatic responses for this detection.")).toBeVisible();
  });

  it("keeps viewers read only", async () => {
    role = "viewer";
    show("detection", detection);
    expect(await screen.findByRole("switch", { name: "Person detected" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save detection settings" })).toBeDisabled();
  });

  it("keeps less common operations under More camera options", async () => {
    show("detection", detection);
    await screen.findByRole("switch", { name: "Person detected" });
    expect(screen.getByText("More camera options")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rule notifications", hidden: true })).toBeInTheDocument();
  });
});

const audio = {
  title: "Audio", description: "", capabilities: { has_microphone: false, has_speaker: true },
  values: { getAudioSettings: { speaker_volume: 40 }, getTestSoundStatus: { playing: false }, getBuzzerStatus: { active: false } },
  errors: {},
  operations: ["getAudioSettings", "setAudioSettings", "getAudioRecording", "setAudioRecording", "getTestSoundStatus", "setTestSound", "getBuzzerStatus", "setBuzzer"].map(id => op(id)),
};

describe("Audio screen", () => {
  it("hides the microphone when the camera has none and sends only changed levels", async () => {
    show("audio", audio);
    const volume = await screen.findByRole("slider", { name: "Speaker volume" });
    expect(screen.queryByRole("slider", { name: "Microphone level" })).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Not available on this camera: Microphone.");
    fireEvent.change(volume, { target: { value: "70" } });
    await userEvent.click(screen.getByRole("button", { name: "Save audio levels" }));
    await waitFor(() => expect(sent()).toEqual([["setAudioSettings", { payload: { speaker_volume: 70 }, query: {}, confirmation: undefined }]]));
  });

  it("shows the buzzer unless the camera says it has none", async () => {
    show("audio", { ...audio, capabilities: { ...audio.capabilities, buzzer_capable: false } });
    await screen.findByRole("slider", { name: "Speaker volume" });
    expect(screen.queryByRole("button", { name: "Sound buzzer" })).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Not available on this camera: Microphone, Buzzer.");
  });

  it("asks before playing a test sound or sounding the buzzer", async () => {
    show("audio", audio);
    await userEvent.click(await screen.findByRole("button", { name: "Play test sound" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(sent()).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Play test sound" }));
    await waitFor(() => expect(sent()[0]).toEqual(["setTestSound", { payload: { active: true }, query: {}, confirmation: "CAM-1" }]));

    await userEvent.click(screen.getByRole("button", { name: "Sound buzzer" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Sound buzzer" }));
    await waitFor(() => expect(sent()[1]).toEqual(["setBuzzer", { payload: { active: true, duration_seconds: 10 }, query: {}, confirmation: "CAM-1" }]));
  });
});

const deterrence = {
  title: "Siren & spotlight", description: "", capabilities: { siren_capable: true, spotlight_capable: true, warning_capable: false },
  values: {
    getDeterrenceStatus: { siren: false, spotlight: true },
    getDeterrenceDurations: { siren_seconds: 30, spotlight_seconds: 60 },
    getDeterrenceDurationOptions: { siren_seconds_min: 5, siren_seconds_max: 120, spotlight_seconds_min: 10, spotlight_seconds_max: 255 },
  },
  errors: {},
  operations: ["getDeterrenceStatus", "setDeterrence", "getDeterrenceDurations", "setDeterrenceDurations", "getDeterrenceDurationOptions"].map(id => op(id)),
};

describe("Siren & spotlight screen", () => {
  it("shows only outputs the camera has, confirms before turning one on, and turns off directly", async () => {
    show("deterrence", deterrence);
    const turnOn = await screen.findByRole("button", { name: "Turn on siren" });
    expect(screen.queryByRole("button", { name: /voice warning/i })).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Not available on this camera: Voice warning.");
    await userEvent.click(turnOn);
    const dialog = await screen.findByRole("alertdialog");
    expect(sent()).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Turn on siren" }));
    await waitFor(() => expect(sent()[0]).toEqual(["setDeterrence", { payload: { action: "siren", active: true }, query: {}, confirmation: "CAM-1" }]));
    await userEvent.click(screen.getByRole("button", { name: "Turn off spotlight" }));
    await waitFor(() => expect(sent()[1]).toEqual(["setDeterrence", { payload: { action: "spotlight", active: false }, query: {}, confirmation: "CAM-1" }]));
  });

  it("saves only changed stop times within camera-reported ranges", async () => {
    show("deterrence", deterrence);
    const siren = await screen.findByRole("slider", { name: "Siren (seconds)" });
    expect(siren).toHaveAttribute("max", "120");
    fireEvent.change(siren, { target: { value: "90" } });
    await userEvent.click(screen.getByRole("button", { name: "Save stop times" }));
    await waitFor(() => expect(sent()).toEqual([["setDeterrenceDurations", { payload: { siren_seconds: 90 }, query: {}, confirmation: undefined }]]));
  });

  it("explains when the camera has no deterrence outputs", async () => {
    show("deterrence", { ...deterrence, capabilities: {} });
    expect(await screen.findByText("This camera has no siren, spotlight or voice warning.")).toBeVisible();
  });
});
