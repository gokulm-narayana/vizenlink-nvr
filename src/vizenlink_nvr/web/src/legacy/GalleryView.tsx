import React, { useState, useEffect, useCallback } from "react";
import { CameraOption } from "./PlaybackView";

export interface GalleryItem {
  id: number;
  camera_serial: string;
  item_type: "snapshot" | "manual_clip" | "export_clip";
  title: string;
  file_path: string;
  file_size_bytes: number;
  duration_seconds?: number | null;
  captured_at: string;
  created_at: string;
  user_id?: number | null;
}

interface GalleryViewProps {
  cameras: CameraOption[];
  userRole?: string;
  onJumpToPlayback?: (cameraSerial: string, timestamp: string) => void;
}

type TypeFilter = "all" | "snapshot" | "export_clip";

export const GalleryView: React.FC<GalleryViewProps> = ({
  cameras,
  userRole,
  onJumpToPlayback,
}) => {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [selectedCamera, setSelectedCamera] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");

  // Modals
  const [previewItem, setPreviewItem] = useState<GalleryItem | null>(null);
  const [itemToDelete, setItemToDelete] = useState<GalleryItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const cameraMap = new Map(cameras.map((c) => [c.serial, c.name]));

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    params.set("limit", "100");
    if (selectedCamera) params.set("camera_serial", selectedCamera);
    if (typeFilter !== "all") params.set("item_type", typeFilter);
    if (startDate) params.set("start_time", new Date(`${startDate}T00:00:00Z`).toISOString());
    if (endDate) params.set("end_time", new Date(`${endDate}T23:59:59Z`).toISOString());

    try {
      const res = await fetch(`/api/v1/gallery?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch gallery items: HTTP ${res.status}`);
      }
      const data = await res.json();
      setItems(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message || "Could not load gallery items");
    } finally {
      setLoading(false);
    }
  }, [selectedCamera, typeFilter, startDate, endDate]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleDeleteConfirm = async () => {
    if (!itemToDelete) return;
    setDeleting(true);
    try {
      const res = await fetch(`/api/v1/gallery/${itemToDelete.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setItemToDelete(null);
      await fetchItems();
    } catch (err: any) {
      alert(`Deletion failed: ${err.message}`);
    } finally {
      setDeleting(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const isOperatorOrOwner = userRole === "owner" || userRole === "operator";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#0b1329",
        color: "#f8fafc",
        overflow: "hidden",
      }}
    >
      {/* Top Filter and Controls Bar */}
      <div
        style={{
          background: "#1e293b",
          borderBottom: "1px solid #334155",
          padding: "12px 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        {/* Type Tabs */}
        <div style={{ display: "flex", gap: "6px" }}>
          {(
            [
              { id: "all", label: "All Media" },
              { id: "snapshot", label: "📷 Snapshots" },
              { id: "export_clip", label: "🎬 Clips" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setTypeFilter(tab.id)}
              style={{
                background: typeFilter === tab.id ? "#0284c7" : "#0f172a",
                color: typeFilter === tab.id ? "#ffffff" : "#94a3b8",
                border: "1px solid",
                borderColor: typeFilter === tab.id ? "#38bdf8" : "#334155",
                borderRadius: "4px",
                padding: "6px 14px",
                fontSize: "13px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Secondary Filters: Camera & Date range */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          <select
            value={selectedCamera}
            onChange={(e) => setSelectedCamera(e.target.value)}
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #334155",
              borderRadius: "4px",
              padding: "5px 10px",
              fontSize: "13px",
            }}
          >
            <option value="">All Cameras</option>
            {cameras.map((c) => (
              <option key={c.serial} value={c.serial}>
                {c.name} ({c.serial})
              </option>
            ))}
          </select>

          <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#94a3b8" }}>
            <span>From:</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={{
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "4px",
                padding: "4px 8px",
                fontSize: "12px",
              }}
            />
            <span>To:</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={{
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "4px",
                padding: "4px 8px",
                fontSize: "12px",
              }}
            />
            {(startDate || endDate || selectedCamera) && (
              <button
                onClick={() => {
                  setStartDate("");
                  setEndDate("");
                  setSelectedCamera("");
                }}
                style={{
                  background: "transparent",
                  color: "#ef4444",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "12px",
                }}
              >
                Reset
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
        {error && (
          <div
            style={{
              background: "#fee2e2",
              color: "#b91c1c",
              padding: "12px",
              borderRadius: "6px",
              marginBottom: "16px",
            }}
          >
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: "center", padding: "40px", color: "#38bdf8" }}>
            Loading gallery media...
          </div>
        ) : items.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "80px 20px",
              background: "#1e293b",
              borderRadius: "8px",
              border: "1px dashed #334155",
              maxWidth: "500px",
              margin: "40px auto",
            }}
          >
            <div style={{ fontSize: "40px", marginBottom: "12px" }}>🖼️</div>
            <h3 style={{ fontSize: "16px", fontWeight: "bold", margin: 0, color: "#cbd5e1" }}>
              No Gallery Media Found
            </h3>
            <p style={{ fontSize: "13px", color: "#64748b", marginTop: "6px" }}>
              {selectedCamera || startDate || endDate || typeFilter !== "all"
                ? "No snapshots or clips match your current filter selection."
                : "Capture snapshots from Live Multiview or export clips from the 24h Playback timeline to see them here."}
            </p>
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: "20px",
            }}
          >
            {items.map((item) => {
              const isSnapshot = item.item_type === "snapshot";
              const downloadUrl = `/api/v1/gallery/${item.id}/download`;
              const camName = cameraMap.get(item.camera_serial) || item.camera_serial;

              return (
                <div
                  key={item.id}
                  style={{
                    background: "#1e293b",
                    border: "1px solid #334155",
                    borderRadius: "8px",
                    overflow: "hidden",
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  {/* Thumbnail / Media Container */}
                  <div
                    onClick={() => setPreviewItem(item)}
                    style={{
                      height: "160px",
                      background: "#0f172a",
                      position: "relative",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {isSnapshot ? (
                      <img
                        src={downloadUrl}
                        alt={item.title}
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        loading="lazy"
                      />
                    ) : (
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                          gap: "8px",
                          color: "#38bdf8",
                        }}
                      >
                        <div
                          style={{
                            width: "48px",
                            height: "48px",
                            background: "rgba(2, 132, 199, 0.4)",
                            borderRadius: "50%",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: "20px",
                          }}
                        >
                          ▶
                        </div>
                        <span style={{ fontSize: "11px", fontWeight: 600 }}>Click to Preview Clip</span>
                      </div>
                    )}

                    {/* Top Right Type Badge */}
                    <div
                      style={{
                        position: "absolute",
                        top: "8px",
                        right: "8px",
                        background: isSnapshot ? "rgba(15, 23, 42, 0.85)" : "rgba(2, 132, 199, 0.85)",
                        color: "#ffffff",
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        fontWeight: "bold",
                      }}
                    >
                      {isSnapshot ? "📷 Snapshot" : "🎬 Clip"}
                    </div>

                    {/* Duration Badge for Clips */}
                    {!isSnapshot && item.duration_seconds && (
                      <div
                        style={{
                          position: "absolute",
                          bottom: "8px",
                          right: "8px",
                          background: "rgba(0, 0, 0, 0.75)",
                          color: "#ffffff",
                          padding: "2px 6px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontFamily: "monospace",
                        }}
                      >
                        {Math.round(item.duration_seconds)}s
                      </div>
                    )}
                  </div>

                  {/* Card Content & Details */}
                  <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "6px", flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: "13px", color: "#f8fafc", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={item.title}>
                      {item.title}
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#94a3b8" }}>
                      <span>{camName}</span>
                      <span>{formatFileSize(item.file_size_bytes)}</span>
                    </div>

                    <div style={{ fontSize: "11px", color: "#64748b" }}>
                      {new Date(item.captured_at).toLocaleString([], { dateStyle: "short", timeStyle: "medium" })}
                    </div>

                    {/* Action Buttons */}
                    <div style={{ display: "flex", gap: "6px", marginTop: "8px", paddingTop: "8px", borderTop: "1px solid #334155" }}>
                      <a
                        href={downloadUrl}
                        download
                        style={{
                          flex: 1,
                          background: "#0284c7",
                          color: "#ffffff",
                          textAlign: "center",
                          padding: "5px 8px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: 600,
                          textDecoration: "none",
                        }}
                        title="Download file to computer"
                      >
                        📥 Download
                      </a>

                      {onJumpToPlayback && (
                        <button
                          onClick={() => onJumpToPlayback(item.camera_serial, item.captured_at)}
                          style={{
                            background: "#334155",
                            color: "#38bdf8",
                            border: "1px solid #475569",
                            borderRadius: "4px",
                            padding: "5px 8px",
                            fontSize: "12px",
                            fontWeight: 600,
                            cursor: "pointer",
                          }}
                          title="View on timeline"
                        >
                          ⏱ Seek
                        </button>
                      )}

                      {isOperatorOrOwner && (
                        <button
                          onClick={() => setItemToDelete(item)}
                          style={{
                            background: "transparent",
                            color: "#ef4444",
                            border: "1px solid #7f1d1d",
                            borderRadius: "4px",
                            padding: "5px 8px",
                            fontSize: "12px",
                            cursor: "pointer",
                          }}
                          title="Delete from gallery"
                        >
                          🗑
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Preview Modal */}
      {previewItem && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.85)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "20px",
          }}
          onClick={() => setPreviewItem(null)}
        >
          <div
            style={{
              background: "#1e293b",
              borderRadius: "8px",
              border: "1px solid #334155",
              maxWidth: "900px",
              width: "100%",
              maxHeight: "90vh",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              style={{
                padding: "12px 16px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderBottom: "1px solid #334155",
              }}
            >
              <div style={{ fontWeight: 600, fontSize: "14px", color: "#f8fafc" }}>
                {previewItem.title}
              </div>
              <button
                onClick={() => setPreviewItem(null)}
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

            {/* Media Body */}
            <div
              style={{
                flex: 1,
                background: "#000000",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                overflow: "hidden",
                minHeight: "300px",
              }}
            >
              {previewItem.item_type === "snapshot" ? (
                <img
                  src={`/api/v1/gallery/${previewItem.id}/download`}
                  alt={previewItem.title}
                  style={{ maxWidth: "100%", maxHeight: "70vh", objectFit: "contain" }}
                />
              ) : (
                <video
                  src={`/api/v1/gallery/${previewItem.id}/download`}
                  controls
                  autoPlay
                  style={{ maxWidth: "100%", maxHeight: "70vh" }}
                />
              )}
            </div>

            {/* Footer with Details & Download */}
            <div
              style={{
                padding: "12px 16px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderTop: "1px solid #334155",
                fontSize: "12px",
                color: "#94a3b8",
              }}
            >
              <div>
                Captured: {new Date(previewItem.captured_at).toLocaleString()} • Size: {formatFileSize(previewItem.file_size_bytes)}
              </div>
              <a
                href={`/api/v1/gallery/${previewItem.id}/download`}
                download
                style={{
                  background: "#0284c7",
                  color: "#ffffff",
                  padding: "6px 14px",
                  borderRadius: "4px",
                  textDecoration: "none",
                  fontWeight: 600,
                }}
              >
                📥 Download
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal (GAL-02 Safety Requirement) */}
      {itemToDelete && (
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
          onClick={() => !deleting && setItemToDelete(null)}
        >
          <div
            style={{
              background: "#1e293b",
              borderRadius: "8px",
              border: "1px solid #7f1d1d",
              width: "420px",
              maxWidth: "90%",
              padding: "20px",
              color: "#f8fafc",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 12px 0", color: "#ef4444", fontSize: "16px", fontWeight: "bold" }}>
              ⚠️ Confirm Permanent Deletion
            </h3>
            <p style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: "1.5", margin: "0 0 16px 0" }}>
              Are you sure you want to permanently delete <strong>{itemToDelete.title}</strong>? The media file will be permanently removed from storage disk. This action cannot be undone.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button
                disabled={deleting}
                onClick={() => setItemToDelete(null)}
                style={{
                  background: "transparent",
                  color: "#94a3b8",
                  border: "1px solid #475569",
                  padding: "6px 14px",
                  borderRadius: "4px",
                  fontSize: "13px",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                disabled={deleting}
                onClick={handleDeleteConfirm}
                style={{
                  background: "#dc2626",
                  color: "#ffffff",
                  border: "none",
                  padding: "6px 16px",
                  borderRadius: "4px",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: deleting ? "wait" : "pointer",
                }}
              >
                {deleting ? "Deleting..." : "Permanently Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

