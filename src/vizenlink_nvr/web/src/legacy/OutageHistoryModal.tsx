import React, { useEffect, useState } from "react";

interface OutageRecord {
  id: number;
  camera_serial: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  reason: string | null;
}

interface OutageHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const OutageHistoryModal: React.FC<OutageHistoryModalProps> = ({ isOpen, onClose }) => {
  const [outages, setOutages] = useState<OutageRecord[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadOutages();
    }
  }, [isOpen]);

  const loadOutages = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/health/outages?limit=50");
      if (res.ok) {
        const data = await res.json();
        setOutages(data);
      }
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (seconds === null) return "Ongoing";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.75)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: "#1e293b",
          width: "720px",
          maxHeight: "80vh",
          borderRadius: "8px",
          padding: "20px",
          display: "flex",
          flexDirection: "column",
          color: "#f8fafc",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h2 style={{ margin: 0, fontSize: "18px" }}>Camera Outage History</h2>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "#94a3b8",
              fontSize: "18px",
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        <div style={{ flex: 1, overflowY: "auto" }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: "20px" }}>Loading outage records...</div>
          ) : outages.length === 0 ? (
            <div style={{ textAlign: "center", padding: "20px", color: "#94a3b8" }}>No outage events recorded.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #334155", textAlign: "left", color: "#94a3b8" }}>
                  <th style={{ padding: "8px" }}>Camera</th>
                  <th style={{ padding: "8px" }}>Disconnected</th>
                  <th style={{ padding: "8px" }}>Reconnected</th>
                  <th style={{ padding: "8px" }}>Duration</th>
                  <th style={{ padding: "8px" }}>Reason</th>
                </tr>
              </thead>
              <tbody>
                {outages.map((o) => (
                  <tr key={o.id} style={{ borderBottom: "1px solid #1e293b" }}>
                    <td style={{ padding: "8px", fontWeight: "bold" }}>{o.camera_serial}</td>
                    <td style={{ padding: "8px" }}>{new Date(o.started_at).toLocaleTimeString()}</td>
                    <td style={{ padding: "8px" }}>
                      {o.ended_at ? new Date(o.ended_at).toLocaleTimeString() : <span style={{ color: "#ef4444" }}>Still Offline</span>}
                    </td>
                    <td style={{ padding: "8px" }}>{formatDuration(o.duration_seconds)}</td>
                    <td style={{ padding: "8px", color: "#94a3b8" }}>{o.reason || "Unknown"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

