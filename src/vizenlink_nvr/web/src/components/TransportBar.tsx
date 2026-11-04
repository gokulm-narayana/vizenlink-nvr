import React from "react";

interface TransportBarProps {
  isPlaying: boolean;
  onPlayPause: () => void;
  onSkip: (seconds: number) => void;
  playbackRate: number;
  onRateChange: (rate: number) => void;
  isMuted: boolean;
  onToggleMute: () => void;
  onToggleFullscreen: () => void;
  onTakeSnapshot: () => void;
  onOpenExport: () => void;
  currentTimeFormatted: string;
  hasActiveSegment: boolean;
}

const RATES = [0.5, 1, 2, 4, 8];

export const TransportBar: React.FC<TransportBarProps> = ({
  isPlaying,
  onPlayPause,
  onSkip,
  playbackRate,
  onRateChange,
  isMuted,
  onToggleMute,
  onToggleFullscreen,
  onTakeSnapshot,
  onOpenExport,
  currentTimeFormatted,
  hasActiveSegment,
}) => {
  return (
    <div
      style={{
        height: "56px",
        background: "#1e293b",
        borderTop: "1px solid #334155",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 20px",
        color: "#f8fafc",
      }}
    >
      {/* Left: Playback transport & skips */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        {/* -10s */}
        <button
          onClick={() => onSkip(-10)}
          style={{
            background: "#334155",
            color: "#f8fafc",
            border: "none",
            borderRadius: "4px",
            padding: "6px 12px",
            fontSize: "13px",
            fontWeight: 600,
            cursor: "pointer",
          }}
          title="Skip backward 10 seconds"
        >
          ⏪ -10s
        </button>

        {/* Play/Pause */}
        <button
          onClick={onPlayPause}
          disabled={!hasActiveSegment}
          style={{
            background: isPlaying ? "#0284c7" : "#0f766e",
            color: "#ffffff",
            border: "none",
            borderRadius: "6px",
            padding: "8px 18px",
            fontSize: "14px",
            fontWeight: "bold",
            cursor: hasActiveSegment ? "pointer" : "not-allowed",
            opacity: hasActiveSegment ? 1 : 0.5,
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}
          title={isPlaying ? "Pause playback" : "Start playback"}
        >
          {isPlaying ? "⏸ Pause" : "▶ Play"}
        </button>

        {/* +10s */}
        <button
          onClick={() => onSkip(10)}
          style={{
            background: "#334155",
            color: "#f8fafc",
            border: "none",
            borderRadius: "4px",
            padding: "6px 12px",
            fontSize: "13px",
            fontWeight: 600,
            cursor: "pointer",
          }}
          title="Skip forward 10 seconds"
        >
          +10s ⏩
        </button>

        {/* Speed Selector */}
        <div style={{ display: "flex", alignItems: "center", gap: "4px", marginLeft: "8px" }}>
          <span style={{ fontSize: "12px", color: "#94a3b8" }}>Speed:</span>
          {RATES.map((rate) => (
            <button
              key={rate}
              onClick={() => onRateChange(rate)}
              style={{
                background: playbackRate === rate ? "#38bdf8" : "#0f172a",
                color: playbackRate === rate ? "#0f172a" : "#cbd5e1",
                border: "1px solid #334155",
                borderRadius: "3px",
                padding: "3px 6px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {rate}x
            </button>
          ))}
        </div>
      </div>

      {/* Center: Current Playhead Timestamp */}
      <div
        style={{
          fontFamily: "monospace",
          fontSize: "14px",
          color: "#38bdf8",
          background: "#0f172a",
          padding: "4px 12px",
          borderRadius: "4px",
          border: "1px solid #1e293b",
        }}
      >
        {currentTimeFormatted}
      </div>

      {/* Right: Snapshot, Export, Mute, Fullscreen */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <button
          onClick={onTakeSnapshot}
          style={{
            background: "#334155",
            color: "#f8fafc",
            border: "1px solid #475569",
            borderRadius: "4px",
            padding: "6px 12px",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "5px",
          }}
          title="Save snapshot frame to gallery"
        >
          📷 Snapshot
        </button>

        <button
          onClick={onOpenExport}
          style={{
            background: "#0284c7",
            color: "#ffffff",
            border: "none",
            borderRadius: "4px",
            padding: "6px 14px",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "5px",
          }}
          title="Export MP4 video clip for selected range"
        >
          ✂️ Export Clip
        </button>

        <button
          onClick={onToggleMute}
          style={{
            background: "transparent",
            color: isMuted ? "#ef4444" : "#94a3b8",
            border: "none",
            fontSize: "16px",
            cursor: "pointer",
            padding: "4px",
          }}
          title={isMuted ? "Unmute" : "Mute"}
        >
          {isMuted ? "🔇" : "🔊"}
        </button>

        <button
          onClick={onToggleFullscreen}
          style={{
            background: "transparent",
            color: "#94a3b8",
            border: "none",
            fontSize: "16px",
            cursor: "pointer",
            padding: "4px",
          }}
          title="Toggle Fullscreen"
        >
          ⛶
        </button>
      </div>
    </div>
  );
};
