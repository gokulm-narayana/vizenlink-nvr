import React, { useRef, useState, useEffect, useCallback, useMemo } from "react";
import { Lock, Bookmark } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { formatTime, useSiteTimeZone } from "@/lib/time";
import {
  getWindowRange,
  timeToPct,
  pctToTime,
  zoomAround,
  retentionSpan,
  nextZoom,
  ZOOM_LEVELS,
  type ZoomLevel,
  type TimelineSegment,
  type TimelineOutage,
  type TimelineEvent,
} from "@/lib/timeline";
import { HatchPattern } from "./HatchPattern";
import { TimelineLegend } from "./TimelineLegend";
import { TIMELINE_COPY } from "./copy";

export interface TimelineProps {
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
  // Optional enhancements
  zone?: string;
  retentionDays?: number | null;
  onTogglePlay?: () => void;
  onToggleMute?: () => void;
  onMarkIn?: () => void;
  onMarkOut?: () => void;
}

export const Timeline: React.FC<TimelineProps> = ({
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
  zone: zoneProp,
  retentionDays = null,
  onTogglePlay,
  onToggleMute,
  onMarkIn,
  onMarkOut,
}) => {
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;

  const trackRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [hoverTime, setHoverTime] = useState<Date | null>(null);
  const [hoverPos, setHoverPos] = useState<number | null>(null);
  const [hoverType, setHoverType] = useState<string | null>(null);

  // Active touches for pinch gesture
  const activePointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const pinchStartDist = useRef<number | null>(null);

  // Anchor keeps playhead centered when zooming or leaving view
  const [anchor, setAnchor] = useState<Date>(currentTime);

  useEffect(() => {
    // If currentTime goes out of current window, re-anchor
    const [wStart, wEnd] = getWindowRange(baseDate, zoomLevel, anchor, zone);
    if (currentTime < wStart || currentTime > wEnd) {
      setAnchor(currentTime);
    }
  }, [currentTime, baseDate, zoomLevel, anchor, zone]);

  const windowRange = useMemo<[Date, Date]>(() => {
    return getWindowRange(baseDate, zoomLevel, anchor, zone);
  }, [baseDate, zoomLevel, anchor, zone]);

  const [winStart, winEnd] = windowRange;

  const seekFromClientX = useCallback(
    (clientX: number) => {
      if (!trackRef.current) return;
      const rect = trackRef.current.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
      const pct = (x / rect.width) * 100;
      const targetTime = pctToTime(pct, windowRange);
      onSeek(targetTime);
    },
    [windowRange, onSeek]
  );

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!trackRef.current) return;
    activePointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (activePointers.current.size === 1) {
      setIsDragging(true);
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      seekFromClientX(e.clientX);
    } else if (activePointers.current.size === 2) {
      const pts = Array.from(activePointers.current.values());
      pinchStartDist.current = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
    }
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (activePointers.current.has(e.pointerId)) {
      activePointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    }

    if (activePointers.current.size === 2 && pinchStartDist.current) {
      const pts = Array.from(activePointers.current.values());
      const currentDist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const ratio = currentDist / pinchStartDist.current;
      if (ratio > 1.2) {
        onZoomChange(nextZoom(zoomLevel, "in"));
        pinchStartDist.current = currentDist;
      } else if (ratio < 0.8) {
        onZoomChange(nextZoom(zoomLevel, "out"));
        pinchStartDist.current = currentDist;
      }
      return;
    }

    if (!trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
    const pct = (x / rect.width) * 100;
    const target = pctToTime(pct, windowRange);
    setHoverPos(x);
    setHoverTime(target);

    // Identify hover type
    const tMs = target.getTime();
    const isOutage = outages.some((o) => {
      const s = new Date(o.started_at).getTime();
      const end = o.ended_at ? new Date(o.ended_at).getTime() : Date.now();
      return tMs >= s && tMs <= end;
    });
    const isEvent = events.find((evt) => {
      const s = new Date(evt.start_time).getTime();
      const end = evt.end_time ? new Date(evt.end_time).getTime() : s + 10000;
      return tMs >= s && tMs <= end;
    });
    const isRecorded = segments.some((seg) => {
      const s = new Date(seg.start_time).getTime();
      const end = new Date(seg.end_time).getTime();
      return tMs >= s && tMs <= end;
    });

    if (isOutage) {
      setHoverType(TIMELINE_COPY.TOOLTIP_OUTAGE);
    } else if (isEvent) {
      setHoverType(TIMELINE_COPY.TOOLTIP_EVENT(isEvent.event_type));
    } else if (isRecorded) {
      setHoverType(TIMELINE_COPY.TOOLTIP_RECORDED);
    } else {
      setHoverType(TIMELINE_COPY.TOOLTIP_NO_FOOTAGE);
    }

    if (isDragging) {
      seekFromClientX(e.clientX);
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    activePointers.current.delete(e.pointerId);
    if (activePointers.current.size < 2) {
      pinchStartDist.current = null;
    }
    if (activePointers.current.size === 0) {
      setIsDragging(false);
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        // pointer capture already lost
      }
    }
  };

  // Keyboard controls
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "SELECT" ||
      target.isContentEditable
    ) {
      return;
    }

    if (e.key === "ArrowRight") {
      e.preventDefault();
      const deltaMs = e.shiftKey ? 60000 : 10000;
      onSeek(new Date(currentTime.getTime() + deltaMs));
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const deltaMs = e.shiftKey ? 60000 : 10000;
      onSeek(new Date(currentTime.getTime() - deltaMs));
    } else if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      onZoomChange(nextZoom(zoomLevel, "in"));
    } else if (e.key === "-") {
      e.preventDefault();
      onZoomChange(nextZoom(zoomLevel, "out"));
    } else if (e.key === " ") {
      e.preventDefault();
      onTogglePlay?.();
    } else if (e.key === "m" || e.key === "M") {
      e.preventDefault();
      onToggleMute?.();
    } else if (e.key === "i" || e.key === "I") {
      e.preventDefault();
      if (onMarkIn) onMarkIn();
      else onSetInMarker();
    } else if (e.key === "o" || e.key === "O") {
      e.preventDefault();
      if (onMarkOut) onMarkOut();
      else onSetOutMarker();
    }
  };

  // Wheel zoom around cursor
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      const pct = (x / rect.width) * 100;
      const cursorTime = pctToTime(pct, windowRange);

      const direction = e.deltaY < 0 ? "in" : "out";
      const targetZoom = nextZoom(zoomLevel, direction);
      if (targetZoom !== zoomLevel) {
        const newRange = zoomAround(windowRange, cursorTime, targetZoom, baseDate, zone);
        setAnchor(new Date((newRange[0].getTime() + newRange[1].getTime()) / 2));
        onZoomChange(targetZoom);
      }
    };

    el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", onWheel);
    };
  }, [windowRange, zoomLevel, baseDate, zone, onZoomChange]);

  // Compute positions
  const playheadPct = timeToPct(currentTime, windowRange);
  const inPct = inMarker ? timeToPct(inMarker, windowRange) : null;
  const outPct = outMarker ? timeToPct(outMarker, windowRange) : null;

  const retention = useMemo(() => {
    return retentionSpan(windowRange, retentionDays);
  }, [windowRange, retentionDays]);

  // Generate tick marks anchored to the site-timezone window start (so GMT+5:30 gets exact hours too)
  const ticks = useMemo(() => {
    const res: Array<{ pct: number; label: string | null }> = [];
    const stepHours =
      zoomLevel === "24h" ? 2 : zoomLevel === "12h" ? 1 : zoomLevel === "4h" ? 0.5 : 0.25;
    const stepMs = stepHours * 3600 * 1000;

    let t = winStart.getTime();
    let stepIdx = 0;
    while (t <= winEnd.getTime()) {
      const d = new Date(t);
      const pct = timeToPct(d, windowRange);
      const isMajor = zoomLevel === "24h" || zoomLevel === "12h" ? true : stepIdx % 2 === 0;
      const rawLabel = isMajor && pct >= 0 && pct <= 97 ? formatTime(d, zone) : null;
      const label = rawLabel ? rawLabel.replace(/:00$/, "") : null;
      res.push({ pct, label });
      t += stepMs;
      stepIdx += 1;
    }
    return res;
  }, [winStart, winEnd, zoomLevel, windowRange, zone]);

  const handleSetIn = onMarkIn || onSetInMarker;
  const handleSetOut = onMarkOut || onSetOutMarker;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-2 select-none">
      <HatchPattern id="outage-hatch" />

      {/* Top Header Row: Markers, Legend, Zoom Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Markers */}
        <div className="flex items-center gap-2 text-xs font-normal">
          <span className="font-semibold text-muted-foreground">
            {TIMELINE_COPY.MARKERS_LABEL}
          </span>
          <Button
            variant={inMarker ? "secondary" : "outline"}
            size="sm"
            onClick={handleSetIn}
            className="text-xs font-semibold px-2 py-1 h-8"
          >
            [ In {inMarker ? formatTime(inMarker, zone) : ""}
          </Button>
          <Button
            variant={outMarker ? "secondary" : "outline"}
            size="sm"
            onClick={handleSetOut}
            className="text-xs font-semibold px-2 py-1 h-8"
          >
            Out ] {outMarker ? formatTime(outMarker, zone) : ""}
          </Button>
          {(inMarker || outMarker) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearMarkers}
              aria-label="Clear markers"
              className="text-xs font-normal text-destructive hover:text-destructive h-8 px-2"
            >
              {TIMELINE_COPY.MARKER_CLEAR}
            </Button>
          )}
        </div>

        {/* Legend */}
        <TimelineLegend />

        {/* Zoom Level Selector */}
        <ToggleGroup
          type="single"
          value={zoomLevel}
          onValueChange={(val) => {
            if (val) onZoomChange(val as ZoomLevel);
          }}
          variant="outline"
          size="sm"
        >
          {ZOOM_LEVELS.map((level) => (
            <ToggleGroupItem
              key={level}
              value={level}
              aria-label={`Zoom to ${level}`}
              className="text-xs font-semibold px-2 py-1"
            >
              {level}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      {/* Main Track & Axis */}
      <div
        ref={trackRef}
        role="slider"
        tabIndex={0}
        aria-label={TIMELINE_COPY.LABEL_TIMELINE}
        aria-valuemin={winStart.getTime()}
        aria-valuemax={winEnd.getTime()}
        aria-valuenow={currentTime.getTime()}
        aria-valuetext={formatTime(currentTime, zone)}
        onKeyDown={handleKeyDown}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onMouseLeave={() => {
          setHoverTime(null);
          setHoverPos(null);
          setHoverType(null);
        }}
        className="relative h-20 w-full rounded-md border border-border bg-card overflow-hidden cursor-pointer touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {/* Axis & Gridlines */}
        <div className="pointer-events-none absolute inset-x-0 top-4 h-8 border-y border-border/60 bg-muted/40" aria-hidden="true" />
        {ticks.map((tick, idx) => (
          <React.Fragment key={idx}>
            <div
              // dynamic-style: timeline axis gridline percentage position
              style={{ left: `${tick.pct}%` }}
              className="absolute top-0 bottom-6 w-[1px] bg-border pointer-events-none"
            />
            {tick.label && (
              <span
                // dynamic-style: timeline hour label percentage position
                style={{ left: `${tick.pct}%` }}
                className="pointer-events-none absolute bottom-1 pl-1 text-xs font-normal text-muted-foreground tabular-nums whitespace-nowrap"
              >
                {tick.label}
              </span>
            )}
          </React.Fragment>
        ))}

        {/* Retention Span */}
        {retention && (
          <div
            // dynamic-style: retention removed span percentage position and width
            style={{
              left: `${timeToPct(retention[0], windowRange)}%`,
              width: `${Math.max(0.2, timeToPct(retention[1], windowRange) - timeToPct(retention[0], windowRange))}%`,
            }}
            title={TIMELINE_COPY.TOOLTIP_RETENTION}
            className="absolute top-4 h-8 rounded-sm bg-input border-b-2 border-dotted border-foreground/60 opacity-80"
          />
        )}

        {/* Recorded Segments */}
        {segments.map((seg) => {
          const sPct = timeToPct(seg.start_time, windowRange);
          const ePct = timeToPct(seg.end_time, windowRange);
          const widthPct = Math.max(0.15, ePct - sPct);
          if (sPct > 100 || ePct < 0) return null;

          return (
            <div
              key={`seg-${seg.id}`}
              // dynamic-style: recorded footage segment percentage position and width
              style={{ left: `${sPct}%`, width: `${widthPct}%` }}
              title={`Segment #${seg.id}: ${formatTime(new Date(seg.start_time), zone)} - ${formatTime(new Date(seg.end_time), zone)}`}
              className="absolute top-4 h-8 rounded-sm bg-primary opacity-95"
            >
              {seg.is_protected && (
                <div className="absolute bottom-[-5px] left-0 right-0 h-1 rounded-full bg-foreground" />
              )}
            </div>
          );
        })}

        {/* Camera Outages */}
        {outages.map((outage) => {
          const sPct = timeToPct(outage.started_at, windowRange);
          const eTime = outage.ended_at ? new Date(outage.ended_at) : new Date();
          const ePct = timeToPct(eTime, windowRange);
          const widthPct = Math.max(0.2, ePct - sPct);
          if (sPct > 100 || ePct < 0) return null;

          return (
            <div
              key={`outage-${outage.id}`}
              // dynamic-style: outage span percentage position and width
              style={{ left: `${sPct}%`, width: `${widthPct}%` }}
              title={`Outage: ${outage.reason || "Camera disconnected"}`}
              className="absolute top-4 h-8 rounded-sm border border-warning text-warning overflow-hidden bg-background"
            >
              <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
                <rect width="100%" height="100%" fill="url(#outage-hatch)" />
              </svg>
            </div>
          );
        })}

        {/* Event Markers */}
        {events.map((evt) => {
          const pct = timeToPct(evt.start_time, windowRange);
          if (pct < 0 || pct > 100) return null;

          return (
            <div
              key={`evt-${evt.id}`}
              // dynamic-style: event diamond marker percentage position
              style={{ left: `${pct}%` }}
              title={`Event #${evt.id} (${evt.event_type})`}
              className="absolute top-2 -translate-x-1/2 flex flex-col items-center z-10 pointer-events-none"
            >
              <div className="h-2.5 w-2.5 rotate-45 bg-info border border-background" />
              {evt.is_locked && <Lock className="h-3 w-3 text-info mt-1" />}
            </div>
          );
        })}

        {/* In / Out Selection Range Band */}
        {inPct !== null && outPct !== null && inPct < outPct && (
          <div
            // dynamic-style: export selection range percentage position and width
            style={{ left: `${inPct}%`, width: `${outPct - inPct}%` }}
            className="absolute top-0 bottom-6 bg-selected/30 pointer-events-none z-10"
          >
            <div className="absolute top-0 bottom-0 left-0 w-1 bg-foreground" />
            <div className="absolute top-0 bottom-0 right-0 w-1 bg-foreground" />
          </div>
        )}

        {/* Hover Time & Span Indicator */}
        {hoverPos !== null && hoverTime && (
          <div
            // dynamic-style: hover indicator x position in pixels
            style={{ left: `${hoverPos}px` }}
            className="absolute top-0 bottom-6 w-[1px] bg-foreground/50 pointer-events-none z-20"
          >
            <div className="absolute bottom-2 -translate-x-1/2 rounded bg-card border border-border px-1.5 py-0.5 text-xs font-semibold text-foreground whitespace-nowrap shadow-sm">
              {formatTime(hoverTime, zone)} {hoverType && `• ${hoverType}`}
            </div>
          </div>
        )}

        {/* Playhead Line */}
        <div
          // dynamic-style: playhead line percentage position
          style={{ left: `${playheadPct}%` }}
          className="absolute top-0 bottom-6 w-0.5 bg-primary-foreground shadow-[0_0_0_1px_var(--foreground)] pointer-events-none z-30"
        >
          {/* Triangular head */}
          <div className="absolute top-0 left-[-5px] w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-t-[8px] border-t-foreground" />
        </div>
      </div>

      {/* Hidden Span Table for Screen Readers */}
      <table className="sr-only">
        <caption>{TIMELINE_COPY.TABLE_CAPTION}</caption>
        <thead>
          <tr>
            <th scope="col">{TIMELINE_COPY.TABLE_HEADER_START}</th>
            <th scope="col">{TIMELINE_COPY.TABLE_HEADER_END}</th>
            <th scope="col">{TIMELINE_COPY.TABLE_HEADER_DURATION}</th>
          </tr>
        </thead>
        <tbody>
          {segments.map((seg) => (
            <tr key={`sr-seg-${seg.id}`}>
              <td>{formatTime(new Date(seg.start_time), zone)}</td>
              <td>{formatTime(new Date(seg.end_time), zone)}</td>
              <td>{seg.duration_seconds}s</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Timeline;
