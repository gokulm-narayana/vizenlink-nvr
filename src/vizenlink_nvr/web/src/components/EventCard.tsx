import React, { useState } from "react";

export interface EventData {
  id: number;
  camera_serial: string;
  event_type: string;
  source: string;
  start_time: string;
  end_time?: string | null;
  snapshot_path?: string | null;
  is_locked: boolean;
  clock_sync_state: string;
  raw_topic?: string | null;
  details?: Record<string, any> | null;
  created_at: string;
}

interface EventCardProps {
  event: EventData;
  cameraName?: string;
  isRead?: boolean;
  onSelect?: (event: EventData) => void;
  onLockToggle?: (eventId: number, newLocked: boolean) => Promise<void>;
}

const EVENT_TYPE_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  motion: { bg: "#fef3c7", text: "#b45309", label: "Motion" },
  line_crossing: { bg: "#ede9fe", text: "#6d28d9", label: "Line Crossing" },
  tamper: { bg: "#fee2e2", text: "#b91c1c", label: "Tamper" },
  person: { bg: "#dbeafe", text: "#1d4ed8", label: "Person" },
  vehicle: { bg: "#dcfce7", text: "#15803d", label: "Vehicle" },
};

export const EventCard: React.FC<EventCardProps> = ({
  event,
  cameraName,
  isRead = false,
  onSelect,
  onLockToggle,
}) => {
  const [imgError, setImgError] = useState(false);
  const [locking, setLocking] = useState(false);

  const styleConfig = EVENT_TYPE_COLORS[event.event_type] || {
    bg: "#334155",
    text: "#cbd5e1",
    label: event.event_type,
  };

  const handleLockClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onLockToggle || locking) return;
    setLocking(true);
    try {
      await onLockToggle(event.id, !event.is_locked);
    } finally {
      setLocking(false);
    }
  };

  const formattedTime = new Date(event.start_time).toLocaleString();

  return (
    <div
      onClick={() => onSelect && onSelect(event)}
      style={{
        background: isRead ? "#1e293b" : "#1e293b",
        border: isRead ? "1px solid #334155" : "1px solid #38bdf8",
        borderRadius: "8px",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        boxShadow: isRead ? "none" : "0 0 10px rgba(56, 189, 248, 0.2)",
        cursor: onSelect ? "pointer" : "default",
        position: "relative",
        transition: "border 0.2s, box-shadow 0.2s",
      }}
    >
      {/* Thumbnail Area */}
      <div
        style={{
          width: "100%",
          height: "160px",
          backgroundColor: "#0f172a",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {imgError || !event.snapshot_path ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "8px",
              color: "#64748b",
              fontSize: "12px",
            }}
          >
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
            <span>No Snapshot Available</span>
          </div>
        ) : (
          <img
            src={`/api/v1/events/${event.id}/snapshot`}
            alt={`${event.event_type} snapshot`}
            onError={() => setImgError(true)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        )}

        {/* Event Type Badge */}
        <div
          style={{
            position: "absolute",
            top: "8px",
            left: "8px",
            background: styleConfig.bg,
            color: styleConfig.text,
            fontWeight: "bold",
            fontSize: "11px",
            padding: "3px 8px",
            borderRadius: "4px",
            textTransform: "uppercase",
            boxShadow: "0 2px 4px rgba(0,0,0,0.3)",
          }}
        >
          {styleConfig.label}
        </div>

        {/* Lock State Pill */}
        {event.is_locked && (
          <div
            style={{
              position: "absolute",
              top: "8px",
              right: "8px",
              background: "#b91c1c",
              color: "#ffffff",
              fontSize: "10px",
              fontWeight: "bold",
              padding: "2px 6px",
              borderRadius: "4px",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            🔒 LOCKED
          </div>
        )}
      </div>

      {/* Details & Actions */}
      <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontWeight: 600, color: "#f8fafc", fontSize: "14px" }}>
            {cameraName || event.camera_serial}
          </span>
          <span style={{ fontSize: "11px", color: "#94a3b8" }}>{formattedTime}</span>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "12px" }}>
          <span style={{ color: "#64748b" }}>ID: #{event.id}</span>
          {event.clock_sync_state !== "synced" && (
            <span
              title={`Clock state: ${event.clock_sync_state}`}
              style={{
                color: "#eab308",
                fontSize: "11px",
                display: "flex",
                alignItems: "center",
                gap: "3px",
              }}
            >
              ⚠️ {event.clock_sync_state}
            </span>
          )}
        </div>

        {/* Lock/Unlock Button */}
        {onLockToggle && (
          <button
            onClick={handleLockClick}
            disabled={locking}
            style={{
              marginTop: "4px",
              background: event.is_locked ? "#334155" : "#1e3a8a",
              color: event.is_locked ? "#94a3b8" : "#93c5fd",
              border: "1px solid",
              borderColor: event.is_locked ? "#475569" : "#3b82f6",
              borderRadius: "4px",
              padding: "5px 10px",
              fontSize: "12px",
              fontWeight: 500,
              cursor: locking ? "wait" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
            }}
          >
            {event.is_locked ? "🔓 Unlock Footage" : "🔒 Protect & Lock"}
          </button>
        )}
      </div>
    </div>
  );
};

