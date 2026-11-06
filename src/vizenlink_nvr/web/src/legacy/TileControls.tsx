import React from "react";
import { PlayerState, StreamRole } from "../services/player";

interface TileControlsProps {
  serial: string;
  name: string;
  state: PlayerState;
  stream: StreamRole;
  isRecording: boolean;
  isMuted: boolean;
  isMaximized: boolean;
  onToggleMute: () => void;
  onToggleMaximize: () => void;
  onSnapshot: () => void;
}

export const TileControls: React.FC<TileControlsProps> = ({
  serial,
  name,
  state,
  stream,
  isRecording,
  isMuted,
  isMaximized,
  onToggleMute,
  onToggleMaximize,
  onSnapshot,
}) => {
  const getBadgeColor = (s: PlayerState) => {
    switch (s) {
      case "live":
        return "#10b981"; // green
      case "stalled":
        return "#f59e0b"; // yellow
      case "connecting":
        return "#3b82f6"; // blue
      case "offline":
      case "error":
      default:
        return "#ef4444"; // red
    }
  };

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        pointerEvents: "none",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "8px",
      }}
    >
      {/* Top Header: Name and Dual Badges */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ background: "rgba(15, 23, 42, 0.75)", padding: "2px 8px", borderRadius: "4px", fontSize: "12px", fontWeight: "bold" }}>
          {name} ({serial}) - <span style={{ textTransform: "uppercase", fontSize: "10px", color: "#94a3b8" }}>{stream}</span>
        </div>

        <div style={{ display: "flex", gap: "6px" }}>
          {/* Status Badge */}
          <span
            style={{
              background: getBadgeColor(state),
              color: "#fff",
              fontSize: "11px",
              padding: "2px 6px",
              borderRadius: "4px",
              textTransform: "uppercase",
              fontWeight: 600,
            }}
          >
            {state}
          </span>

          {/* Recording Badge */}
          {isRecording && (
            <span
              style={{
                background: "#dc2626",
                color: "#fff",
                fontSize: "11px",
                padding: "2px 6px",
                borderRadius: "4px",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                fontWeight: 600,
              }}
            >
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#fff" }} />
              REC
            </span>
          )}
        </div>
      </div>

      {/* Bottom Bar: Action buttons */}
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          gap: "8px",
          pointerEvents: "auto",
        }}
      >
        {/* Snapshot Download */}
        <button
          onClick={onSnapshot}
          title="Download snapshot"
          disabled={state !== "live"}
          style={{
            background: "rgba(30, 41, 59, 0.8)",
            color: "#fff",
            border: "1px solid #475569",
            borderRadius: "4px",
            padding: "4px 8px",
            cursor: state === "live" ? "pointer" : "not-allowed",
            fontSize: "12px",
          }}
        >
          📷 Snapshot
        </button>

        {/* Audio Mute Toggle */}
        <button
          onClick={onToggleMute}
          title={isMuted ? "Unmute" : "Mute"}
          style={{
            background: "rgba(30, 41, 59, 0.8)",
            color: "#fff",
            border: "1px solid #475569",
            borderRadius: "4px",
            padding: "4px 8px",
            cursor: "pointer",
            fontSize: "12px",
          }}
        >
          {isMuted ? "🔇 Unmute" : "🔊 Mute"}
        </button>

        {/* Maximize / Restore Toggle */}
        <button
          onClick={onToggleMaximize}
          title={isMaximized ? "Restore grid" : "Maximize view"}
          style={{
            background: "rgba(30, 41, 59, 0.8)",
            color: "#fff",
            border: "1px solid #475569",
            borderRadius: "4px",
            padding: "4px 8px",
            cursor: "pointer",
            fontSize: "12px",
          }}
        >
          {isMaximized ? "🗗 Restore" : "🗖 Maximize"}
        </button>
      </div>
    </div>
  );
};

