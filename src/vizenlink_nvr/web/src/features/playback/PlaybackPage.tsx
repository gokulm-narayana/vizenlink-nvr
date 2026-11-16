import React, { useRef, useState, useMemo, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { useAuthStatus, useCameras } from "@/lib/queries";
import { useSiteTimeZone, zonedDayStart } from "@/lib/time";
import { toIsoDate, type TimelineSegment, type ZoomLevel } from "@/lib/timeline";
import { cn } from "cn";
import { Timeline } from "./timeline/Timeline";
import { useTimeline, useCameraRetention, useRecordedDays, useSaveSnapshot } from "./api";
import { usePlaybackEngine } from "./usePlaybackEngine";
import { PLAYBACK_COPY } from "./copy";
import { PlaybackToolbar } from "./PlaybackToolbar";
import { TransportBar } from "./TransportBar";
import { ClipExportDialog } from "./ClipExportDialog";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Film, Loader2, ZoomIn, ZoomOut } from "lucide-react";
import { MAX_ZOOM, useDigitalZoom } from "@/features/live/useDigitalZoom";

function findSegmentAt(segments: TimelineSegment[], instantMs: number) {
  return segments.find((s) => new Date(s.start_time).getTime() <= instantMs && instantMs < new Date(s.end_time).getTime());
}

interface SyncCameraTileProps {
  serial: string;
  name: string;
  channelIndex: number;
  isFocused: boolean;
  day: string;
  zone: string;
  currentTime: Date;
  isPlaying: boolean;
  playbackRate: number;
  isMuted: boolean;
  onSelectSingleView: () => void;
}

const SyncCameraTile: React.FC<SyncCameraTileProps> = ({
  serial,
  name,
  channelIndex,
  isFocused,
  day,
  zone,
  currentTime,
  isPlaying,
  playbackRate,
  isMuted,
  onSelectSingleView,
}) => {
  const { data, isPending, isError } = useTimeline(serial, day, zone);
  const video = useRef<HTMLVideoElement>(null);
  const [videoError, setVideoError] = useState(false);
  const segment = findSegmentAt(data?.segments || [], currentTime.getTime());

  const latestRef = useRef({ currentTime, isPlaying, playbackRate, segment });
  latestRef.current = { currentTime, isPlaying, playbackRate, segment };

  const syncTile = useCallback(() => {
    const el = video.current;
    const { currentTime: t, isPlaying: playing, playbackRate: rate, segment: seg } = latestRef.current;
    if (!el || !seg) return;
    const offset = Math.max(0, (t.getTime() - new Date(seg.start_time).getTime()) / 1000);
    if (el.readyState >= 1 && Math.abs(el.currentTime - offset) > 0.4) {
      el.currentTime = offset;
    }
    el.playbackRate = rate;
    if (playing) {
      if (el.paused) void el.play()?.catch(() => setVideoError(true));
    } else if (!el.paused) {
      el.pause();
    }
  }, []);

  useEffect(() => {
    syncTile();
  }, [currentTime, isPlaying, playbackRate, segment?.id, syncTile]);

  useEffect(() => {
    setVideoError(false);
  }, [segment?.id]);

  return (
    <button
      type="button"
      onClick={onSelectSingleView}
      aria-label={`Open ${name} in single view`}
      className={cn(
        "group relative flex h-full min-h-0 w-full items-center justify-center overflow-hidden rounded-md border bg-video-bg text-left text-video-fg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        isFocused ? "border-primary ring-2 ring-primary/60" : "border-border hover:border-primary/60"
      )}
    >
      <video
        ref={video}
        src={segment ? `/api/v1/playback/segment/${segment.id}` : undefined}
        playsInline
        muted={isMuted || !isFocused}
        onLoadedMetadata={syncTile}
        onCanPlay={syncTile}
        onError={() => setVideoError(true)}
        className="h-full w-full object-contain"
      />

      <div className="pointer-events-none absolute inset-x-2 top-2 z-10 flex items-center justify-between gap-2">
        <span className="truncate rounded bg-video-overlay/85 px-2 py-1 text-xs font-semibold tabular-nums text-video-fg">
          CH {String(channelIndex + 1).padStart(2, "0")} · {name}
        </span>
        <span className={cn("shrink-0 rounded px-2 py-1 text-xs font-semibold uppercase", isFocused ? "bg-primary text-primary-foreground" : segment ? "bg-video-overlay/85 text-video-fg" : "bg-video-overlay/85 text-video-fg/70")}>
          {isFocused ? "Focused" : segment ? "Synced" : "Gap"}
        </span>
      </div>

      <span className="pointer-events-none absolute bottom-2 left-2 z-10 rounded bg-video-overlay/85 px-2 py-1 text-xs font-semibold text-video-fg opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
        Single view
      </span>

      {isPending ? (
        <div className="absolute inset-0 flex items-center justify-center bg-video-bg/80">
          <Loader2 className="size-6 animate-spin text-primary" />
        </div>
      ) : !segment || videoError || isError ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-video-bg p-2 text-center text-video-fg/70">
          <Film className="size-6" />
          <span className="text-xs font-semibold">
            {isError ? PLAYBACK_COPY.loadError : videoError ? "Couldn't play clip" : PLAYBACK_COPY.noFootageAtTime}
          </span>
        </div>
      ) : null}
    </button>
  );
};

export function PlaybackPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const zone = useSiteTimeZone();
  const { data: rawCameras = [] } = useCameras(true);

  const cameraParam = searchParams.get("camera");
  const tParam = searchParams.get("t");

  const selectedSerial = useMemo(() => {
    if (cameraParam && rawCameras.some((c) => c.serial === cameraParam)) {
      return cameraParam;
    }
    return rawCameras.length > 0 ? rawCameras[0].serial : "";
  }, [cameraParam, rawCameras]);

  const initialInstant = useMemo(() => {
    if (tParam) {
      const parsed = new Date(tParam);
      if (!isNaN(parsed.getTime())) return parsed;
    }
    return new Date();
  }, [tParam]);

  const [selectedDay, setSelectedDay] = useState<string>(() =>
    toIsoDate(initialInstant, zone)
  );

  // Sync selectedDay if tParam changes externally
  useEffect(() => {
    if (tParam) {
      const parsed = new Date(tParam);
      if (!isNaN(parsed.getTime())) {
        setSelectedDay(toIsoDate(parsed, zone));
      }
    }
  }, [tParam, zone]);

  const [yearNum, monthNum] = useMemo(() => {
    const parts = selectedDay.split("-").map(Number);
    return [parts[0] || 2026, parts[1] || 11];
  }, [selectedDay]);

  const { data: recordedDays = [] } = useRecordedDays(selectedSerial, yearNum, monthNum);

  const {
    data: timelineData,
    isLoading: loadingTimeline,
    isError: timelineError,
    refetch: refetchTimeline,
  } = useTimeline(selectedSerial, selectedDay, zone);

  const retentionDays = useCameraRetention(selectedSerial);

  const segments = timelineData?.segments || [];
  const outages = timelineData?.outages || [];
  const events = timelineData?.events || [];

  const videoRef = useRef<HTMLVideoElement>(null);
  const videoStageRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleTimeChange = useCallback((newTime: Date) => {
    // URL sync
  }, []);

  const engine = usePlaybackEngine({
    videoRef,
    segments,
    initialTime: initialInstant,
    onTimeChange: handleTimeChange,
  });

  const autoSeekedKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (tParam || !selectedSerial || loadingTimeline || segments.length === 0) return;
    const key = `${selectedSerial}:${selectedDay}`;
    if (autoSeekedKeyRef.current === key) return;
    autoSeekedKeyRef.current = key;
    const tMs = engine.currentTime.getTime();
    const covered = segments.some((s) => tMs >= new Date(s.start_time).getTime() && tMs < new Date(s.end_time).getTime());
    if (!covered) {
      const latestSeg = segments[segments.length - 1];
      const latestStart = new Date(latestSeg.start_time).getTime();
      const latestEnd = new Date(latestSeg.end_time).getTime();
      const target = new Date(Math.min(Math.max(latestStart, latestStart + 2000), latestEnd - 1000));
      engine.seek(target, false);
    }
  }, [tParam, selectedSerial, selectedDay, loadingTimeline, segments, engine.currentTime, engine.seek]);

  const role = useAuthStatus().data?.user?.role;
  const client = useQueryClient();
  const active = segments.find(segment => segment.id === engine.activeSegment?.id);
  const manuallyLocked = active?.protection_reason?.split(",").some(reason => reason.startsWith("evidence_lock:"));
  const lock = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "lock" | "unlock" }) =>
      apiFetch(`/api/v1/playback/segments/${id}/${action}`, { method: "POST" }),
    onSuccess: async (_, { action }) => {
      await client.invalidateQueries({ queryKey: ["playback", "timeline"] });
      toast.success(action === "lock" ? "Footage locked against retention cleanup" : "Manual footage lock removed");
    },
    onError: (error) => toast.error(error.message),
  });

  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>("24h");
  const [inMarker, setInMarker] = useState<Date | null>(null);
  const [outMarker, setOutMarker] = useState<Date | null>(null);
  const [isExportDialogOpen, setIsExportDialogOpen] = useState(false);

  const isSyncMode = searchParams.get("mode") === "sync";
  const [syncGridSize, setSyncGridSize] = useState<4 | 6>(4);
  const { zoom, zoomed, reset: resetZoom, zoomIn, zoomOut, panHandlers } = useDigitalZoom(
    videoStageRef,
    !isSyncMode
  );

  useEffect(() => {
    resetZoom();
  }, [selectedSerial, isSyncMode, resetZoom]);

  const syncCameras = useMemo(() => {
    const isCamOnline = (c: { is_online?: boolean; state?: string }) =>
      c.is_online !== false && (!c.state || c.state === "active" || c.state === "online");
    const ordered = [
      ...rawCameras.filter((c) => c.serial === selectedSerial),
      ...rawCameras.filter((c) => c.serial !== selectedSerial && isCamOnline(c)),
      ...rawCameras.filter((c) => c.serial !== selectedSerial && !isCamOnline(c)),
    ];
    return ordered.slice(0, syncGridSize);
  }, [rawCameras, selectedSerial, syncGridSize]);

  const handleViewModeChange = (mode: "single" | "sync") => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (mode === "sync") next.set("mode", "sync");
        else next.delete("mode");
        return next;
      },
      { replace: true }
    );
  };

  const handleCameraChange = (newSerial: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("camera", newSerial);
        next.set("t", engine.currentTime.toISOString());
        return next;
      },
      { replace: true }
    );
  };

  const handleSelectSyncTile = (serial: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("camera", serial);
        next.set("t", engine.currentTime.toISOString());
        next.delete("mode");
        return next;
      },
      { replace: true }
    );
  };

  const handleDayChange = (newDay: string) => {
    setSelectedDay(newDay);
    const dayStart = zonedDayStart(newDay, zone);
    setSearchParams(
      { camera: selectedSerial, t: dayStart.toISOString() },
      { replace: true }
    );
    engine.seek(dayStart, engine.isPlaying);
  };

  // Snapshot handling
  const { mutate: saveSnapshot, isPending: isSnapshotPending } = useSaveSnapshot();
  const [snapshotError, setSnapshotError] = useState<string | null>(null);

  const handleTakeSnapshot = useCallback(() => {
    if (!videoRef.current || videoRef.current.readyState < 2) {
      setSnapshotError(PLAYBACK_COPY.snapshotError);
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

      saveSnapshot(
        {
          camera_serial: selectedSerial,
          image_base64: b64DataUrl,
          title: `Snapshot ${selectedSerial} ${engine.currentTime.toISOString()}`,
          captured_at: engine.currentTime.toISOString(),
        },
        {
          onSuccess: () => {
            setSnapshotError(null);
            toast.success(PLAYBACK_COPY.snapshotSaved);
          },
          onError: () => {
            setSnapshotError(PLAYBACK_COPY.snapshotError);
          },
        }
      );
    } catch {
      setSnapshotError(PLAYBACK_COPY.snapshotError);
    }
  }, [engine.currentTime, saveSnapshot, selectedSerial]);

  const baseDate = useMemo(() => zonedDayStart(selectedDay, zone), [selectedDay, zone]);
  const [topOffset, setTopOffset] = useState(80);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const parentEl = el.parentElement;
    const shellInset = parentEl?.parentElement ?? null;
    const prevParentOverflow = parentEl?.style.overflow ?? "";
    const prevDocOverflow = document.documentElement.style.overflow;

    if (parentEl) {
      parentEl.style.overflow = "hidden";
      parentEl.scrollTop = 0;
    }
    document.documentElement.style.overflow = "hidden";

    const measure = () => {
      if (window.scrollY !== 0 || window.scrollX !== 0) {
        window.scrollTo(0, 0);
      }
      if (parentEl && parentEl.scrollTop !== 0) {
        parentEl.scrollTop = 0;
      }
      const top = Math.max(0, Math.round(el.getBoundingClientRect().top + window.scrollY));
      if (top > 0) setTopOffset(top);
    };

    measure();
    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            requestAnimationFrame(measure);
          })
        : null;
    if (ro) {
      if (parentEl) ro.observe(parentEl);
      if (shellInset) ro.observe(shellInset);
      ro.observe(document.body);
    }

    const mo =
      typeof MutationObserver !== "undefined" && shellInset
        ? new MutationObserver(() => {
            requestAnimationFrame(measure);
          })
        : null;
    if (mo && shellInset) {
      mo.observe(shellInset, { childList: true, subtree: true });
    }

    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, { passive: true });
    return () => {
      ro?.disconnect();
      mo?.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure);
      if (parentEl) parentEl.style.overflow = prevParentOverflow;
      document.documentElement.style.overflow = prevDocOverflow;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="flex min-h-0 w-full flex-col gap-2 overflow-hidden p-2"
      // dynamic-style: fit playback workspace to remaining viewport below header and any alert banner
      style={{ height: `calc(100dvh - ${topOffset + 8}px)` }}
    >
      {/* Top Toolbar */}
      <PlaybackToolbar
        cameras={rawCameras}
        selectedSerial={selectedSerial}
        onSelectCamera={handleCameraChange}
        selectedDay={selectedDay}
        onSelectDay={handleDayChange}
        recordedDays={recordedDays}
        currentTime={engine.currentTime}
        onSeek={(target) => engine.seek(target, engine.isPlaying)}
        zone={zone}
        viewMode={isSyncMode ? "sync" : "single"}
        onViewModeChange={handleViewModeChange}
        syncGridSize={syncGridSize}
        onSyncGridSizeChange={setSyncGridSize}
      />

      {/* Video Area */}
      <div
        ref={videoStageRef}
        {...(!isSyncMode ? panHandlers : {})}
        onDoubleClick={!isSyncMode && zoomed ? resetZoom : undefined}
        className={cn(
          "dark relative flex min-h-0 flex-1 w-full items-center justify-center overflow-hidden rounded-lg border border-border bg-video-bg",
          !isSyncMode && zoomed && "cursor-grab touch-none active:cursor-grabbing"
        )}
      >
        <video
          ref={videoRef}
          playsInline
          muted={engine.isMuted}
          onTimeUpdate={engine.handleTimeUpdate}
          onEnded={engine.handleEnded}
          // dynamic-style: digital zoom pans and scales the playback video inside the stage
          style={zoomed ? { transform: `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.scale})` } : undefined}
          className={isSyncMode ? "hidden" : "h-full w-full object-contain"}
        />

        {!isSyncMode && (
          <div
            data-video-chrome
            role="group"
            aria-label="Digital zoom"
            className="absolute bottom-2 right-2 z-20 flex items-center gap-1 rounded-lg border border-border bg-video-overlay/85 p-1 text-video-fg backdrop-blur-sm"
            onDoubleClick={(e) => e.stopPropagation()}
          >
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-video-fg hover:bg-video-overlay hover:text-video-fg"
              aria-label="Zoom out"
              disabled={!zoomed}
              onClick={zoomOut}
            >
              <ZoomOut className="size-4" />
            </Button>
            <button
              type="button"
              className="min-w-12 rounded-md px-2 py-1 text-xs font-semibold tabular-nums hover:bg-video-overlay disabled:opacity-70"
              aria-label={zoomed ? `Zoom ${zoom.scale.toFixed(1)} times, reset zoom` : "Zoom 1 times"}
              disabled={!zoomed}
              onClick={resetZoom}
            >
              {zoom.scale.toFixed(1)}×
            </button>
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-video-fg hover:bg-video-overlay hover:text-video-fg"
              aria-label="Zoom in"
              disabled={zoom.scale >= MAX_ZOOM}
              onClick={zoomIn}
            >
              <ZoomIn className="size-4" />
            </Button>
          </div>
        )}

        {isSyncMode && syncCameras.length > 0 && (
          <div
            className={cn(
              "grid h-full w-full min-h-0 gap-2 p-2",
              syncGridSize === 4 ? "grid-cols-1 sm:grid-cols-2 sm:grid-rows-2" : "grid-cols-2 lg:grid-cols-3 lg:grid-rows-2"
            )}
          >
            {syncCameras.map((cam, idx) => (
              <SyncCameraTile
                key={cam.serial}
                serial={cam.serial}
                name={cam.name}
                channelIndex={idx}
                isFocused={cam.serial === selectedSerial}
                day={selectedDay}
                zone={zone}
                currentTime={engine.currentTime}
                isPlaying={engine.isPlaying}
                playbackRate={engine.playbackRate}
                isMuted={engine.isMuted}
                onSelectSingleView={() => handleSelectSyncTile(cam.serial)}
              />
            ))}
          </div>
        )}

        {/* Loading overlay */}
        {loadingTimeline && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-video-bg/80 text-foreground">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="text-sm font-semibold">{PLAYBACK_COPY.loadingTimeline}</span>
          </div>
        )}

        {/* Error overlay */}
        {timelineError && !loadingTimeline && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-4 bg-video-bg/85">
            <Alert variant="destructive" className="max-w-md" role="alert">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="flex flex-col gap-2">
                <span>{PLAYBACK_COPY.loadError}</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => refetchTimeline()}
                  className="self-start"
                >
                  {PLAYBACK_COPY.retryPlayback}
                </Button>
              </AlertDescription>
            </Alert>
          </div>
        )}

        {/* Empty day overlay */}
        {!loadingTimeline && !timelineError && !isSyncMode && segments.length === 0 && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 p-4 text-center bg-video-bg/85 text-muted-foreground">
            <Film className="h-10 w-10 text-muted-foreground/60" />
            <p className="text-sm font-semibold text-foreground">{PLAYBACK_COPY.emptyDay}</p>
          </div>
        )}

        {/* No footage in gap overlay */}
        {!loadingTimeline && !timelineError && !isSyncMode && segments.length > 0 && !engine.hasActiveSegment && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 p-4 text-center bg-video-bg/75 text-muted-foreground">
            <Film className="h-8 w-8 text-muted-foreground/60" />
            <p className="text-sm font-semibold text-foreground">{PLAYBACK_COPY.noFootageAtTime}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-1 bg-video-overlay text-video-fg hover:bg-video-overlay/80 hover:text-video-fg"
              onClick={() => engine.seek(new Date(segments[segments.length - 1].start_time), engine.isPlaying)}
            >
              Jump to latest footage
            </Button>
          </div>
        )}
      </div>

      {/* Transport Controls Bar */}
      <TransportBar
        isPlaying={engine.isPlaying}
        onPlayPause={engine.togglePlay}
        onSkip={engine.skip}
        playbackRate={engine.playbackRate}
        onRateChange={engine.setPlaybackRate}
        isMuted={engine.isMuted}
        onToggleMute={engine.toggleMute}
        onTakeSnapshot={handleTakeSnapshot}
        isSnapshotPending={isSnapshotPending}
        snapshotError={snapshotError}
        onRetrySnapshot={handleTakeSnapshot}
        onDismissSnapshotError={() => setSnapshotError(null)}
        onMarkIn={() => setInMarker(engine.currentTime)}
        onMarkOut={() => setOutMarker(engine.currentTime)}
        inMarker={inMarker}
        outMarker={outMarker}
        onOpenExport={() => setIsExportDialogOpen(true)}
        currentTime={engine.currentTime}
        zone={zone}
        hasActiveSegment={engine.hasActiveSegment}
        containerRef={containerRef}
        extraActions={
          (role === "owner" || role === "operator") && active ? (
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs font-semibold"
              disabled={lock.isPending}
              onClick={() => lock.mutate({ id: active.id, action: manuallyLocked ? "unlock" : "lock" })}
            >
              {lock.isPending ? "Saving…" : manuallyLocked ? "Unlock this segment" : "Lock this segment"}
            </Button>
          ) : undefined
        }
      />

      {/* Clip Export Dialog */}
      <ClipExportDialog
        open={isExportDialogOpen}
        onOpenChange={setIsExportDialogOpen}
        cameraSerial={selectedSerial}
        cameraName={rawCameras.find((c) => c.serial === selectedSerial)?.name}
        inMarker={inMarker}
        outMarker={outMarker}
        zone={zone}
        onExportSuccess={() => {
          setInMarker(null);
          setOutMarker(null);
        }}
      />

      {/* Timeline Card */}
      <div className="w-full">
        <Timeline
          baseDate={baseDate}
          currentTime={engine.currentTime}
          onSeek={(target) => engine.seek(target, engine.isPlaying)}
          segments={segments}
          outages={outages}
          events={events}
          zoomLevel={zoomLevel}
          onZoomChange={setZoomLevel}
          inMarker={inMarker}
          outMarker={outMarker}
          onSetInMarker={() => setInMarker(engine.currentTime)}
          onSetOutMarker={() => setOutMarker(engine.currentTime)}
          onClearMarkers={() => {
            setInMarker(null);
            setOutMarker(null);
          }}
          zone={zone}
          retentionDays={retentionDays}
          onTogglePlay={engine.togglePlay}
          onToggleMute={engine.toggleMute}
          onMarkIn={() => setInMarker(engine.currentTime)}
          onMarkOut={() => setOutMarker(engine.currentTime)}
        />
      </div>
    </div>
  );
}