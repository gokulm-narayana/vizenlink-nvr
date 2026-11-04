import React, { useEffect, useState } from "react";
import { GridDimension, GridStorage } from "../services/grid_storage";
import { VideoTile } from "./VideoTile";

export interface CameraInfo {
  serial: string;
  name: string;
  state: string;
}

interface LiveGridProps {
  cameras: CameraInfo[];
  recordingSerials?: Set<string>;
}

export const LiveGrid: React.FC<LiveGridProps> = ({ cameras, recordingSerials = new Set() }) => {
  const [dimension, setDimension] = useState<GridDimension>(2);
  const [page, setPage] = useState<number>(0);
  const [maximizedSerial, setMaximizedSerial] = useState<string | null>(null);

  // Load layout from localStorage on mount
  useEffect(() => {
    const saved = GridStorage.load(2);
    setDimension(saved.dimension);
    setPage(saved.page);
  }, []);

  // Save layout to localStorage on change
  useEffect(() => {
    GridStorage.save({
      dimension,
      page,
      slotAssignments: {},
    });
  }, [dimension, page]);

  const tilesPerPage = dimension * dimension;
  const totalPages = Math.max(1, Math.ceil(cameras.length / tilesPerPage));
  const currentPage = Math.min(page, totalPages - 1);

  const startIdx = currentPage * tilesPerPage;
  const visibleCameras = cameras.slice(startIdx, startIdx + tilesPerPage);

  // Render full screen or maximized single view
  if (maximizedSerial) {
    const cam = cameras.find((c) => c.serial === maximizedSerial);
    return (
      <div style={{ width: "100%", height: "calc(100vh - 70px)", padding: "12px", boxSizing: "border-box" }}>
        {cam && (
          <VideoTile
            serial={cam.serial}
            name={cam.name}
            isRecording={recordingSerials.has(cam.serial)}
            isMaximized={true}
            onToggleMaximize={() => setMaximizedSerial(null)}
          />
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 70px)", padding: "12px", boxSizing: "border-box" }}>
      {/* Top Toolbar: Grid Selectors and Pagination */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span style={{ fontSize: "14px", fontWeight: "bold", color: "#94a3b8" }}>Layout:</span>
          {([1, 2, 3, 4] as GridDimension[]).map((dim) => (
            <button
              key={dim}
              onClick={() => {
                setDimension(dim);
                setPage(0);
              }}
              style={{
                background: dimension === dim ? "#2563eb" : "#334155",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                padding: "6px 12px",
                cursor: "pointer",
                fontWeight: dimension === dim ? "bold" : "normal",
              }}
            >
              {dim}×{dim}
            </button>
          ))}
        </div>

        {totalPages > 1 && (
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <button
              disabled={currentPage === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              style={{ background: "#334155", color: "#fff", border: "none", borderRadius: "4px", padding: "6px 12px", cursor: currentPage === 0 ? "not-allowed" : "pointer" }}
            >
              ◀ Prev
            </button>
            <span style={{ fontSize: "13px", color: "#94a3b8" }}>
              Page {currentPage + 1} of {totalPages}
            </span>
            <button
              disabled={currentPage >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              style={{ background: "#334155", color: "#fff", border: "none", borderRadius: "4px", padding: "6px 12px", cursor: currentPage >= totalPages - 1 ? "not-allowed" : "pointer" }}
            >
              Next ▶
            </button>
          </div>
        )}
      </div>

      {/* Multiview Grid Matrix */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${dimension}, 1fr)`,
          gridTemplateRows: `repeat(${dimension}, 1fr)`,
          gap: "8px",
          flex: 1,
          width: "100%",
          minHeight: 0,
        }}
      >
        {Array.from({ length: tilesPerPage }).map((_, index) => {
          const cam = visibleCameras[index];
          if (!cam) {
            return (
              <div
                key={`empty-${index}`}
                style={{
                  background: "#1e293b",
                  borderRadius: "4px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#475569",
                  fontSize: "14px",
                }}
              >
                Empty Slot
              </div>
            );
          }

          return (
            <VideoTile
              key={cam.serial}
              serial={cam.serial}
              name={cam.name}
              isRecording={recordingSerials.has(cam.serial)}
              isMaximized={false}
              onToggleMaximize={() => setMaximizedSerial(cam.serial)}
            />
          );
        })}
      </div>
    </div>
  );
};
