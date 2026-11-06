import React, { useRef, useState, useMemo, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { useCameras } from "@/lib/queries";
import { useSiteTimeZone, zonedDayStart } from "@/lib/time";
import { toIsoDate, type ZoomLevel } from "@/lib/timeline";
import { Timeline } from "./timeline/Timeline";
import { useTimeline, useCameraRetention, useRecordedDays, useSaveSnapshot } from "./api";
import { usePlaybackEngine } from "./usePlaybackEngine";
import { PLAYBACK_COPY } from "./copy";
import { PlaybackToolbar } from "./PlaybackToolbar";
import { TransportBar } from "./TransportBar";
import { ClipExportDialog } from "./ClipExportDialog";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Film, Loader2 } from "lucide-react";

export function PlaybackPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const zone = useSiteTimeZone();
  const { data: rawCameras = [] } = useCameras();

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

  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>("24h");
  const [inMarker, setInMarker] = useState<Date | null>(null);
  const [outMarker, setOutMarker] = useState<Date | null>(null);
  const [isExportDialogOpen, setIsExportDialogOpen] = useState(false);

  const handleCameraChange = (newSerial: string) => {
    setSearchParams(
      { camera: newSerial, t: engine.currentTime.toISOString() },
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

  return (
    <div ref={containerRef} className="flex flex-col h-full w-full p-2 gap-2 overflow-y-auto">
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
      />

      {/* Video Area */}
      <div className="dark relative flex aspect-video w-full max-h-[60dvh] items-center justify-center overflow-hidden rounded-lg border border-border bg-video-bg">
        <video
          ref={videoRef}
          playsInline
          muted={engine.isMuted}
          onTimeUpdate={engine.handleTimeUpdate}
          onEnded={engine.handleEnded}
          className="h-full w-full object-contain"
        />

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
        {!loadingTimeline && !timelineError && segments.length === 0 && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 p-4 text-center bg-video-bg/85 text-muted-foreground">
            <Film className="h-10 w-10 text-muted-foreground/60" />
            <p className="text-sm font-semibold text-foreground">{PLAYBACK_COPY.emptyDay}</p>
          </div>
        )}

        {/* No footage in gap overlay */}
        {!loadingTimeline && !timelineError && segments.length > 0 && !engine.hasActiveSegment && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 p-4 text-center bg-video-bg/75 text-muted-foreground">
            <Film className="h-8 w-8 text-muted-foreground/60" />
            <p className="text-sm font-semibold text-foreground">{PLAYBACK_COPY.noFootageAtTime}</p>
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
