import type { CameraInfo, HealthStatus, RecordingStatusItem } from "@/lib/queries";

/**
 * Phase 10 "honest status": one shared evaluation of whether the recorder is actually
 * saving footage, so the sidebar, header and Dashboard can never disagree.
 * A storage or recorder fault is always "Not recording", never "Healthy".
 */
export type RecorderLevel = "ok" | "warning" | "critical";

export interface RecorderStatusResult {
  level: RecorderLevel;
  label: "Healthy" | "Needs attention" | "Not recording" | "Checking…";
  detail: string;
  recordingCount: number;
  cameraCount: number;
  storageBroken: boolean;
}

const ACTIVE_MODES = new Set(["continuous", "scheduled", "event"]);
const OK_STORAGE = new Set(["ok", "healthy"]);

/** A camera is offline when the API says so, or its registry state is not "active". */
export function isCameraOffline(cam: CameraInfo, openOutageSerials?: Set<string>): boolean {
  if (cam.is_online === false) return true;
  if (typeof cam.state === "string" && cam.state !== "active") return true;
  return Boolean(openOutageSerials?.has(cam.serial));
}

/** Serials that are really recording now; falls back to policy only if the API omits is_recording. */
export function recordingSerials(recList: RecordingStatusItem[]): Set<string> {
  const serials = new Set<string>();
  for (const r of recList) {
    const active = typeof r.is_recording === "boolean" ? r.is_recording : ACTIVE_MODES.has(r.mode);
    if (active) serials.add(r.camera_serial);
  }
  return serials;
}

export function isStorageBroken(storageState?: string | null, health?: HealthStatus | null): boolean {
  if (health?.storage_ok === false) return true;
  if (storageState && !OK_STORAGE.has(storageState)) return true;
  return false;
}

export function evaluateRecorderStatus(input: {
  health?: HealthStatus | null;
  storageState?: string | null;
  cameras: CameraInfo[];
  recList: RecordingStatusItem[];
  openOutageSerials?: Set<string>;
}): RecorderStatusResult {
  const { health, storageState, cameras, recList, openOutageSerials } = input;
  const storageBroken = isStorageBroken(storageState, health);
  const recording = recordingSerials(recList);
  // When storage is broken nothing is written, whatever the per-camera policy says.
  const recordingCount = storageBroken ? 0 : cameras.filter((c) => recording.has(c.serial)).length;
  const cameraCount = cameras.length;
  const base = { recordingCount, cameraCount, storageBroken };

  if (!health && !storageState) {
    return { ...base, level: "warning", label: "Checking…", detail: "Waiting for recorder status." };
  }
  if (storageBroken) {
    return {
      ...base,
      level: "critical",
      label: "Not recording",
      detail: "Recording storage is unavailable. No footage is being saved.",
    };
  }
  if (health?.db_ok === false || health?.mediamtx_ok === false) {
    return {
      ...base,
      level: "critical",
      label: "Not recording",
      detail: health.db_ok === false ? "The recorder database is unreachable." : "The video service is not running.",
    };
  }
  const offline = cameras.filter((c) => isCameraOffline(c, openOutageSerials)).length;
  if (offline > 0 || recordingCount < cameraCount || (health?.status && health.status !== "healthy")) {
    const parts: string[] = [];
    if (offline > 0) parts.push(`${offline} camera${offline === 1 ? "" : "s"} offline`);
    if (recordingCount < cameraCount) parts.push(`${cameraCount - recordingCount} not recording`);
    return {
      ...base,
      level: "warning",
      label: "Needs attention",
      detail: parts.length ? parts.join(", ") : "Some recorder checks need attention.",
    };
  }
  if (cameraCount === 0) {
    return { ...base, level: "ok", label: "Healthy", detail: "Recorder is ready. Add a camera to start recording." };
  }
  return { ...base, level: "ok", label: "Healthy", detail: "All cameras are recording." };
}
