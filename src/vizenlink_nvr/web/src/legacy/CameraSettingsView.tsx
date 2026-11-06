import React, { useEffect, useState } from "react";
import type { CameraInfo } from "@/lib/types";

interface CameraSettingsViewProps {
  cameras: CameraInfo[];
  userRole?: string;
}

interface CameraSettingsData {
  identity: {
    name: string;
    location: string;
    timezone?: string;
    supported_timezones: Array<{ code: string; label: string }>;
  };
  device_info: {
    manufacturer: string;
    model: string;
    firmware_version: string;
    serial_number: string;
    hardware_id: string;
  };
  encoders: Array<{
    profile_token: string;
    profile_name: string;
    venc_token: string;
    current: {
      encoding: string;
      width: number;
      height: number;
      quality: number;
      frame_rate_limit: number;
      bitrate_limit_kbps: number;
      gov_length: number;
      profile: string;
    };
    options: {
      encodings: string[];
      resolutions: Array<{ width: number; height: number }>;
      quality_range: [number, number];
      frame_rate_range: [number, number];
      bitrate_range_kbps: [number, number];
      gov_length_range: [number, number];
    };
  }>;
  imaging: {
    current: {
      brightness: number;
      contrast: number;
      color_saturation: number;
      sharpness: number;
      ir_cut_filter: string;
      wdr_mode: string;
      wdr_level: number;
      night_vision_type: string;
      mirror_flip: string;
      anti_flicker: string;
    };
    options: {
      brightness_range: [number, number];
      contrast_range: [number, number];
      color_saturation_range: [number, number];
      sharpness_range: [number, number];
      ir_cut_filter_modes: string[];
      wdr_supported: boolean;
      wdr_level_range: [number, number];
      night_vision_color_capable: boolean;
      night_vision_smart_capable: boolean;
    };
  };
  osd: Array<{
    token: string;
    video_source_token: string;
    osd_type: string;
    position: string;
    plain_text?: string;
    date_format: string;
    time_format: string;
  }>;
}

interface CameraHealthData {
  serial: string;
  online: boolean;
  uptime_seconds?: number;
  reboot_reason?: string;
  clock_sync_status: string;
  firmware_version: string;
  last_seen?: string;
}

type SettingsTab = "identity" | "encoders" | "imaging" | "osd" | "maintenance";

export const CameraSettingsView: React.FC<CameraSettingsViewProps> = ({ cameras, userRole }) => {
  const [selectedSerial, setSelectedSerial] = useState<string>(cameras[0]?.serial || "");
  const [activeTab, setActiveTab] = useState<SettingsTab>("identity");
  const [settings, setSettings] = useState<CameraSettingsData | null>(null);
  const [health, setHealth] = useState<CameraHealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; error?: boolean } | null>(null);

  // Form states
  const [identityForm, setIdentityForm] = useState({ name: "", location: "", timezone: "", password: "" });
  const [selectedEncoderIdx, setSelectedEncoderIdx] = useState<number>(0);
  const [encoderForm, setEncoderForm] = useState({
    encoding: "H265",
    resolution: "1920x1080",
    frameRate: 25,
    bitrate: 2048,
    quality: 50,
  });
  const [imagingForm, setImagingForm] = useState({
    brightness: 50,
    contrast: 50,
    saturation: 50,
    sharpness: 50,
    irCutFilter: "AUTO",
    wdrMode: "OFF",
    wdrLevel: 0,
    nightVisionType: "grey",
    mirrorFlip: "off",
    antiFlicker: "Auto",
  });
  const [osdForm, setOsdForm] = useState({
    timestampPos: "UpperLeft",
    textPos: "BottomRight",
    plainText: "",
  });

  // Modal dialog states
  const [showRebootModal, setShowRebootModal] = useState<boolean>(false);
  const [showResetModal, setShowResetModal] = useState<boolean>(false);
  const [resetMode, setResetMode] = useState<"Soft" | "Hard">("Soft");
  const [resetConfirmText, setResetConfirmText] = useState<string>("");
  const [showWdrWarning, setShowWdrWarning] = useState<boolean>(false);

  const isOperator = userRole === "owner" || userRole === "operator";

  useEffect(() => {
    if (cameras.length > 0 && !selectedSerial) {
      setSelectedSerial(cameras[0].serial);
    }
  }, [cameras, selectedSerial]);

  const loadSettings = async (serial: string) => {
    if (!serial) return;
    setLoading(true);
    setStatusMessage(null);
    try {
      const [settingsRes, healthRes] = await Promise.all([
        fetch(`/api/v1/cameras/${serial}/settings`),
        fetch(`/api/v1/cameras/${serial}/health`),
      ]);

      if (settingsRes.ok) {
        const data: CameraSettingsData = await settingsRes.json();
        setSettings(data);

        setIdentityForm({
          name: data.identity.name,
          location: data.identity.location,
          timezone: data.identity.timezone || "UTC",
          password: "",
        });

        if (data.encoders && data.encoders.length > 0) {
          const enc = data.encoders[0];
          setEncoderForm({
            encoding: enc.current.encoding,
            resolution: `${enc.current.width}x${enc.current.height}`,
            frameRate: enc.current.frame_rate_limit,
            bitrate: enc.current.bitrate_limit_kbps,
            quality: enc.current.quality,
          });
        }

        setImagingForm({
          brightness: data.imaging.current.brightness,
          contrast: data.imaging.current.contrast,
          saturation: data.imaging.current.color_saturation,
          sharpness: data.imaging.current.sharpness,
          irCutFilter: data.imaging.current.ir_cut_filter,
          wdrMode: data.imaging.current.wdr_mode,
          wdrLevel: data.imaging.current.wdr_level,
          nightVisionType: data.imaging.current.night_vision_type,
          mirrorFlip: data.imaging.current.mirror_flip,
          antiFlicker: data.imaging.current.anti_flicker,
        });

        const tsOsd = data.osd.find((o) => o.osd_type === "DateAndTime");
        const txtOsd = data.osd.find((o) => o.osd_type === "Plain");
        setOsdForm({
          timestampPos: tsOsd?.position || "UpperLeft",
          textPos: txtOsd?.position || "BottomRight",
          plainText: txtOsd?.plain_text || "",
        });
      }

      if (healthRes.ok) {
        const hData: CameraHealthData = await healthRes.json();
        setHealth(hData);
      }
    } catch {
      setStatusMessage({ text: "Failed to connect or fetch camera settings", error: true });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedSerial) {
      loadSettings(selectedSerial);
    }
  }, [selectedSerial]);

  const handleSaveIdentity = async () => {
    if (!isOperator) return;
    setStatusMessage(null);
    try {
      const payload: Record<string, string> = {};
      if (identityForm.name) payload.name = identityForm.name;
      if (identityForm.location) payload.location = identityForm.location;
      if (identityForm.timezone) payload.timezone = identityForm.timezone;
      if (identityForm.password) payload.password = identityForm.password;

      const res = await fetch(`/api/v1/cameras/${selectedSerial}/settings/identity`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setStatusMessage({ text: "Camera identity updated successfully" });
        loadSettings(selectedSerial);
      } else {
        const err = await res.json();
        setStatusMessage({ text: err.detail || "Failed to update identity", error: true });
      }
    } catch {
      setStatusMessage({ text: "Network error updating identity", error: true });
    }
  };

  const handleSaveEncoder = async () => {
    if (!isOperator || !settings?.encoders[selectedEncoderIdx]) return;
    setStatusMessage(null);
    const enc = settings.encoders[selectedEncoderIdx];
    const [w, h] = encoderForm.resolution.split("x").map(Number);

    try {
      const res = await fetch(`/api/v1/cameras/${selectedSerial}/settings/encoder`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          venc_token: enc.venc_token,
          encoding: encoderForm.encoding,
          width: w,
          height: h,
          frame_rate_limit: Number(encoderForm.frameRate),
          bitrate_limit_kbps: Number(encoderForm.bitrate),
          quality: Number(encoderForm.quality),
        }),
      });
      if (res.ok) {
        setStatusMessage({ text: `Encoder settings for ${enc.profile_name} saved` });
        loadSettings(selectedSerial);
      } else {
        const err = await res.json();
        setStatusMessage({ text: err.detail || "Failed to update encoder", error: true });
      }
    } catch {
      setStatusMessage({ text: "Network error updating encoder", error: true });
    }
  };

  const handleSaveImaging = async () => {
    if (!isOperator) return;
    setStatusMessage(null);
    try {
      const res = await fetch(`/api/v1/cameras/${selectedSerial}/settings/imaging`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          brightness: Number(imagingForm.brightness),
          contrast: Number(imagingForm.contrast),
          color_saturation: Number(imagingForm.saturation),
          sharpness: Number(imagingForm.sharpness),
          ir_cut_filter: imagingForm.irCutFilter,
          wdr_mode: imagingForm.wdrMode,
          wdr_level: Number(imagingForm.wdrLevel),
          night_vision_type: imagingForm.nightVisionType,
          mirror_flip: imagingForm.mirrorFlip,
          anti_flicker: imagingForm.antiFlicker,
        }),
      });
      if (res.ok) {
        setStatusMessage({ text: "Imaging and ISP parameters saved" });
        loadSettings(selectedSerial);
      } else {
        const err = await res.json();
        setStatusMessage({ text: err.detail || "Failed to update imaging", error: true });
      }
    } catch {
      setStatusMessage({ text: "Network error updating imaging", error: true });
    }
  };

  const handleSaveOsd = async () => {
    if (!isOperator || !settings) return;
    setStatusMessage(null);
    try {
      const txtOsd = settings.osd.find((o) => o.osd_type === "Plain") || {
        token: "OSD_Text",
        video_source_token: "VideoSource_1",
      };
      const tsOsd = settings.osd.find((o) => o.osd_type === "DateAndTime") || {
        token: "OSD_Time",
        video_source_token: "VideoSource_1",
      };

      await fetch(`/api/v1/cameras/${selectedSerial}/settings/osd`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: txtOsd.token,
          video_source_token: txtOsd.video_source_token,
          osd_type: "Plain",
          position: osdForm.textPos,
          plain_text: osdForm.plainText,
        }),
      });

      await fetch(`/api/v1/cameras/${selectedSerial}/settings/osd`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: tsOsd.token,
          video_source_token: tsOsd.video_source_token,
          osd_type: "DateAndTime",
          position: osdForm.timestampPos,
        }),
      });

      setStatusMessage({ text: "OSD overlays updated successfully" });
      loadSettings(selectedSerial);
    } catch {
      setStatusMessage({ text: "Network error updating OSD", error: true });
    }
  };

  const handleReboot = async () => {
    if (!isOperator) return;
    setShowRebootModal(false);
    setStatusMessage({ text: "Initiating camera reboot..." });
    try {
      const res = await fetch(`/api/v1/cameras/${selectedSerial}/reboot`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setStatusMessage({ text: data.message || "Reboot command received by camera" });
      } else {
        const err = await res.json();
        setStatusMessage({ text: err.detail || "Failed to reboot camera", error: true });
      }
    } catch {
      setStatusMessage({ text: "Network error executing reboot", error: true });
    }
  };

  const handleFactoryReset = async () => {
    if (!isOperator) return;
    if (resetConfirmText.trim().toUpperCase() !== "RESET") {
      setStatusMessage({ text: "Type 'RESET' to confirm factory reset", error: true });
      return;
    }
    setShowResetModal(false);
    setStatusMessage({ text: `Executing ${resetMode} factory reset...` });
    try {
      const res = await fetch(`/api/v1/cameras/${selectedSerial}/factory-reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: resetMode, confirmation: "RESET" }),
      });
      if (res.ok) {
        const data = await res.json();
        setStatusMessage({ text: data.message });
      } else {
        const err = await res.json();
        setStatusMessage({ text: err.detail || "Factory reset failed", error: true });
      }
    } catch {
      setStatusMessage({ text: "Network error executing factory reset", error: true });
    }
  };

  const formatUptime = (seconds?: number) => {
    if (!seconds) return "Unknown";
    const d = Math.floor(seconds / (3600 * 24));
    const h = Math.floor((seconds % (3600 * 24)) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${d > 0 ? `${d}d ` : ""}${h}h ${m}m ${s}s`;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#0f172a", color: "#f8fafc" }}>
      {/* Top Header & Camera Selector */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "16px 24px",
          background: "#1e293b",
          borderBottom: "1px solid #334155",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <h2 style={{ fontSize: "18px", margin: 0, fontWeight: "bold" }}>Camera Settings</h2>
          <select
            value={selectedSerial}
            onChange={(e) => setSelectedSerial(e.target.value)}
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "6px 12px",
              fontSize: "14px",
              cursor: "pointer",
            }}
          >
            {cameras.map((cam) => (
              <option key={cam.serial} value={cam.serial}>
                {cam.name || cam.serial}
              </option>
            ))}
          </select>
        </div>

        {/* Sub-tabs */}
        <nav style={{ display: "flex", gap: "8px" }}>
          {(["identity", "encoders", "imaging", "osd", "maintenance"] as SettingsTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                background: activeTab === tab ? "#0284c7" : "transparent",
                color: activeTab === tab ? "#ffffff" : "#94a3b8",
                border: "1px solid",
                borderColor: activeTab === tab ? "#0284c7" : "#475569",
                borderRadius: "4px",
                padding: "6px 14px",
                fontSize: "13px",
                fontWeight: 600,
                cursor: "pointer",
                textTransform: "capitalize",
              }}
            >
              {tab === "identity" ? "Identity & Info" : tab === "encoders" ? "Video Encoders" : tab === "osd" ? "OSD Overlays" : tab}
            </button>
          ))}
        </nav>
      </div>

      {/* Status banner */}
      {statusMessage && (
        <div
          style={{
            padding: "10px 24px",
            background: statusMessage.error ? "#7f1d1d" : "#065f46",
            color: "#ffffff",
            fontSize: "13px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{statusMessage.text}</span>
          <button
            onClick={() => setStatusMessage(null)}
            style={{ background: "transparent", border: "none", color: "#fff", cursor: "pointer" }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Settings Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px" }}>
        {loading && <div style={{ color: "#94a3b8", textAlign: "center", padding: "40px" }}>Loading camera settings...</div>}

        {!loading && settings && (
          <div style={{ maxWidth: "800px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "24px" }}>
            {/* TAB 1: IDENTITY & INFO */}
            {activeTab === "identity" && (
              <div style={{ background: "#1e293b", borderRadius: "8px", border: "1px solid #334155", padding: "24px" }}>
                <h3 style={{ margin: "0 0 16px 0", fontSize: "16px", color: "#38bdf8" }}>Device Identity & Credentials</h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "20px" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Camera Name</label>
                    <input
                      type="text"
                      disabled={!isOperator}
                      value={identityForm.name}
                      onChange={(e) => setIdentityForm({ ...identityForm, name: e.target.value })}
                      style={{ width: "100%", padding: "8px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Location Tag</label>
                    <input
                      type="text"
                      disabled={!isOperator}
                      value={identityForm.location}
                      onChange={(e) => setIdentityForm({ ...identityForm, location: e.target.value })}
                      style={{ width: "100%", padding: "8px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Timezone</label>
                    <select
                      disabled={!isOperator}
                      value={identityForm.timezone}
                      onChange={(e) => setIdentityForm({ ...identityForm, timezone: e.target.value })}
                      style={{ width: "100%", padding: "8px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                    >
                      {settings.identity.supported_timezones.map((tz) => (
                        <option key={tz.code} value={tz.code}>
                          {tz.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Change Camera Password</label>
                    <input
                      type="password"
                      disabled={!isOperator}
                      placeholder="Leave blank to keep unchanged"
                      value={identityForm.password}
                      onChange={(e) => setIdentityForm({ ...identityForm, password: e.target.value })}
                      style={{ width: "100%", padding: "8px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                    />
                  </div>
                </div>

                {isOperator && (
                  <button
                    onClick={handleSaveIdentity}
                    style={{ background: "#0284c7", color: "#fff", border: "none", borderRadius: "4px", padding: "8px 16px", cursor: "pointer", fontWeight: 600 }}
                  >
                    Save Identity
                  </button>
                )}

                <h3 style={{ margin: "32px 0 16px 0", fontSize: "16px", color: "#94a3b8" }}>Hardware & Build Information</h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", fontSize: "13px" }}>
                  <div><span style={{ color: "#64748b" }}>Model:</span> {settings.device_info.model}</div>
                  <div><span style={{ color: "#64748b" }}>Manufacturer:</span> {settings.device_info.manufacturer}</div>
                  <div><span style={{ color: "#64748b" }}>Firmware:</span> {settings.device_info.firmware_version}</div>
                  <div><span style={{ color: "#64748b" }}>Serial:</span> {settings.device_info.serial_number}</div>
                  <div><span style={{ color: "#64748b" }}>Hardware ID:</span> {settings.device_info.hardware_id}</div>
                </div>
              </div>
            )}

            {/* TAB 2: VIDEO ENCODERS */}
            {activeTab === "encoders" && (
              <div style={{ background: "#1e293b", borderRadius: "8px", border: "1px solid #334155", padding: "24px" }}>
                <div style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
                  {settings.encoders.map((enc, idx) => (
                    <button
                      key={enc.profile_token}
                      onClick={() => {
                        setSelectedEncoderIdx(idx);
                        setEncoderForm({
                          encoding: enc.current.encoding,
                          resolution: `${enc.current.width}x${enc.current.height}`,
                          frameRate: enc.current.frame_rate_limit,
                          bitrate: enc.current.bitrate_limit_kbps,
                          quality: enc.current.quality,
                        });
                      }}
                      style={{
                        background: selectedEncoderIdx === idx ? "#0f172a" : "transparent",
                        color: selectedEncoderIdx === idx ? "#38bdf8" : "#94a3b8",
                        border: "1px solid",
                        borderColor: selectedEncoderIdx === idx ? "#38bdf8" : "#475569",
                        borderRadius: "4px",
                        padding: "6px 12px",
                        cursor: "pointer",
                      }}
                    >
                      {enc.profile_name}
                    </button>
                  ))}
                </div>

                {settings.encoders[selectedEncoderIdx] && (() => {
                  const currentEnc = settings.encoders[selectedEncoderIdx];
                  const opts = currentEnc.options;
                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                      <div>
                        <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Video Codec</label>
                        <select
                          disabled={!isOperator}
                          value={encoderForm.encoding}
                          onChange={(e) => setEncoderForm({ ...encoderForm, encoding: e.target.value })}
                          style={{ width: "200px", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                        >
                          {opts.encodings.map((c) => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Resolution</label>
                        <select
                          disabled={!isOperator}
                          value={encoderForm.resolution}
                          onChange={(e) => setEncoderForm({ ...encoderForm, resolution: e.target.value })}
                          style={{ width: "200px", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                        >
                          {opts.resolutions.map((r) => (
                            <option key={`${r.width}x${r.height}`} value={`${r.width}x${r.height}`}>
                              {r.width} x {r.height}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>
                          Frame Rate (FPS): {encoderForm.frameRate} (Allowed: {opts.frame_rate_range[0]} - {opts.frame_rate_range[1]})
                        </label>
                        <input
                          type="range"
                          disabled={!isOperator}
                          min={opts.frame_rate_range[0]}
                          max={opts.frame_rate_range[1]}
                          value={encoderForm.frameRate}
                          onChange={(e) => setEncoderForm({ ...encoderForm, frameRate: Number(e.target.value) })}
                          style={{ width: "100%" }}
                        />
                      </div>

                      <div>
                        <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>
                          Bitrate Limit (kbps): {encoderForm.bitrate} (Allowed: {opts.bitrate_range_kbps[0]} - {opts.bitrate_range_kbps[1]})
                        </label>
                        <input
                          type="range"
                          disabled={!isOperator}
                          min={opts.bitrate_range_kbps[0]}
                          max={opts.bitrate_range_kbps[1]}
                          step={128}
                          value={encoderForm.bitrate}
                          onChange={(e) => setEncoderForm({ ...encoderForm, bitrate: Number(e.target.value) })}
                          style={{ width: "100%" }}
                        />
                      </div>

                      {isOperator && (
                        <button
                          onClick={handleSaveEncoder}
                          style={{ background: "#0284c7", color: "#fff", border: "none", borderRadius: "4px", padding: "8px 16px", cursor: "pointer", fontWeight: 600, width: "fit-content", marginTop: "10px" }}
                        >
                          Save Encoder Configuration
                        </button>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}

            {/* TAB 3: IMAGING & ISP */}
            {activeTab === "imaging" && (
              <div style={{ background: "#1e293b", borderRadius: "8px", border: "1px solid #334155", padding: "24px", display: "flex", flexDirection: "column", gap: "20px" }}>
                <h3 style={{ margin: 0, fontSize: "16px", color: "#38bdf8" }}>Day / Night & Night Vision</h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>IR Cut Filter (Day/Night Mode)</label>
                    <select
                      disabled={!isOperator}
                      value={imagingForm.irCutFilter}
                      onChange={(e) => setImagingForm({ ...imagingForm, irCutFilter: e.target.value })}
                      style={{ width: "100%", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                    >
                      {settings.imaging.options.ir_cut_filter_modes.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Night Vision Type</label>
                    <select
                      disabled={!isOperator}
                      value={imagingForm.nightVisionType}
                      onChange={(e) => setImagingForm({ ...imagingForm, nightVisionType: e.target.value })}
                      style={{ width: "100%", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                    >
                      <option value="grey">Grey (Standard IR)</option>
                      <option value="color" disabled={!settings.imaging.options.night_vision_color_capable}>
                        Color {!settings.imaging.options.night_vision_color_capable ? "(Unsupported)" : ""}
                      </option>
                      <option value="smart" disabled={!settings.imaging.options.night_vision_smart_capable}>
                        Smart {!settings.imaging.options.night_vision_smart_capable ? "(Unsupported)" : ""}
                      </option>
                    </select>
                  </div>
                </div>

                <h3 style={{ margin: "16px 0 0 0", fontSize: "16px", color: "#38bdf8" }}>Wide Dynamic Range (WDR)</h3>
                {settings.imaging.options.wdr_supported ? (
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
                      <label style={{ fontSize: "14px" }}>Enable WDR:</label>
                      <input
                        type="checkbox"
                        disabled={!isOperator}
                        checked={imagingForm.wdrMode === "ON"}
                        onChange={(e) => {
                          const next = e.target.checked ? "ON" : "OFF";
                          setImagingForm({ ...imagingForm, wdrMode: next });
                          setShowWdrWarning(true);
                        }}
                      />
                    </div>
                    {showWdrWarning && (
                      <div style={{ background: "#854d0e", color: "#fef08a", padding: "8px 12px", borderRadius: "4px", fontSize: "12px", marginBottom: "12px" }}>
                        ⚠️ Toggling WDR changes sensor readout mode and may trigger a brief camera reboot.
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ color: "#64748b", fontSize: "13px" }}>WDR is not supported on this camera model or build.</div>
                )}

                <h3 style={{ margin: "16px 0 0 0", fontSize: "16px", color: "#38bdf8" }}>Image Signal Processing (ISP)</h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                  <div>
                    <label style={{ fontSize: "12px", color: "#94a3b8" }}>Brightness: {imagingForm.brightness}</label>
                    <input
                      type="range"
                      disabled={!isOperator}
                      min={settings.imaging.options.brightness_range[0]}
                      max={settings.imaging.options.brightness_range[1]}
                      value={imagingForm.brightness}
                      onChange={(e) => setImagingForm({ ...imagingForm, brightness: Number(e.target.value) })}
                      style={{ width: "100%" }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "12px", color: "#94a3b8" }}>Contrast: {imagingForm.contrast}</label>
                    <input
                      type="range"
                      disabled={!isOperator}
                      min={settings.imaging.options.contrast_range[0]}
                      max={settings.imaging.options.contrast_range[1]}
                      value={imagingForm.contrast}
                      onChange={(e) => setImagingForm({ ...imagingForm, contrast: Number(e.target.value) })}
                      style={{ width: "100%" }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "12px", color: "#94a3b8" }}>Saturation: {imagingForm.saturation}</label>
                    <input
                      type="range"
                      disabled={!isOperator}
                      min={settings.imaging.options.color_saturation_range[0]}
                      max={settings.imaging.options.color_saturation_range[1]}
                      value={imagingForm.saturation}
                      onChange={(e) => setImagingForm({ ...imagingForm, saturation: Number(e.target.value) })}
                      style={{ width: "100%" }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "12px", color: "#94a3b8" }}>Sharpness: {imagingForm.sharpness}</label>
                    <input
                      type="range"
                      disabled={!isOperator}
                      min={settings.imaging.options.sharpness_range[0]}
                      max={settings.imaging.options.sharpness_range[1]}
                      value={imagingForm.sharpness}
                      onChange={(e) => setImagingForm({ ...imagingForm, sharpness: Number(e.target.value) })}
                      style={{ width: "100%" }}
                    />
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginTop: "10px" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Mirror / Flip</label>
                    <select
                      disabled={!isOperator}
                      value={imagingForm.mirrorFlip}
                      onChange={(e) => setImagingForm({ ...imagingForm, mirrorFlip: e.target.value })}
                      style={{ width: "100%", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                    >
                      <option value="off">Normal</option>
                      <option value="mirror">Mirror (Horizontal)</option>
                      <option value="flip">Flip (Vertical)</option>
                      <option value="both">Both (180° Rotate)</option>
                    </select>
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Anti-Flicker (Mains Frequency)</label>
                    <select
                      disabled={!isOperator}
                      value={imagingForm.antiFlicker}
                      onChange={(e) => setImagingForm({ ...imagingForm, antiFlicker: e.target.value })}
                      style={{ width: "100%", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                    >
                      <option value="Auto">Auto</option>
                      <option value="50Hz">50Hz (EU / Asia)</option>
                      <option value="60Hz">60Hz (US)</option>
                    </select>
                  </div>
                </div>

                {isOperator && (
                  <button
                    onClick={handleSaveImaging}
                    style={{ background: "#0284c7", color: "#fff", border: "none", borderRadius: "4px", padding: "8px 16px", cursor: "pointer", fontWeight: 600, width: "fit-content", marginTop: "10px" }}
                  >
                    Save Imaging Settings
                  </button>
                )}
              </div>
            )}

            {/* TAB 4: OSD OVERLAYS */}
            {activeTab === "osd" && (
              <div style={{ background: "#1e293b", borderRadius: "8px", border: "1px solid #334155", padding: "24px", display: "flex", flexDirection: "column", gap: "20px" }}>
                <h3 style={{ margin: 0, fontSize: "16px", color: "#38bdf8" }}>On-Screen Display Overlays</h3>
                <div>
                  <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Timestamp Position</label>
                  <select
                    disabled={!isOperator}
                    value={osdForm.timestampPos}
                    onChange={(e) => setOsdForm({ ...osdForm, timestampPos: e.target.value })}
                    style={{ width: "200px", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                  >
                    <option value="UpperLeft">Top Left</option>
                    <option value="UpperRight">Top Right</option>
                    <option value="BottomLeft">Bottom Left</option>
                    <option value="BottomRight">Bottom Right</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Custom Camera Label</label>
                  <input
                    type="text"
                    disabled={!isOperator}
                    value={osdForm.plainText}
                    onChange={(e) => setOsdForm({ ...osdForm, plainText: e.target.value })}
                    placeholder="Enter display label"
                    style={{ width: "300px", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>Label Position</label>
                  <select
                    disabled={!isOperator}
                    value={osdForm.textPos}
                    onChange={(e) => setOsdForm({ ...osdForm, textPos: e.target.value })}
                    style={{ width: "200px", padding: "6px", background: "#0f172a", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }}
                  >
                    <option value="UpperLeft">Top Left</option>
                    <option value="UpperRight">Top Right</option>
                    <option value="BottomLeft">Bottom Left</option>
                    <option value="BottomRight">Bottom Right</option>
                  </select>
                </div>

                {isOperator && (
                  <button
                    onClick={handleSaveOsd}
                    style={{ background: "#0284c7", color: "#fff", border: "none", borderRadius: "4px", padding: "8px 16px", cursor: "pointer", fontWeight: 600, width: "fit-content", marginTop: "10px" }}
                  >
                    Save OSD Overlays
                  </button>
                )}
              </div>
            )}

            {/* TAB 5: MAINTENANCE & HEALTH */}
            {activeTab === "maintenance" && (
              <div style={{ background: "#1e293b", borderRadius: "8px", border: "1px solid #334155", padding: "24px", display: "flex", flexDirection: "column", gap: "24px" }}>
                <h3 style={{ margin: 0, fontSize: "16px", color: "#38bdf8" }}>Camera Health & Status</h3>
                {health && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", fontSize: "13px" }}>
                    <div>
                      <span style={{ color: "#64748b" }}>Status: </span>
                      <span style={{ color: health.online ? "#4ade80" : "#f87171", fontWeight: 600 }}>
                        {health.online ? "Online" : "Unreachable"}
                      </span>
                    </div>
                    <div>
                      <span style={{ color: "#64748b" }}>Uptime: </span>
                      <span>{formatUptime(health.uptime_seconds)}</span>
                    </div>
                    <div>
                      <span style={{ color: "#64748b" }}>Clock Sync: </span>
                      <span style={{ color: health.clock_sync_status === "synced" ? "#4ade80" : "#fbbf24" }}>
                        {health.clock_sync_status}
                      </span>
                    </div>
                    <div>
                      <span style={{ color: "#64748b" }}>Last Reboot Reason: </span>
                      <span>{health.reboot_reason || "Normal Startup"}</span>
                    </div>
                  </div>
                )}

                <h3 style={{ margin: "16px 0 0 0", fontSize: "16px", color: "#ef4444" }}>Device Management</h3>
                <div style={{ display: "flex", gap: "16px" }}>
                  <button
                    disabled={!isOperator}
                    onClick={() => setShowRebootModal(true)}
                    style={{
                      background: "#334155",
                      color: "#fff",
                      border: "1px solid #475569",
                      borderRadius: "4px",
                      padding: "8px 16px",
                      cursor: isOperator ? "pointer" : "not-allowed",
                      fontWeight: 600,
                    }}
                  >
                    Reboot Camera
                  </button>
                  <button
                    disabled={!isOperator}
                    onClick={() => {
                      setResetConfirmText("");
                      setShowResetModal(true);
                    }}
                    style={{
                      background: "#dc2626",
                      color: "#fff",
                      border: "none",
                      borderRadius: "4px",
                      padding: "8px 16px",
                      cursor: isOperator ? "pointer" : "not-allowed",
                      fontWeight: 600,
                    }}
                  >
                    Factory Reset
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* REBOOT CONFIRMATION MODAL */}
      {showRebootModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div style={{ background: "#1e293b", padding: "24px", borderRadius: "8px", maxWidth: "400px", width: "90%", border: "1px solid #334155" }}>
            <h3 style={{ margin: "0 0 12px 0", color: "#f8fafc" }}>Reboot Camera?</h3>
            <p style={{ color: "#94a3b8", fontSize: "13px", lineHeight: "1.5", margin: "0 0 20px 0" }}>
              The camera will restart immediately. Video streaming and recording will be briefly interrupted for ~10 to 30 seconds.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button
                onClick={() => setShowRebootModal(false)}
                style={{ background: "transparent", color: "#cbd5e1", border: "1px solid #475569", borderRadius: "4px", padding: "6px 12px", cursor: "pointer" }}
              >
                Cancel
              </button>
              <button
                onClick={handleReboot}
                style={{ background: "#0284c7", color: "#fff", border: "none", borderRadius: "4px", padding: "6px 14px", cursor: "pointer", fontWeight: 600 }}
              >
                Confirm Reboot
              </button>
            </div>
          </div>
        </div>
      )}

      {/* FACTORY RESET DOUBLE CONFIRMATION MODAL */}
      {showResetModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div style={{ background: "#1e293b", padding: "24px", borderRadius: "8px", maxWidth: "460px", width: "90%", border: "1px solid #dc2626" }}>
            <h3 style={{ margin: "0 0 12px 0", color: "#ef4444" }}>⚠️ Warning: Camera Factory Reset</h3>
            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", fontSize: "12px", color: "#cbd5e1", marginBottom: "6px" }}>Select Reset Mode:</label>
              <div style={{ display: "flex", gap: "16px" }}>
                <label style={{ fontSize: "13px", display: "flex", alignItems: "center", gap: "6px" }}>
                  <input
                    type="radio"
                    name="resetMode"
                    value="Soft"
                    checked={resetMode === "Soft"}
                    onChange={() => setResetMode("Soft")}
                  />
                  Soft Reset (Keep Network)
                </label>
                <label style={{ fontSize: "13px", display: "flex", alignItems: "center", gap: "6px" }}>
                  <input
                    type="radio"
                    name="resetMode"
                    value="Hard"
                    checked={resetMode === "Hard"}
                    onChange={() => setResetMode("Hard")}
                  />
                  Hard Reset (Erase All)
                </label>
              </div>
            </div>

            <p style={{ color: "#94a3b8", fontSize: "12px", lineHeight: "1.5", margin: "0 0 16px 0" }}>
              {resetMode === "Soft"
                ? "Soft reset resets ISP, OSD, and camera preferences to factory defaults. Network configuration will be preserved."
                : "Hard reset wipes all configuration including WiFi/network credentials. The camera will re-enter AP provisioning mode."}
            </p>

            <div style={{ marginBottom: "20px" }}>
              <label style={{ display: "block", fontSize: "12px", color: "#ef4444", marginBottom: "4px" }}>
                Type <strong>RESET</strong> to confirm:
              </label>
              <input
                type="text"
                value={resetConfirmText}
                onChange={(e) => setResetConfirmText(e.target.value)}
                placeholder="RESET"
                style={{ width: "100%", padding: "8px", background: "#0f172a", border: "1px solid #dc2626", borderRadius: "4px", color: "#fff" }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button
                onClick={() => setShowResetModal(false)}
                style={{ background: "transparent", color: "#cbd5e1", border: "1px solid #475569", borderRadius: "4px", padding: "6px 12px", cursor: "pointer" }}
              >
                Cancel
              </button>
              <button
                onClick={handleFactoryReset}
                disabled={resetConfirmText.trim().toUpperCase() !== "RESET"}
                style={{
                  background: resetConfirmText.trim().toUpperCase() === "RESET" ? "#dc2626" : "#475569",
                  color: "#fff",
                  border: "none",
                  borderRadius: "4px",
                  padding: "6px 14px",
                  cursor: resetConfirmText.trim().toUpperCase() === "RESET" ? "pointer" : "not-allowed",
                  fontWeight: 600,
                }}
              >
                Execute Factory Reset
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default CameraSettingsView;
