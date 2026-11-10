import { describe, expect, it } from "vitest";
import { evaluateRecorderStatus, recordingSerials } from "./recorder-status";

const healthy = { status: "healthy", db_ok: true, mediamtx_ok: true, storage_ok: true, total_cameras: 2, active_cameras: 2 };
const cams = [
  { id: 1, serial: "A", name: "Gate", is_online: true },
  { id: 2, serial: "B", name: "Yard", is_online: true },
];
const allRecording = [
  { camera_serial: "A", mode: "continuous", is_recording: true },
  { camera_serial: "B", mode: "continuous", is_recording: true },
];

describe("evaluateRecorderStatus (Phase 10 honest status)", () => {
  it("is Healthy only when storage, services and every camera are fine", () => {
    const r = evaluateRecorderStatus({ health: healthy, storageState: "ok", cameras: cams, recList: allRecording });
    expect(r).toMatchObject({ level: "ok", label: "Healthy", recordingCount: 2, cameraCount: 2 });
  });

  it("reports Not recording with zero recording cameras when storage is unmounted, even if health says ok", () => {
    const r = evaluateRecorderStatus({ health: healthy, storageState: "unmounted", cameras: cams, recList: allRecording });
    expect(r).toMatchObject({ level: "critical", label: "Not recording", recordingCount: 0, storageBroken: true });
  });

  it("reports Not recording when health.storage_ok is false", () => {
    const r = evaluateRecorderStatus({ health: { ...healthy, storage_ok: false }, cameras: cams, recList: allRecording });
    expect(r.label).toBe("Not recording");
  });

  it("reports Not recording when the video service is down", () => {
    const r = evaluateRecorderStatus({ health: { ...healthy, mediamtx_ok: false }, storageState: "ok", cameras: cams, recList: allRecording });
    expect(r).toMatchObject({ level: "critical", label: "Not recording" });
  });

  it("needs attention when a camera is offline or not recording", () => {
    const offline = evaluateRecorderStatus({
      health: healthy,
      storageState: "ok",
      cameras: [cams[0], { ...cams[1], is_online: false }],
      recList: allRecording,
    });
    expect(offline).toMatchObject({ level: "warning", label: "Needs attention" });
    expect(offline.detail).toContain("1 camera offline");

    const notRec = evaluateRecorderStatus({ health: healthy, storageState: "ok", cameras: cams, recList: allRecording.slice(0, 1) });
    expect(notRec.detail).toContain("1 not recording");
  });

  it("trusts is_recording over the configured mode", () => {
    const set = recordingSerials([
      { camera_serial: "A", mode: "continuous", is_recording: false },
      { camera_serial: "B", mode: "off" },
      { camera_serial: "C", mode: "continuous" },
    ]);
    expect([...set]).toEqual(["C"]);
  });
});
