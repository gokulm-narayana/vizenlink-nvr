import React, { useRef, useState, useEffect, useCallback } from "react";

export type ZoomLevel = "24h" | "12h" | "4h" | "1h";

export interface TimelineSegment {
  id: number;
  start_time: string;
  end_time: string;
  is_protected: boolean;
  duration_seconds: number;
}

export interface TimelineOutage {
  id: number;
  started_at: string;
  ended_at?: string | null;
  duration_seconds?: number | null;
  reason?: string | null;
}

export interface TimelineEvent {
  id: number;
  event_type: string;
  start_time: string;
  end_time?: string | null;
  is_locked: boolean;
}

interface TimelineCanvasProps {
  baseDate: Date;
  currentTime: Date;
  onSeek: (target: Date) => void;
  segments: TimelineSegment[];
  outages: TimelineOutage[];
  events: TimelineEvent[];
  zoomLevel: ZoomLevel;
  onZoomChange: (zoom: ZoomLevel) => void;
  inMarker: Date | null;
  outMarker: Date | null;
  onSetInMarker: () => void;
  onSetOutMarker: () => void;
  onClearMarkers: () => void;
}

export const TimelineCanvas: React.FC<TimelineCanvasProps> = ({
  baseDate,
  currentTime,
  onSeek,
  segments,
  outages,
  events,
  zoomLevel,
  onZoomChange,
  inMarker,
  outMarker,
  onSetInMarker,
  onSetOutMarker,
  onClearMarkers,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [hoverTime, setHoverTime] = useState<Date | null>(null);
  const [hoverPos, setHoverPos] = useState<number | null>(null);

  // Calculate visible window [windowStart, windowEnd] based on zoomLevel and currentTime
  const getWindowRange = useCallback((): [Date, Date] => {
    const startOfDay = new Date(baseDate);
    startOfDay.setHours(0, 0, 0, 0);

    const endOfDay = new Date(baseDate);
    endOfDay.setHours(23, 59, 59, 999);

    if (zoomLevel === "24h") {
      return [startOfDay, endOfDay];
    }

    const durationHours = zoomLevel === "12h" ? 12 : zoomLevel === "4h" ? 4 : 1;
    const durationMs = durationHours * 3600 * 1000;

    let centerMs = currentTime.getTime();
    if (isNaN(centerMs) || centerMs < startOfDay.getTime() || centerMs > endOfDay.getTime()) {
      centerMs = startOfDay.getTime() + durationMs / 2;
    }

    let winStart = new Date(centerMs - durationMs / 2);
    let winEnd = new Date(centerMs + durationMs / 2);

    if (winStart < startOfDay) {
      winStart = startOfDay;
      winEnd = new Date(startOfDay.getTime() + durationMs);
    }
    if (winEnd > endOfDay) {
      winEnd = endOfDay;
      winStart = new Date(endOfDay.getTime() - durationMs);
    }

    return [winStart, winEnd];
  }, [baseDate, currentTime, zoomLevel]);

  const [winStart, winEnd] = getWindowRange();
  const totalWindowMs = Math.max(1000, winEnd.getTime() - winStart.getTime());

  const timeToPct = (timeStrOrDate: string | Date): number => {
    const t = typeof timeStrOrDate === "string" ? new Date(timeStrOrDate).getTime() : timeStrOrDate.getTime();
    return Math.max(0, Math.min(100, ((t - winStart.getTime()) / totalWindowMs) * 100));
  };

  const pctToDate = (pct: number): Date => {
    const clamped = Math.max(0, Math.min(100, pct));
    return new Date(winStart.getTime() + (clamped / 100) * totalWindowMs);
  };

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!containerRef.current) return;
    setIsDragging(true);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    seekFromPointer(e.clientX);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = (x / rect.width) * 100;
    setHoverPos(x);
    setHoverTime(pctToDate(pct));

    if (isDragging) {
      seekFromPointer(e.clientX);
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (isDragging) {
      setIsDragging(false);
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        // pointer capture already lost
      }
    }
  };

  const seekFromPointer = (clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const pct = (x / rect.width) * 100;
    onSeek(pctToDate(pct));
  };

  // Generate tick marks (hours and half-hours)
  const renderTicks = () => {
    const ticks: React.ReactNode[] = [];
    const stepHours = zoomLevel === "24h" ? 2 : zoomLevel === "12h" ? 1 : zoomLevel === "4h" ? 0.5 : 0.166;
    const stepMs = stepHours * 3600 * 1000;

    let t = Math.ceil(winStart.getTime() / stepMs) * stepMs;
    while (t <= winEnd.getTime()) {
      const d = new Date(t);
      const pct = timeToPct(d);
      const isMajor = d.getMinutes() === 0;
      const label = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

      ticks.push(
        <div
          key={`tick-${t}`}
          style={{
            position: "absolute",
            left: `${pct}%`,
            top: 0,
            bottom: 0,
            width: "1px",
            background: isMajor ? "#475569" : "#334155",
            pointerEvents: "none",
          }}
        >
          {isMajor && (
            <span
              style={{
                position: "absolute",
                top: "2px",
                left: "4px",
                fontSize: "10px",
                color: "#94a3b8",
                userSelect: "none",
                whiteSpace: "nowrap",
              }}
            >
              {label}
            </span>
          )}
        </div>
      );
      t += stepMs;
    }
    return ticks;
  };

  const playheadPct = timeToPct(currentTime);
  const inPct = inMarker ? timeToPct(inMarker) : null;
  const outPct = outMarker ? timeToPct(outMarker) : null;

  return (
    <div
      style={{
        background: "#0f172a",
        borderTop: "1px solid #334155",
        padding: "12px 16px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        userSelect: "none",
      }}
    >
      {/* Top Header Controls: Zoom and Marker Actions */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        {/* Markers Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px" }}>
          <span style={{ color: "#94a3b8", fontWeight: 500 }}>Export Markers:</span>
          <button
            onClick={onSetInMarker}
            style={{
              background: inMarker ? "#0284c7" : "#1e293b",
              color: "#f8fafc",
              border: "1px solid #38bdf8",
              borderRadius: "4px",
              padding: "3px 8px",
              cursor: "pointer",
              fontWeight: 600,
            }}
            title="Set In Marker at current playhead"
          >
            [ In {inMarker ? inMarker.toLocaleTimeString([], { hour12: false }) : ""}
          </button>
          <button
            onClick={onSetOutMarker}
            style={{
              background: outMarker ? "#0284c7" : "#1e293b",
              color: "#f8fafc",
              border: "1px solid #38bdf8",
              borderRadius: "4px",
              padding: "3px 8px",
              cursor: "pointer",
              fontWeight: 600,
            }}
            title="Set Out Marker at current playhead"
          >
            Out ] {outMarker ? outMarker.toLocaleTimeString([], { hour12: false }) : ""}
          </button>
          {(inMarker || outMarker) && (
            <button
              onClick={onClearMarkers}
              style={{
                background: "transparent",
                color: "#ef4444",
                border: "1px solid #7f1d1d",
                borderRadius: "4px",
                padding: "3px 6px",
                cursor: "pointer",
              }}
            >
              Clear
            </button>
          )}
        </div>

        {/* Legend */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px", fontSize: "11px", color: "#94a3b8" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <span style={{ width: "10px", height: "10px", background: "#10b981", borderRadius: "2px" }} />
            <span>Recorded</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <span style={{ width: "10px", height: "10px", background: "#f59e0b", borderRadius: "2px" }} />
            <span>Locked</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <span style={{ width: "10px", height: "10px", background: "#ef4444", borderRadius: "2px" }} />
            <span>Outage</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <span style={{ width: "8px", height: "8px", background: "#eab308", transform: "rotate(45deg)" }} />
            <span>Event</span>
          </div>
        </div>

        {/* Zoom Selector */}
        <div style={{ display: "flex", gap: "4px" }}>
          {(["24h", "12h", "4h", "1h"] as ZoomLevel[]).map((level) => (
            <button
              key={level}
              onClick={() => onZoomChange(level)}
              style={{
                background: zoomLevel === level ? "#38bdf8" : "#1e293b",
                color: zoomLevel === level ? "#0f172a" : "#94a3b8",
                border: "1px solid #334155",
                borderRadius: "4px",
                padding: "3px 8px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {level}
            </button>
          ))}
        </div>
      </div>

      {/* Main Interactive Bar */}
      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onMouseLeave={() => {
          setHoverTime(null);
          setHoverPos(null);
        }}
        style={{
          position: "relative",
          height: "64px",
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: "6px",
          overflow: "hidden",
          cursor: isDragging ? "grabbing" : "pointer",
          touchAction: "none",
        }}
      >
        {/* Tick Lines */}
        {renderTicks()}

        {/* In / Out Selection Range Fill */}
        {inPct !== null && outPct !== null && inPct < outPct && (
          <div
            style={{
              position: "absolute",
              left: `${inPct}%`,
              width: `${outPct - inPct}%`,
              top: 0,
              bottom: 0,
              background: "rgba(56, 189, 248, 0.2)",
              borderLeft: "2px solid #38bdf8",
              borderRight: "2px solid #38bdf8",
              pointerEvents: "none",
            }}
          />
        )}

        {/* Recorded Spans (Teal/Green) */}
        {segments.map((seg) => {
          const sPct = timeToPct(seg.start_time);
          const ePct = timeToPct(seg.end_time);
          const widthPct = Math.max(0.15, ePct - sPct);
          if (sPct > 100 || ePct < 0) return null;

          return (
            <div
              key={`seg-${seg.id}`}
              title={`Segment #${seg.id}: ${new Date(seg.start_time).toLocaleTimeString()} - ${new Date(seg.end_time).toLocaleTimeString()}`}
              style={{
                position: "absolute",
                left: `${sPct}%`,
                width: `${widthPct}%`,
                top: "18px",
                height: "28px",
                background: seg.is_protected ? "#f59e0b" : "#10b981",
                borderRadius: "2px",
                opacity: 0.9,
              }}
            />
          );
        })}

        {/* Camera Outages (Red, PLAY-08) */}
        {outages.map((outage) => {
          const sPct = timeToPct(outage.started_at);
          const eTime = outage.ended_at ? new Date(outage.ended_at) : new Date();
          const ePct = timeToPct(eTime);
          const widthPct = Math.max(0.2, ePct - sPct);
          if (sPct > 100 || ePct < 0) return null;

          return (
            <div
              key={`outage-${outage.id}`}
              title={`Outage: ${outage.reason || "Camera disconnected"} (${new Date(outage.started_at).toLocaleTimeString()})`}
              style={{
                position: "absolute",
                left: `${sPct}%`,
                width: `${widthPct}%`,
                top: "18px",
                height: "28px",
                background: "repeating-linear-gradient(45deg, #ef4444, #ef4444 6px, #b91c1c 6px, #b91c1c 12px)",
                borderRadius: "2px",
                border: "1px solid #f87171",
              }}
            />
          );
        })}

        {/* Event Markers (Yellow Diamonds / Tags, PLAY-01) */}
        {events.map((evt) => {
          const pct = timeToPct(evt.start_time);
          if (pct < 0 || pct > 100) return null;

          return (
            <div
              key={`evt-${evt.id}`}
              title={`Event #${evt.id} (${evt.event_type}) at ${new Date(evt.start_time).toLocaleTimeString()}`}
              style={{
                position: "absolute",
                left: `${pct}%`,
                top: "48px",
                transform: "translateX(-50%) rotate(45deg)",
                width: "9px",
                height: "9px",
                background: evt.is_locked ? "#ef4444" : "#eab308",
                border: "1px solid #ffffff",
                zIndex: 2,
              }}
            />
          );
        })}

        {/* Hover Time Indicator */}
        {hoverPos !== null && hoverTime && (
          <div
            style={{
              position: "absolute",
              left: `${hoverPos}px`,
              top: 0,
              bottom: 0,
              width: "1px",
              background: "rgba(255, 255, 255, 0.4)",
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                position: "absolute",
                bottom: "2px",
                transform: "translateX(-50%)",
                background: "#0284c7",
                color: "#ffffff",
                padding: "1px 5px",
                borderRadius: "3px",
                fontSize: "10px",
                fontWeight: 600,
                whiteSpace: "nowrap",
              }}
            >
              {hoverTime.toLocaleTimeString([], { hour12: false })}
            </div>
          </div>
        )}

        {/* Playhead Line */}
        <div
          style={{
            position: "absolute",
            left: `${playheadPct}%`,
            top: 0,
            bottom: 0,
            width: "2px",
            background: "#ef4444",
            zIndex: 10,
            pointerEvents: "none",
          }}
        >
          {/* Triangular head */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: "-5px",
              width: 0,
              height: 0,
              borderLeft: "6px solid transparent",
              borderRight: "6px solid transparent",
              borderTop: "8px solid #ef4444",
            }}
          />
        </div>
      </div>
    </div>
  );
};
