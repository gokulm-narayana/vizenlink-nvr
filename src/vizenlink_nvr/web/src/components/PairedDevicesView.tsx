import React, { useEffect, useState } from "react";
import { MobilePairingModal } from "./MobilePairingModal";

export interface PairedDevice {
  id: string;
  device_id: string;
  device_name: string;
  platform: string;
  user_id: number;
  username?: string;
  paired_at: string;
  last_seen_at: string;
  is_revoked: boolean;
  revoked_at?: string;
}

interface PairedDevicesViewProps {
  userRole?: string;
}

export const PairedDevicesView: React.FC<PairedDevicesViewProps> = () => {
  const [devices, setDevices] = useState<PairedDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPairModalOpen, setIsPairModalOpen] = useState(false);
  const [revokingDevice, setRevokingDevice] = useState<PairedDevice | null>(null);
  const [actionInProgress, setActionInProgress] = useState(false);

  const fetchDevices = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/mobile/devices");
      if (!res.ok) {
        throw new Error(`Failed to load paired devices: ${res.statusText}`);
      }
      const json: PairedDevice[] = await res.json();
      setDevices(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load devices");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  const handleRevoke = async () => {
    if (!revokingDevice) return;
    setActionInProgress(true);
    try {
      const res = await fetch(`/api/v1/mobile/devices/${revokingDevice.id}/revoke`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error(`Failed to revoke device: ${res.statusText}`);
      }
      setRevokingDevice(null);
      await fetchDevices();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to revoke device");
    } finally {
      setActionInProgress(false);
    }
  };

  const formatDate = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto", color: "#f8fafc" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "24px",
          borderBottom: "1px solid #334155",
          paddingBottom: "16px",
        }}
      >
        <div>
          <h1 style={{ fontSize: "22px", fontWeight: "bold", margin: "0 0 6px 0", color: "#38bdf8" }}>
            Paired Mobile Devices
          </h1>
          <p style={{ margin: 0, fontSize: "14px", color: "#94a3b8" }}>
            Manage authorized mobile apps connecting to this NVR over the local network.
          </p>
        </div>
        <div style={{ display: "flex", gap: "12px" }}>
          <button
            onClick={fetchDevices}
            style={{
              background: "#334155",
              color: "#cbd5e1",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "8px 14px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Refresh
          </button>
          <button
            onClick={() => setIsPairModalOpen(true)}
            style={{
              background: "#0284c7",
              color: "#ffffff",
              border: "none",
              borderRadius: "4px",
              padding: "8px 16px",
              fontWeight: 600,
              cursor: "pointer",
              boxShadow: "0 2px 4px rgba(0, 0, 0, 0.2)",
            }}
          >
            + Pair New Device
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "40px", color: "#94a3b8" }}>
          Loading registered mobile devices...
        </div>
      ) : error ? (
        <div
          style={{
            background: "#450a0a",
            border: "1px solid #991b1b",
            color: "#fca5a5",
            padding: "16px",
            borderRadius: "6px",
            marginBottom: "20px",
          }}
        >
          {error}
        </div>
      ) : devices.length === 0 ? (
        <div
          style={{
            background: "#1e293b",
            border: "1px dashed #475569",
            borderRadius: "8px",
            padding: "48px 24px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "40px", marginBottom: "12px" }}>📱</div>
          <h3 style={{ fontSize: "18px", color: "#f8fafc", margin: "0 0 8px 0" }}>No Mobile Devices Paired</h3>
          <p style={{ color: "#94a3b8", fontSize: "14px", maxWidth: "440px", margin: "0 auto 20px auto" }}>
            Pair your iOS or Android device running the VizenLink mobile app to watch live feeds, browse recorded history, and monitor recorder health.
          </p>
          <button
            onClick={() => setIsPairModalOpen(true)}
            style={{
              background: "#0284c7",
              color: "#ffffff",
              border: "none",
              borderRadius: "4px",
              padding: "8px 18px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Pair Your First Device
          </button>
        </div>
      ) : (
        <div
          style={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: "8px",
            overflow: "hidden",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "14px" }}>
            <thead>
              <tr style={{ background: "#0f172a", borderBottom: "1px solid #334155", color: "#94a3b8" }}>
                <th style={{ padding: "12px 16px" }}>Device</th>
                <th style={{ padding: "12px 16px" }}>Platform</th>
                <th style={{ padding: "12px 16px" }}>Account</th>
                <th style={{ padding: "12px 16px" }}>Paired Date</th>
                <th style={{ padding: "12px 16px" }}>Last Active</th>
                <th style={{ padding: "12px 16px" }}>Status</th>
                <th style={{ padding: "12px 16px", textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((device) => (
                <tr
                  key={device.id}
                  style={{
                    borderBottom: "1px solid #334155",
                    opacity: device.is_revoked ? 0.6 : 1,
                  }}
                >
                  <td style={{ padding: "12px 16px", fontWeight: 600 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span>{device.platform.toLowerCase() === "ios" ? "🍏" : "🤖"}</span>
                      <span>{device.device_name}</span>
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span
                      style={{
                        background: "#334155",
                        color: "#cbd5e1",
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "12px",
                        fontWeight: 600,
                        textTransform: "uppercase",
                      }}
                    >
                      {device.platform}
                    </span>
                  </td>
                  <td style={{ padding: "12px 16px", color: "#cbd5e1" }}>
                    {device.username || `User #${device.user_id}`}
                  </td>
                  <td style={{ padding: "12px 16px", color: "#94a3b8" }}>{formatDate(device.paired_at)}</td>
                  <td style={{ padding: "12px 16px", color: "#94a3b8" }}>{formatDate(device.last_seen_at)}</td>
                  <td style={{ padding: "12px 16px" }}>
                    {device.is_revoked ? (
                      <span
                        style={{
                          background: "#7f1d1d",
                          color: "#fca5a5",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: 600,
                        }}
                      >
                        Revoked
                      </span>
                    ) : (
                      <span
                        style={{
                          background: "#14532d",
                          color: "#86efac",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: 600,
                        }}
                      >
                        Active
                      </span>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px", textAlign: "right" }}>
                    {!device.is_revoked ? (
                      <button
                        onClick={() => setRevokingDevice(device)}
                        style={{
                          background: "transparent",
                          color: "#ef4444",
                          border: "1px solid #dc2626",
                          borderRadius: "4px",
                          padding: "4px 10px",
                          fontSize: "12px",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Revoke Access
                      </button>
                    ) : (
                      <span style={{ fontSize: "12px", color: "#64748b" }}>Access Disabled</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* QR Pairing Modal */}
      <MobilePairingModal
        isOpen={isPairModalOpen}
        onClose={() => {
          setIsPairModalOpen(false);
          fetchDevices();
        }}
      />

      {/* Confirmation Modal for Revocation */}
      {revokingDevice && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(0, 0, 0, 0.75)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "20px",
          }}
        >
          <div
            style={{
              background: "#1e293b",
              border: "1px solid #dc2626",
              borderRadius: "8px",
              width: "100%",
              maxWidth: "440px",
              padding: "24px",
              color: "#f8fafc",
            }}
          >
            <h3 style={{ margin: "0 0 12px 0", color: "#ef4444", fontSize: "18px" }}>
              Revoke Mobile Device Access
            </h3>
            <p style={{ margin: "0 0 20px 0", fontSize: "14px", color: "#cbd5e1", lineHeight: "1.5" }}>
              Are you sure you want to revoke access for <strong>{revokingDevice.device_name}</strong>?
              The device will be immediately disconnected and its tokens permanently invalidated.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button
                onClick={() => setRevokingDevice(null)}
                disabled={actionInProgress}
                style={{
                  background: "transparent",
                  color: "#cbd5e1",
                  border: "1px solid #475569",
                  borderRadius: "4px",
                  padding: "6px 14px",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleRevoke}
                disabled={actionInProgress}
                style={{
                  background: "#dc2626",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "4px",
                  padding: "6px 14px",
                  fontWeight: 600,
                  cursor: actionInProgress ? "not-allowed" : "pointer",
                }}
              >
                {actionInProgress ? "Revoking..." : "Confirm Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
