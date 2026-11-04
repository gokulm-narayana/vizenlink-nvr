import React, { useState, useEffect } from "react";

interface ClipExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  cameraSerial: string;
  cameraName?: string;
  initialStartTime?: Date | null;
  initialEndTime?: Date | null;
  onExportSuccess?: (item: any) => void;
  onNavigateToGallery?: () => void;
}

function toLocalDatetimeInput(d: Date): string {
  const pad = (n: number) => n.toString().padStart(2, "0");
  const year = d.getFullYear();
  const month = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const hours = pad(d.getHours());
  const minutes = pad(d.getMinutes());
  const seconds = pad(d.getSeconds());
  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
}

export const ClipExportModal: React.FC<ClipExportModalProps> = ({
  isOpen,
  onClose,
  cameraSerial,
  cameraName,
  initialStartTime,
  initialEndTime,
  onExportSuccess,
  onNavigateToGallery,
}) => {
  const [startTimeStr, setStartTimeStr] = useState<string>("");
  const [endTimeStr, setEndTimeStr] = useState<string>("");
  const [title, setTitle] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportedItem, setExportedItem] = useState<any | null>(null);

  useEffect(() => {
    if (isOpen) {
      const now = new Date();
      const s = initialStartTime || new Date(now.getTime() - 60000);
      const e = initialEndTime || now;
      setStartTimeStr(toLocalDatetimeInput(s));
      setEndTimeStr(toLocalDatetimeInput(e));
      setTitle(`Clip ${cameraName || cameraSerial} ${s.toLocaleTimeString([], { hour12: false })}`);
      setError(null);
      setExportedItem(null);
    }
  }, [isOpen, cameraSerial, cameraName, initialStartTime, initialEndTime]);

  if (!isOpen) return null;

  const startDate = startTimeStr ? new Date(startTimeStr) : null;
  const endDate = endTimeStr ? new Date(endTimeStr) : null;
  const durationSec =
    startDate && endDate && endDate > startDate ? Math.round((endDate.getTime() - startDate.getTime()) / 1000) : 0;

  const handleExport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!startDate || !endDate || endDate <= startDate) {
      setError("End time must be after start time");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/v1/playback/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          camera_serial: cameraSerial,
          start_time: startDate.toISOString(),
          end_time: endDate.toISOString(),
          title: title.trim() || undefined,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const item = await res.json();
      setExportedItem(item);
      if (onExportSuccess) onExportSuccess(item);
    } catch (err: any) {
      setError(err.message || "Failed to export clip");
    } finally {
      setLoading(false);
    }
  };

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
      onClick={onClose}
    >
      <div
        style={{
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: "8px",
          width: "480px",
          maxWidth: "90%",
          padding: "24px",
          color: "#f8fafc",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h2 style={{ margin: 0, fontSize: "18px", fontWeight: "bold", color: "#38bdf8" }}>
            ✂️ Export Video Clip
          </h2>
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

        {error && (
          <div
            style={{
              background: "#fee2e2",
              color: "#b91c1c",
              padding: "10px",
              borderRadius: "6px",
              marginBottom: "16px",
              fontSize: "13px",
            }}
          >
            {error}
          </div>
        )}

        {exportedItem ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div
              style={{
                background: "#065f46",
                color: "#34d399",
                padding: "12px",
                borderRadius: "6px",
                fontSize: "14px",
                fontWeight: 600,
              }}
            >
              ✓ Clip successfully exported and stored in gallery!
            </div>

            <div style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: "1.6" }}>
              <div><strong>Title:</strong> {exportedItem.title}</div>
              <div><strong>File size:</strong> {(exportedItem.file_size_bytes / 1024 / 1024).toFixed(2)} MB</div>
              <div><strong>Duration:</strong> {Math.round(exportedItem.duration_seconds || durationSec)} seconds</div>
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
              <a
                href={`/api/v1/gallery/${exportedItem.id}/download`}
                download
                style={{
                  flex: 1,
                  background: "#0284c7",
                  color: "#ffffff",
                  textAlign: "center",
                  padding: "10px",
                  borderRadius: "6px",
                  textDecoration: "none",
                  fontWeight: 600,
                  fontSize: "13px",
                }}
              >
                📥 Download MP4
              </a>
              {onNavigateToGallery && (
                <button
                  onClick={() => {
                    onClose();
                    onNavigateToGallery();
                  }}
                  style={{
                    flex: 1,
                    background: "#334155",
                    color: "#f8fafc",
                    border: "1px solid #475569",
                    padding: "10px",
                    borderRadius: "6px",
                    fontWeight: 600,
                    fontSize: "13px",
                    cursor: "pointer",
                  }}
                >
                  📂 View in Gallery
                </button>
              )}
            </div>
          </div>
        ) : (
          <form onSubmit={handleExport} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <div>
              <label style={{ fontSize: "12px", color: "#94a3b8", display: "block", marginBottom: "4px" }}>
                Camera
              </label>
              <input
                type="text"
                disabled
                value={`${cameraName || cameraSerial} (${cameraSerial})`}
                style={{
                  width: "100%",
                  padding: "8px 10px",
                  background: "#0f172a",
                  border: "1px solid #334155",
                  borderRadius: "4px",
                  color: "#cbd5e1",
                  fontSize: "13px",
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: "12px", color: "#94a3b8", display: "block", marginBottom: "4px" }}>
                Clip Title (optional)
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Incident Evidence"
                style={{
                  width: "100%",
                  padding: "8px 10px",
                  background: "#0f172a",
                  border: "1px solid #334155",
                  borderRadius: "4px",
                  color: "#f8fafc",
                  fontSize: "13px",
                }}
              />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div>
                <label style={{ fontSize: "12px", color: "#94a3b8", display: "block", marginBottom: "4px" }}>
                  Start Time
                </label>
                <input
                  type="datetime-local"
                  step="1"
                  required
                  value={startTimeStr}
                  onChange={(e) => setStartTimeStr(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 10px",
                    background: "#0f172a",
                    border: "1px solid #334155",
                    borderRadius: "4px",
                    color: "#f8fafc",
                    fontSize: "13px",
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: "12px", color: "#94a3b8", display: "block", marginBottom: "4px" }}>
                  End Time
                </label>
                <input
                  type="datetime-local"
                  step="1"
                  required
                  value={endTimeStr}
                  onChange={(e) => setEndTimeStr(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 10px",
                    background: "#0f172a",
                    border: "1px solid #334155",
                    borderRadius: "4px",
                    color: "#f8fafc",
                    fontSize: "13px",
                  }}
                />
              </div>
            </div>

            <div
              style={{
                background: "#0f172a",
                padding: "10px 12px",
                borderRadius: "4px",
                fontSize: "12px",
                color: "#94a3b8",
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <span>Calculated Clip Duration:</span>
              <strong style={{ color: "#38bdf8" }}>
                {durationSec > 0 ? `${durationSec} seconds (${(durationSec / 60).toFixed(1)} mins)` : "0s"}
              </strong>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "8px" }}>
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                style={{
                  background: "transparent",
                  color: "#94a3b8",
                  border: "1px solid #475569",
                  padding: "8px 16px",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || durationSec <= 0}
                style={{
                  background: "#0284c7",
                  color: "#ffffff",
                  border: "none",
                  padding: "8px 20px",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: loading || durationSec <= 0 ? "not-allowed" : "pointer",
                  opacity: loading || durationSec <= 0 ? 0.6 : 1,
                }}
              >
                {loading ? "Exporting..." : "Start Lossless Export"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

