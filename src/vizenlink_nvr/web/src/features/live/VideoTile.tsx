import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { WifiOff, AlertTriangle, ZoomIn, ZoomOut } from "lucide-react";
import { TilePlayer, type PlayerState, type StreamRole } from "@/services/player";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative } from "@/lib/time";
import type { ViewMode } from "@/stores/ui";
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@/components/ui/context-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "cn";
import { TileOverlay } from "./TileOverlay";
import { LIVE_COPY } from "./copy";
import { MAX_ZOOM, useDigitalZoom } from "./useDigitalZoom";

export const MANUAL_CLIP_PROMPT_INTERVAL_SECONDS = 30;
export const MANUAL_CLIP_MAX_SECONDS = 300;

interface VideoTileProps {
  serial: string;
  name: string;
  isRecording?: boolean;
  isMaximized?: boolean;
  lastSeenAt?: string | null;
  viewMode: ViewMode;
  onToggleMaximize: () => void;
  /** Old VMS channel number shown on the tile ("CH 3"). */
  channel?: number;
  /** Fill the grid cell instead of keeping a 16:9 box (Multiview fit-to-screen). */
  fill?: boolean;
  /** Extra hover actions (favourite, playback, settings) shown bottom-left. */
  actions?: React.ReactNode;
  /** Right-click menu items; receives the tile's own snapshot/clip/fullscreen actions. */
  renderMenu?: (tile: {
    snapshot: () => void;
    fullscreen: () => void;
    toggleClip: () => void;
    isRecordingClip: boolean;
  }) => React.ReactNode;
  /** Drag-to-swap between channels. */
  onDragStartTile?: () => void;
  onDropTile?: () => void;
  /** Whether the camera registry reports it online (enables live snapshot fallback when WebRTC is offline). */
  isOnline?: boolean;
  /** Corner button and the menu's "Full screen": the page decides what full screen means. */
  onFullscreen?: () => void;
  /** This camera currently fills the screen. */
  fullscreenActive?: boolean;
  /** Move the top-right badges inwards (the page shows its own button in that corner). */
  cornerInset?: boolean;
}

export const VideoTile: React.FC<VideoTileProps> = ({
  serial,
  name,
  isRecording = false,
  isMaximized = false,
  lastSeenAt,
  viewMode,
  onToggleMaximize,
  channel,
  fill = false,
  actions,
  renderMenu,
  onDragStartTile,
  onDropTile,
  isOnline = false,
  onFullscreen,
  fullscreenActive = false,
  cornerInset = false,
}) => {
  const [dragOver, setDragOver] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<TilePlayer | null>(null);

  const [playerState, setPlayerState] = useState<PlayerState>("connecting");
  const [isMuted, setIsMuted] = useState(true);
  const [snapLoaded, setSnapLoaded] = useState(false);
  const [snapTick, setSnapTick] = useState(0);

  useEffect(() => {
    setSnapLoaded(false);
    setSnapTick(0);
  }, [serial]);

  useEffect(() => {
    if (!isOnline || playerState === "live") return;
    const timer = window.setInterval(() => setSnapTick((t) => t + 1), 2500);
    return () => window.clearInterval(timer);
  }, [isOnline, playerState]);

  const effectiveState: PlayerState = playerState === "live" || (isOnline && snapLoaded) ? "live" : playerState;

  // Large views get the full-quality stream.
  const streamRole: StreamRole = isMaximized ? "main" : "sub";

  // Digital zoom is offered on the large view only, where the wheel is not needed for
  // scrolling and the main stream has the detail to zoom into.
  const zoomEnabled = isMaximized;
  const { zoom, zoomed, reset: resetZoom, zoomIn, zoomOut, panHandlers } = useDigitalZoom(containerRef, zoomEnabled);

  // Initialize and attach player
  useEffect(() => {
    const player = new TilePlayer({
      serial,
      stream: streamRole,
      onStateChange: (state) => {
        setPlayerState(state);
      },
    });
    playerRef.current = player;

    if (videoRef.current) {
      void player.attach(videoRef.current);
    }

    return () => {
      player.cleanup();
      playerRef.current = null;
    };
  }, [serial]);

  // Switch stream when maximize toggles
  useEffect(() => {
    if (playerRef.current) {
      void playerRef.current.switchStream(streamRole);
    }
  }, [streamRole]);

  // Keyboard: Enter enlarges, Esc goes back. F (full screen) is handled by the page.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter") {
      e.preventDefault();
      onToggleMaximize();
    } else if (isMaximized && e.key === "Escape") {
      e.preventDefault();
      onToggleMaximize();
    }
  };

  // Snapshots and manual clips are stored on the recorder and listed in the Gallery.
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const savingSnapshot = useRef(false);
  const [isManualRecording, setIsManualRecording] = useState(false);
  const [manualRecordSeconds, setManualRecordSeconds] = useState(0);
  const [showContinuePrompt, setShowContinuePrompt] = useState(false);
  const clipStartRef = useRef<Date | null>(null);
  const elapsedSecondsRef = useRef(0);
  const nextPromptAtRef = useRef(MANUAL_CLIP_PROMPT_INTERVAL_SECONDS);
  const savingClipRef = useRef(false);

  const handleStopManualClip = async () => {
    if (savingClipRef.current) return;
    const startTime = clipStartRef.current;
    setIsManualRecording(false);
    setShowContinuePrompt(false);
    setManualRecordSeconds(0);
    elapsedSecondsRef.current = 0;
    clipStartRef.current = null;
    if (!startTime) return;

    savingClipRef.current = true;
    const endTime = new Date(Math.max(Date.now(), startTime.getTime() + 1000));
    try {
      await apiFetch("/api/v1/playback/manual-clip", {
        method: "POST",
        body: {
          camera_serial: serial,
          start_time: startTime.toISOString(),
          end_time: endTime.toISOString(),
          title: `${name || serial} manual clip`,
        },
      });
      void queryClient.invalidateQueries({ queryKey: ["gallery"] });
      toast.success(`Manual clip of ${name || serial} saved to the Gallery`, {
        action: { label: "Open Gallery", onClick: () => void navigate("/gallery?tab=clips") },
      });
    } catch (error) {
      toast.error(`Manual clip not saved. ${error instanceof Error ? error.message : "Try again."}`);
    } finally {
      savingClipRef.current = false;
    }
  };

  const stopManualClipRef = useRef(handleStopManualClip);
  stopManualClipRef.current = handleStopManualClip;

  useEffect(() => {
    if (!isManualRecording) return;
    const timer = window.setInterval(() => {
      const next = elapsedSecondsRef.current + 1;
      elapsedSecondsRef.current = next;
      setManualRecordSeconds(next);
      if (next >= MANUAL_CLIP_MAX_SECONDS) {
        void stopManualClipRef.current();
      } else if (next >= nextPromptAtRef.current) {
        setShowContinuePrompt(true);
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isManualRecording]);

  const handleStartManualClip = () => {
    if (savingClipRef.current || isManualRecording) return;
    elapsedSecondsRef.current = 0;
    clipStartRef.current = new Date();
    nextPromptAtRef.current = MANUAL_CLIP_PROMPT_INTERVAL_SECONDS;
    setManualRecordSeconds(0);
    setShowContinuePrompt(false);
    setIsManualRecording(true);
  };

  const handleContinueManualClip = () => {
    nextPromptAtRef.current = elapsedSecondsRef.current + MANUAL_CLIP_PROMPT_INTERVAL_SECONDS;
    setShowContinuePrompt(false);
  };

  const handleToggleManualRecord = () => {
    if (isManualRecording) {
      void handleStopManualClip();
    } else {
      handleStartManualClip();
    }
  };

  const handleSnapshot = async () => {
    if (savingSnapshot.current) return;
    savingSnapshot.current = true;
    const capturedAt = new Date();
    try {
      const canvas = document.createElement("canvas");
      const video = videoRef.current;
      let source: CanvasImageSource;
      if (video && video.videoWidth > 0 && playerState === "live") {
        source = video;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
      } else {
        // No live video frames in the browser: take the picture straight from the camera.
        const response = await fetch(`/api/v1/cameras/${encodeURIComponent(serial)}/snapshot?profile=high&t=${capturedAt.getTime()}`, { credentials: "same-origin" });
        if (!response.ok) throw new Error("The camera did not return a picture.");
        const url = URL.createObjectURL(await response.blob());
        try {
          const image = new Image();
          await new Promise<void>((resolve, reject) => {
            image.onload = () => resolve();
            image.onerror = () => reject(new Error("The camera picture could not be read."));
            image.src = url;
          });
          source = image;
          canvas.width = image.naturalWidth || 1280;
          canvas.height = image.naturalHeight || 720;
          canvas.getContext("2d")?.drawImage(image, 0, 0, canvas.width, canvas.height);
        } finally {
          URL.revokeObjectURL(url);
        }
      }
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("This browser cannot capture the picture.");
      if (source === video) ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
      await apiFetch("/api/v1/playback/snapshot", {
        method: "POST",
        body: {
          camera_serial: serial,
          image_base64: canvas.toDataURL("image/jpeg", 0.92),
          title: `${name || serial} live snapshot`,
          captured_at: capturedAt.toISOString(),
        },
      });
      void queryClient.invalidateQueries({ queryKey: ["gallery"] });
      toast.success(`Snapshot of ${name || serial} saved to the Gallery`, {
        action: { label: "Open Gallery", onClick: () => void navigate("/gallery") },
      });
    } catch (error) {
      toast.error(`Snapshot not saved. ${error instanceof Error ? error.message : "Try again."}`);
    } finally {
      savingSnapshot.current = false;
    }
  };

  // A click on a button, link or badge inside the tile must never count as a
  // double-click on the picture or start a drag of the whole tile.
  const onChrome = (target: EventTarget | null) =>
    target instanceof Element && Boolean(target.closest("[data-video-chrome], button, a"));
  // dragstart reports the tile itself as its target, so where the press began is remembered here.
  const pressedOnChrome = useRef(false);

  const handleToggleMute = () => {
    if (videoRef.current) {
      videoRef.current.muted = !videoRef.current.muted;
      setIsMuted(videoRef.current.muted);
    }
  };

  const handleRetry = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (playerRef.current) {
      playerRef.current.retryNow();
    }
  };

  const tile = (
    <div
      ref={containerRef}
      role="group"
      aria-label={`${name}, ${effectiveState}`}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      // Double-click puts a zoomed picture back first; only then does it leave the large view.
      onDoubleClick={(e) => {
        if (onChrome(e.target)) return;
        if (zoomed) resetZoom();
        else onToggleMaximize();
      }}
      {...panHandlers}
      onPointerDownCapture={(e) => { pressedOnChrome.current = onChrome(e.target); }}
      draggable={Boolean(onDragStartTile) && !zoomed}
      onDragStart={(e) => {
        // Pressing a tile button with a slightly moving mouse used to start a drag and swallow the click.
        if (!onDragStartTile || pressedOnChrome.current || onChrome(e.target)) {
          e.preventDefault();
          return;
        }
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", serial);
        onDragStartTile();
      }}
      onDragOver={(e) => {
        if (!onDropTile) return;
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        if (!onDropTile) return;
        e.preventDefault();
        setDragOver(false);
        onDropTile();
      }}
      className={cn(
        "dark relative flex w-full items-center justify-center overflow-hidden rounded-lg border border-border bg-video-bg group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        fill ? "h-full min-h-0" : "aspect-video",
        zoomed && "cursor-grab touch-none active:cursor-grabbing",
        dragOver && "ring-2 ring-primary"
      )}
    >
      {/* Video Element */}
      <video
        ref={videoRef}
        className="h-full w-full object-contain"
        // dynamic-style: digital zoom pans and scales the picture inside the tile.
        style={zoomed ? { transform: `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.scale})` } : undefined}
        muted={isMuted}
        playsInline
        autoPlay
      />

      {/* Live snapshot fallback when simulated/online camera has no WebRTC session */}
      {isOnline && playerState !== "live" && (
        <img
          src={`/api/v1/cameras/${encodeURIComponent(serial)}/snapshot?profile=${streamRole === "main" ? "high" : "low"}&t=${snapTick}`}
          alt=""
          onLoad={() => setSnapLoaded(true)}
          onError={() => setSnapLoaded(false)}
          className={cn(
            "pointer-events-none absolute inset-0 h-full w-full object-contain transition-opacity duration-200",
            snapLoaded ? "opacity-100" : "opacity-0"
          )}
          // dynamic-style: digital zoom pans and scales the snapshot fallback inside the tile.
          style={zoomed ? { transform: `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.scale})` } : undefined}
        />
      )}

      {/* State: Connecting */}
      {effectiveState === "connecting" && (
        <div className="absolute inset-0 z-0 flex flex-col items-center justify-center bg-video-bg">
          <Skeleton className="absolute inset-0 bg-video-overlay/40" />
          <Spinner className="h-6 w-6 text-video-fg z-10" />
        </div>
      )}

      {/* State: Offline */}
      {effectiveState === "offline" && (
        <div className="absolute inset-0 z-0 flex flex-col items-center justify-center gap-2 bg-video-bg p-4 text-center">
          <WifiOff className="h-6 w-6 text-offline" />
          <span className="text-sm font-semibold text-video-fg">
            {LIVE_COPY.OFFLINE_BADGE}
          </span>
          {lastSeenAt && (
            <span className="text-xs font-normal text-video-fg/80">
              {LIVE_COPY.LAST_SEEN(formatRelative(lastSeenAt))}
            </span>
          )}
        </div>
      )}

      {/* State: Error */}
      {effectiveState === "error" && (
        <div className="absolute inset-0 z-0 flex flex-col items-center justify-center gap-2 bg-video-bg p-4 text-center">
          <AlertTriangle className="h-6 w-6 text-destructive" />
          <span className="text-sm font-semibold text-video-fg">
            {LIVE_COPY.STREAM_ERROR_MESSAGE}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={handleRetry}
            className="mt-2 text-xs font-semibold bg-video-overlay text-video-fg hover:bg-video-overlay/80 hover:text-video-fg border-border"
          >
            {LIVE_COPY.RETRY_STREAM_ACTION}
          </Button>
        </div>
      )}

      {/* Overlays */}
      <TileOverlay
        name={name}
        serial={serial}
        state={effectiveState}
        isRecording={isRecording}
        isManualRecording={isManualRecording}
        manualRecordSeconds={manualRecordSeconds}
        isMuted={isMuted}
        isMaximized={isMaximized}
        stream={streamRole}
        viewMode={viewMode}
        onSnapshot={() => void handleSnapshot()}
        onToggleManualRecord={handleToggleManualRecord}
        onToggleMute={handleToggleMute}
        onToggleMaximize={onToggleMaximize}
        onToggleFullscreen={onFullscreen}
        isFullscreenActive={fullscreenActive}
        cornerInset={cornerInset}
        channel={channel}
      />

      {zoomEnabled && (effectiveState === "live" || zoomed) && (
        <div
          data-video-chrome
          role="group"
          aria-label="Digital zoom"
          className={cn(
            "absolute bottom-12 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-lg bg-video-overlay/80 p-1 text-video-fg transition-opacity duration-150",
            // Always shown while zoomed so the way back is never hidden.
            zoomed ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100"
          )}
          onDoubleClick={(e) => e.stopPropagation()}
        >
          <Button variant="ghost" size="icon" className="size-8 text-video-fg hover:bg-video-overlay hover:text-video-fg" aria-label="Zoom out" disabled={!zoomed} onClick={zoomOut}>
            <ZoomOut className="size-4" />
          </Button>
          <button
            type="button"
            className="min-w-12 rounded-md px-2 py-1 text-xs font-semibold tabular-nums hover:bg-video-overlay disabled:opacity-60"
            aria-label={zoomed ? `Zoom ${zoom.scale.toFixed(1)} times, reset zoom` : "Zoom 1 times"}
            disabled={!zoomed}
            onClick={resetZoom}
          >
            {zoom.scale.toFixed(1)}×
          </button>
          <Button variant="ghost" size="icon" className="size-8 text-video-fg hover:bg-video-overlay hover:text-video-fg" aria-label="Zoom in" disabled={zoom.scale >= MAX_ZOOM} onClick={zoomIn}>
            <ZoomIn className="size-4" />
          </Button>
        </div>
      )}

      {actions && (
        <div data-video-chrome className="absolute bottom-2 left-2 z-20 flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100">
          {actions}
        </div>
      )}
    </div>
  );

  const content = (
    <>
      {renderMenu ? (
        <ContextMenu>
          <ContextMenuTrigger asChild>{tile}</ContextMenuTrigger>
          <ContextMenuContent aria-label={`${name} actions`}>
            {renderMenu({
              snapshot: () => void handleSnapshot(),
              fullscreen: () => (onFullscreen ?? onToggleMaximize)(),
              toggleClip: handleToggleManualRecord,
              isRecordingClip: isManualRecording,
            })}
          </ContextMenuContent>
        </ContextMenu>
      ) : (
        tile
      )}

      <AlertDialog open={showContinuePrompt}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{LIVE_COPY.CLIP_PROMPT_TITLE}</AlertDialogTitle>
            <AlertDialogDescription>
              {LIVE_COPY.CLIP_PROMPT_DESCRIPTION(name || serial, manualRecordSeconds)}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => void handleStopManualClip()}>
              {LIVE_COPY.CLIP_PROMPT_STOP}
            </AlertDialogCancel>
            <AlertDialogAction onClick={handleContinueManualClip}>
              {LIVE_COPY.CLIP_PROMPT_CONTINUE}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );

  return content;
};
