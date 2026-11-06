import React, { useEffect, useState } from "react";
import type { ViewMode } from "@/lib/types";
import { OutageHistoryModal } from "./OutageHistoryModal";

interface HealthData {
  status: string;
  db_ok: boolean;
  mediamtx_ok: boolean;
  storage_ok: boolean;
  total_cameras: number;
  active_cameras: number;
  details: Record<string, any>;
}

interface StorageData {
  storage_path: string;
  allow_system_disk: boolean;
  reserve_bytes: number;
  health_state: string;
  health_reason?: string | null;
  telemetry?: {
    total_bytes: number;
    used_bytes: number;
    free_bytes: number;
    reserve_bytes: number;
  } | null;
  estimated_retention_days?: number | null;
}

interface DashboardProps {
  viewMode: ViewMode;
  recordingCount: number;
}

export const Dashboard: React.FC<DashboardProps> = ({ viewMode, recordingCount }) => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [storage, setStorage] = useState<StorageData | null>(null);
  const [outageModalOpen, setOutageModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [hRes, sRes] = await Promise.all([
        fetch("/api/v1/health"),
        fetch("/api/v1/storage/status"),
      ]);
      if (hRes.ok) setHealth(await hRes.json());
      if (sRes.ok) setStorage(await sRes.json());
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  };

  const toGiB = (bytes?: number | null) => {
    if (!bytes) return "0.0";
    return (bytes / (1024 * 1024 * 1024)).toFixed(1);
  };

  if (loading) {
    return <div style={{ padding: "40px", textAlign: "center" }}>Loading system health telemetry...</div>;
  }

  const freeBytes = storage?.telemetry?.free_bytes || 0;
  const totalBytes = storage?.telemetry?.total_bytes || 1;
  const usedBytes = storage?.telemetry?.used_bytes || 0;
  const usedPercent = Math.min(100, Math.round((usedBytes / totalBytes) * 100));

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <h2 style={{ margin: "0 0 6px 0", fontSize: "22px" }}>System Health & Diagnostics</h2>
          <span style={{ color: "#94a3b8", fontSize: "14px" }}>
            Operational telemetry ({viewMode === "advanced" ? "Advanced Diagnostic Mode" : "Simplified View"})
          </span>
        </div>

        <button
          onClick={() => setOutageModalOpen(true)}
          style={{
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            padding: "8px 16px",
            cursor: "pointer",
            fontWeight: "bold",
            fontSize: "13px",
          }}
        >
          View Camera Outage History
        </button>
      </div>

      {/* Top Metric Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "16px", marginBottom: "24px" }}>
        {/* Status Card */}
        <div style={{ background: "#1e293b", padding: "16px", borderRadius: "8px", borderLeft: `4px solid ${health?.status === "healthy" ? "#10b981" : "#ef4444"}` }}>
          <div style={{ color: "#94a3b8", fontSize: "12px", textTransform: "uppercase", marginBottom: "4px" }}>Recorder Status</div>
          <div style={{ fontSize: "24px", fontWeight: "bold", textTransform: "capitalize", color: health?.status === "healthy" ? "#10b981" : "#ef4444" }}>
            {health?.status || "Unknown"}
          </div>
        </div>

        {/* Cameras Card */}
        <div style={{ background: "#1e293b", padding: "16px", borderRadius: "8px" }}>
          <div style={{ color: "#94a3b8", fontSize: "12px", textTransform: "uppercase", marginBottom: "4px" }}>Cameras Online</div>
          <div style={{ fontSize: "24px", fontWeight: "bold" }}>
            {health?.active_cameras || 0} / {health?.total_cameras || 0}
          </div>
        </div>

        {/* Recording Card */}
        <div style={{ background: "#1e293b", padding: "16px", borderRadius: "8px" }}>
          <div style={{ color: "#94a3b8", fontSize: "12px", textTransform: "uppercase", marginBottom: "4px" }}>Active Recordings</div>
          <div style={{ fontSize: "24px", fontWeight: "bold", color: "#38bdf8" }}>
            {recordingCount}
          </div>
        </div>

        {/* Retention Estimate */}
        <div style={{ background: "#1e293b", padding: "16px", borderRadius: "8px" }}>
          <div style={{ color: "#94a3b8", fontSize: "12px", textTransform: "uppercase", marginBottom: "4px" }}>Est. Retention Days</div>
          <div style={{ fontSize: "24px", fontWeight: "bold" }}>
            {storage?.estimated_retention_days ? `${storage.estimated_retention_days.toFixed(1)} Days` : "Calculating..."}
          </div>
        </div>
      </div>

      {/* Storage Disk Capacity Section */}
      <div style={{ background: "#1e293b", padding: "20px", borderRadius: "8px", marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 12px 0", fontSize: "16px" }}>Recording Volume Capacity</h3>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", color: "#94a3b8", marginBottom: "6px" }}>
          <span>Used: {toGiB(usedBytes)} GiB ({usedPercent}%)</span>
          <span>Free: {toGiB(freeBytes)} GiB / {toGiB(totalBytes)} GiB</span>
        </div>

        {/* Progress Bar */}
        <div style={{ height: "12px", background: "#0f172a", borderRadius: "6px", overflow: "hidden" }}>
          <div
            style={{
              height: "100%",
              width: `${usedPercent}%`,
              background: usedPercent > 85 ? "#ef4444" : "#2563eb",
              transition: "width 0.3s ease",
            }}
          />
        </div>
      </div>

      {/* Advanced Diagnostics Telemetry (AUTH-06: revealed only in Advanced mode) */}
      {viewMode === "advanced" && (
        <div style={{ background: "#1e293b", padding: "20px", borderRadius: "8px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "16px", color: "#a5b4fc" }}>Advanced Technical Diagnostics</h3>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", fontSize: "13px" }}>
            <div>
              <span style={{ color: "#94a3b8" }}>Storage Path:</span> <code>{storage?.storage_path}</code>
            </div>
            <div>
              <span style={{ color: "#94a3b8" }}>Reserve Bytes:</span> <code>{toGiB(storage?.reserve_bytes)} GiB ({storage?.reserve_bytes} B)</code>
            </div>
            <div>
              <span style={{ color: "#94a3b8" }}>Storage Health State:</span> <code>{storage?.health_state}</code>
            </div>
            <div>
              <span style={{ color: "#94a3b8" }}>Database Probe:</span> <code>{health?.db_ok ? "Connected (OK)" : "Failed"}</code>
            </div>
            <div>
              <span style={{ color: "#94a3b8" }}>MediaMTX Stream Engine:</span> <code>{health?.mediamtx_ok ? "Running (127.0.0.1:9997)" : "Unreachable"}</code>
            </div>
            <div>
              <span style={{ color: "#94a3b8" }}>Watchdog Gap Count:</span> <code>{health?.details?.gap_count ?? 0} Gaps</code>
            </div>
          </div>
        </div>
      )}

      <OutageHistoryModal isOpen={outageModalOpen} onClose={() => setOutageModalOpen(false)} />
    </div>
  );
};
