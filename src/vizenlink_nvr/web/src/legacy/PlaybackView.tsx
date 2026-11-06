import React, { useState, useEffect, useRef, useCallback } from "react";
import { TimelineCanvas, ZoomLevel, TimelineSegment, TimelineOutage, TimelineEvent } from "./TimelineCanvas";
import { TransportBar } from "./TransportBar";
import { ClipExportModal } from "./ClipExportModal";

import type { CameraOption } from "@/lib/types";
export type { CameraOption };

interface PlaybackViewProps {
  cameras: CameraOption[];
  initialCameraSerial?: string;
  initialTimestamp?: string;
  onClearInitialJump?: () => void;
  onOpenGallery?: () => void;
}

export const PlaybackView: React.FC<PlaybackViewProps> = ({
  cameras,
  initialCameraSerial,
  initialTimestamp,
  onClearInitialJump,
  onOpenGallery,
}) => {
  const [selectedSerial, setSelectedSerial] = useState<string>(() => {
    return initialCameraSerial || (cameras.length > 0 ? cameras[0].serial : "");
  });

  const [selectedDate, setSelectedDate] = useState<string>(() => {
    if (initialTimestamp) {
      return initialTimestamp.slice(0, 10);
    }
    const today = new Date();
    return today.toISOString().slice(0, 10);
  });

  const [recordedDays, setRecordedDays] = useState<Set<string>>(new Set());
  const [segments, setSegments] = useState<TimelineSegment[]>([]);
  const [outages, setOutages] = useState<TimelineOutage[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loadingTimeline, setLoadingTimeline] = useState(false);

  // Playback state
  const [currentTime, setCurrentTime] = useState<Date>(() => {
    if (initialTimestamp) {
      return new Date(initialTimestamp);
    }
    const d = new Date();
    return d;
  });
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isMuted, setIsMuted] = useState(true);
  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>("24h");

  // In / Out markers for export
  const [inMarker, setInMarker] = useState<Date | null>(null);
  const [outMarker, setOutMarker] = useState<Date | null>(null);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  // Export clip modal state
  const [isExporting, setIsExporting] = useState(false);
  const [exportTitle, setExportTitle] = useState("");
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [snapshotToast, setSnapshotToast] = useState<string | null>(null);

  // Video DOM element
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeSegment, setActiveSegment] = useState<TimelineSegment | null>(null);

  // Handle initialJump from props
  useEffect(() => {
    if (initialCameraSerial) {
      setSelectedSerial(initialCameraSerial);
    }
    if (initialTimestamp) {
      setSelectedDate(initialTimestamp.slice(0, 10));
      setCurrentTime(new Date(initialTimestamp));
      if (onClearInitialJump) onClearInitialJump();
    }
  }, [initialCameraSerial, initialTimestamp, onClearInitialJump]);

  // Fetch calendar days with recordings for current month
  const fetchRecordedDays = useCallback(async () => {
    if (!selectedSerial) return;
    const parts = selectedDate.split("-");
    const year = parseInt(parts[0], 10);
    const month = parseInt(parts[1], 10);

    try {
      const res = await fetch(`/api/v1/playback/days?camera_serial=${selectedSerial}&year=${year}&month=${month}`);
      if (res.ok) {
        const data = await res.json();
        setRecordedDays(new Set(data.days));
      }
    } catch {
      // Ignore background failure
    }
  }, [selectedSerial, selectedDate]);

  useEffect(() => {
    fetchRecordedDays();
  }, [fetchRecordedDays]);

  // Fetch 24-hour timeline data for selected day
  const fetchTimeline = useCallback(async () => {
    if (!selectedSerial) return;
    setLoadingTimeline(true);
    const startIso = `${selectedDate}T00:00:00Z`;
    const endIso = `${selectedDate}T23:59:59.999Z`;

    try {
      const res = await fetch(
        `/api/v1/playback/timeline?camera_serial=${selectedSerial}&start_time=${startIso}&end_time=${endIso}`
      );
      if (res.ok) {
        const data = await res.json();
        setSegments(data.segments);
        setOutages(data.outages);
        setEvents(data.events);
      }
    } catch {
      // Ignore network errors
    } finally {
      setLoadingTimeline(false);
    }
  }, [selectedSerial, selectedDate]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  // Find active segment covering target time, or next available segment if in a gap
  const findCoveringOrNextSegment = useCallback(
    (target: Date): { covering: TimelineSegment | null; next: TimelineSegment | null } => {
      const targetMs = target.getTime();
      let covering: TimelineSegment | null = null;
      let next: TimelineSegment | null = null;

      for (const seg of segments) {
        const sMs = new Date(seg.start_time).getTime();
        const eMs = new Date(seg.end_time).getTime();

        if (targetMs >= sMs && targetMs <= eMs) {
          covering = seg;
          break;
        }
        if (sMs > targetMs) {
          if (!next || sMs < new Date(next.start_time).getTime()) {
            next = seg;
          }
        }
      }
      return { covering, next };
    },
    [segments]
  );

  // Sync active segment when currentTime changes
  const syncPlaybackPosition = useCallback(
    (target: Date, autoPlay: boolean = false) => {
      const { covering, next } = findCoveringOrNextSegment(target);

      if (covering) {
        setActiveSegment(covering);
        setCurrentTime(target);

        if (videoRef.current) {
          const segStartMs = new Date(covering.start_time).getTime();
          const targetOffsetSec = Math.max(0, (target.getTime() - segStartMs) / 1000);
          const srcUrl = `/api/v1/playback/segment/${covering.id}`;

          // If changing segments, update src
          if (!videoRef.current.src.endsWith(srcUrl)) {
            videoRef.current.src = srcUrl;
            videoRef.current.currentTime = targetOffsetSec;
            if (autoPlay) {
              videoRef.current.play().catch(() => setIsPlaying(false));
            }
          } else {
            // Same segment, just seek
            if (Math.abs(videoRef.current.currentTime - targetOffsetSec) > 0.5) {
              videoRef.current.currentTime = targetOffsetSec;
            }
          }
        }
      } else if (next) {
        // Gap skipping: advance smoothly to next segment start (PLAY-08 resilience)
        const nextStart = new Date(next.start_time);
        setActiveSegment(next);
        setCurrentTime(nextStart);

        if (videoRef.current) {
          videoRef.current.src = `/api/v1/playback/segment/${next.id}`;
          videoRef.current.currentTime = 0;
          if (autoPlay) {
            videoRef.current.play().catch(() => setIsPlaying(false));
          }
        }
      } else {
        // No footage available forward
        setActiveSegment(null);
        setCurrentTime(target);
        if (videoRef.current) {
          videoRef.current.pause();
        }
        setIsPlaying(false);
      }
    },
    [findCoveringOrNextSegment]
  );

  // Handle Seek from timeline click/drag
  const handleSeek = (target: Date) => {
    syncPlaybackPosition(target, isPlaying);
  };

  // Video element event listeners
  const handleVideoTimeUpdate = () => {
    if (!videoRef.current || !activeSegment) return;
    const segStartMs = new Date(activeSegment.start_time).getTime();
    const currentMs = segStartMs + videoRef.current.currentTime * 1000;
    setCurrentTime(new Date(currentMs));
  };

  const handleVideoEnded = () => {
    // Current segment reached end: jump to next segment
    if (!activeSegment) return;
    const segEnd = new Date(activeSegment.end_time);
    syncPlaybackPosition(new Date(segEnd.getTime() + 100), true);
  };

  // Transport actions
  const handlePlayPause = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      if (!activeSegment) {
        // Jump to first segment if available
        if (segments.length > 0) {
          syncPlaybackPosition(new Date(segments[0].start_time), true);
          setIsPlaying(true);
        }
      } else {
        videoRef.current
          .play()
          .then(() => setIsPlaying(true))
          .catch(() => setIsPlaying(false));
      }
    }
  };

  const handleSkip = (seconds: number) => {
    const nextTime = new Date(currentTime.getTime() + seconds * 1000);
    syncPlaybackPosition(nextTime, isPlaying);
  };

  const handleRateChange = (rate: number) => {
    setPlaybackRate(rate);
    if (videoRef.current) {
      videoRef.current.playbackRate = rate;
    }
  };

  const handleToggleMute = () => {
    const nextMuted = !isMuted;
    setIsMuted(nextMuted);
    if (videoRef.current) {
      videoRef.current.muted = nextMuted;
    }
  };

  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  };

  // Capture video frame snapshot (LIVE-07, PLAY-07)
  const handleTakeSnapshot = async () => {
    if (!videoRef.current || videoRef.current.readyState < 2) {
      setSnapshotToast("Cannot capture frame: video not ready");
      return;
    }

    try {
      const video = videoRef.current;
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas 2D context unavailable");

      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const b64DataUrl = canvas.toDataURL("image/jpeg", 0.92);

      const title = `Snapshot ${selectedSerial} ${currentTime.toISOString()}`;
      const res = await fetch("/api/v1/playback/snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          camera_serial: selectedSerial,
          image_base64: b64DataUrl,
          title,
          captured_at: currentTime.toISOString(),
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      setSnapshotToast(`Snapshot saved to gallery successfully!`);
      setTimeout(() => setSnapshotToast(null), 4000);
    } catch (err: any) {
      setSnapshotToast(`Failed to capture snapshot: ${err.message}`);
      setTimeout(() => setSnapshotToast(null), 4000);
    }
  };

  // Trigger MP4 Clip Export (PLAY-06)
  const handleExecuteExport = async () => {
    if (!inMarker || !outMarker || inMarker >= outMarker) {
      setExportMessage("Please select valid In and Out markers (In must precede Out).");
      return;
    }

    setIsExporting(true);
    setExportMessage(null);
    try {
      const res = await fetch("/api/v1/playback/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          camera_serial: selectedSerial,
          start_time: inMarker.toISOString(),
          end_time: outMarker.toISOString(),
          title: exportTitle || `Clip ${selectedSerial} ${inMarker.toLocaleTimeString([], { hour12: false })}`,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const item = await res.json();
      setExportMessage(`Clip successfully exported! Saved as #${item.id} (${(item.file_size_bytes / 1024 / 1024).toFixed(1)} MB).`);
      setInMarker(null);
      setOutMarker(null);
      setExportTitle("");
    } catch (err: any) {
      setExportMessage(`Export failed: ${err.message}`);
    } finally {
      setIsExporting(false);
    }
  };

  const baseDate = new Date(`${selectedDate}T00:00:00`);
  const currentTimeFormatted = currentTime.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  return (
    <div
      ref={containerRef}
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#0b1329",
        color: "#f8fafc",
      }}
    >
      {/* Top Header Controls: Camera selector & Date picker */}
      <div
        style={{
          height: "52px",
          background: "#1e293b",
          borderBottom: "1px solid #334155",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          zIndex: 5,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {/* Camera Selector */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <label style={{ fontSize: "13px", fontWeight: 600, color: "#94a3b8" }}>Camera:</label>
            <select
              value={selectedSerial}
              onChange={(e) => setSelectedSerial(e.target.value)}
              style={{
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "4px",
                padding: "5px 10px",
                fontSize: "13px",
              }}
            >
              {cameras.map((c) => (
                <option key={c.serial} value={c.serial}>
                  {c.name} ({c.serial})
                </option>
              ))}
            </select>
          </div>

          {/* Date Picker */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <label style={{ fontSize: "13px", fontWeight: 600, color: "#94a3b8" }}>Date:</label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              style={{
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "4px",
                padding: "4px 8px",
                fontSize: "13px",
              }}
            />
            {recordedDays.has(selectedDate) && (
              <span
                style={{
                  fontSize: "11px",
                  background: "#065f46",
                  color: "#34d399",
                  padding: "2px 6px",
                  borderRadius: "4px",
                  fontWeight: 600,
                }}
              >
                ● Recorded Footage Available
              </span>
            )}
          </div>
        </div>

        {/* Action Link: View Gallery */}
        {onOpenGallery && (
          <button
            onClick={onOpenGallery}
            style={{
              background: "#334155",
              color: "#38bdf8",
              border: "1px solid #0284c7",
              borderRadius: "4px",
              padding: "5px 12px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            📂 View Media Gallery
          </button>
        )}
      </div>

      {/* Snapshot Toast notification */}
      {snapshotToast && (
        <div
          style={{
            position: "absolute",
            top: "64px",
            right: "24px",
            background: "#0284c7",
            color: "#ffffff",
            padding: "8px 16px",
            borderRadius: "6px",
            fontSize: "13px",
            fontWeight: 600,
            boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
            zIndex: 100,
          }}
        >
          {snapshotToast}
        </div>
      )}

      {/* Center Video Area */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#000000",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <video
          ref={videoRef}
          controls={false}
          muted={isMuted}
          onTimeUpdate={handleVideoTimeUpdate}
          onEnded={handleVideoEnded}
          style={{
            maxWidth: "100%",
            maxHeight: "100%",
            objectFit: "contain",
          }}
        />

        {/* Outage or Empty Footage Overlay */}
        {!activeSegment && !loadingTimeline && (
          <div
            style={{
              position: "absolute",
              textAlign: "center",
              color: "#94a3b8",
              background: "rgba(15, 23, 42, 0.85)",
              padding: "24px 32px",
              borderRadius: "8px",
              border: "1px solid #334155",
            }}
          >
            <div style={{ fontSize: "36px", marginBottom: "8px" }}>🎬</div>
            <div style={{ fontSize: "16px", fontWeight: 600, color: "#f8fafc" }}>
              No Recording At Selected Time
            </div>
            <div style={{ fontSize: "13px", color: "#64748b", marginTop: "4px" }}>
              Click on a green span on the timeline below to start playback.
            </div>
          </div>
        )}

        {/* Loading Spinner */}
        {loadingTimeline && (
          <div
            style={{
              position: "absolute",
              color: "#38bdf8",
              fontSize: "14px",
              fontWeight: 600,
            }}
          >
            Loading 24h timeline...
          </div>
        )}
      </div>

      {/* Transport Controls Bar */}
      <TransportBar
        isPlaying={isPlaying}
        onPlayPause={handlePlayPause}
        onSkip={handleSkip}
        playbackRate={playbackRate}
        onRateChange={handleRateChange}
        isMuted={isMuted}
        onToggleMute={handleToggleMute}
        onToggleFullscreen={handleToggleFullscreen}
        onTakeSnapshot={handleTakeSnapshot}
        onOpenExport={() => setIsExportModalOpen(true)}
        currentTimeFormatted={`${selectedDate} ${currentTimeFormatted}`}
        hasActiveSegment={activeSegment !== null}
      />

      {/* Interactive 24-Hour Timeline */}
      <TimelineCanvas
        baseDate={baseDate}
        currentTime={currentTime}
        onSeek={handleSeek}
        segments={segments}
        outages={outages}
        events={events}
        zoomLevel={zoomLevel}
        onZoomChange={setZoomLevel}
        inMarker={inMarker}
        outMarker={outMarker}
        onSetInMarker={() => setInMarker(currentTime)}
        onSetOutMarker={() => setOutMarker(currentTime)}
        onClearMarkers={() => {
          setInMarker(null);
          setOutMarker(null);
        }}
      />

      {/* Quick Export Drawer if markers set */}
      {inMarker && outMarker && (
        <div
          style={{
            background: "#1e293b",
            borderTop: "1px solid #0284c7",
            padding: "10px 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: "13px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ fontWeight: 600, color: "#38bdf8" }}>Clip Export:</span>
            <span>
              {inMarker.toLocaleTimeString([], { hour12: false })} →{" "}
              {outMarker.toLocaleTimeString([], { hour12: false })} (
              {Math.max(0, Math.round((outMarker.getTime() - inMarker.getTime()) / 1000))}s)
            </span>
            <input
              type="text"
              placeholder="Clip Title (optional)"
              value={exportTitle}
              onChange={(e) => setExportTitle(e.target.value)}
              style={{
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "4px",
                padding: "3px 8px",
                fontSize: "12px",
                width: "200px",
              }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            {exportMessage && (
              <span
                style={{
                  fontSize: "12px",
                  color: exportMessage.includes("failed") ? "#ef4444" : "#34d399",
                }}
              >
                {exportMessage}
              </span>
            )}
            <button
              onClick={handleExecuteExport}
              disabled={isExporting}
              style={{
                background: "#0284c7",
                color: "#ffffff",
                border: "none",
                borderRadius: "4px",
                padding: "6px 14px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: isExporting ? "wait" : "pointer",
              }}
            >
              {isExporting ? "Exporting..." : "Confirm Export"}
            </button>
            <button
              onClick={() => {
                setInMarker(null);
                setOutMarker(null);
                setExportMessage(null);
              }}
              style={{
                background: "transparent",
                color: "#94a3b8",
                border: "none",
                cursor: "pointer",
                fontSize: "13px",
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Full Clip Export Dialog */}
      <ClipExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        cameraSerial={selectedSerial}
        cameraName={cameras.find((c) => c.serial === selectedSerial)?.name}
        initialStartTime={inMarker || new Date(currentTime.getTime() - 60000)}
        initialEndTime={outMarker || currentTime}
        onExportSuccess={() => {
          setInMarker(null);
          setOutMarker(null);
        }}
        onNavigateToGallery={onOpenGallery}
      />
    </div>
  );
};
