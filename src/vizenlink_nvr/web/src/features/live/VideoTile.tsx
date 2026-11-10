import React, { useEffect, useRef, useState } from "react";
import { WifiOff, AlertTriangle } from "lucide-react";
import { TilePlayer, type PlayerState, type StreamRole } from "@/services/player";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative } from "@/lib/time";
import type { ViewMode } from "@/stores/ui";
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@/components/ui/context-menu";
import { cn } from "cn";
import { TileOverlay } from "./TileOverlay";
import { LIVE_COPY } from "./copy";

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
  /** Right-click menu items; receives the tile's own snapshot/fullscreen actions. */
  renderMenu?: (tile: { snapshot: () => void; fullscreen: () => void }) => React.ReactNode;
  /** Drag-to-swap between channels. */
  onDragStartTile?: () => void;
  onDropTile?: () => void;
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
}) => {
  const [dragOver, setDragOver] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<TilePlayer | null>(null);

  const [playerState, setPlayerState] = useState<PlayerState>("connecting");
  const [isMuted, setIsMuted] = useState(true);

  const streamRole: StreamRole = isMaximized ? "main" : "sub";

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

  // Handle keyboard events (Enter to maximize, F for fullscreen, Esc to restore)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter") {
      e.preventDefault();
      onToggleMaximize();
    } else if (isMaximized && (e.key === "f" || e.key === "F")) {
      e.preventDefault();
      if (!document.fullscreenElement) {
        void containerRef.current?.requestFullscreen();
      } else {
        void document.exitFullscreen();
      }
    } else if (isMaximized && e.key === "Escape") {
      e.preventDefault();
      onToggleMaximize();
    }
  };

  const handleSnapshot = () => {
    const video = videoRef.current;
    if (!video) return;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const url = canvas.toDataURL("image/jpeg", 0.92);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${name || serial}_${new Date().toISOString().replace(/[:.]/g, "-")}.jpg`;
        a.click();
      }
    } catch {
      // Ignore snapshot canvas security errors
    }
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      void containerRef.current?.requestFullscreen?.();
    } else {
      void document.exitFullscreen?.();
    }
  };

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
      aria-label={`${name}, ${playerState}`}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onDoubleClick={onToggleMaximize}
      draggable={Boolean(onDragStartTile)}
      onDragStart={(e) => {
        if (!onDragStartTile) return;
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
        dragOver && "ring-2 ring-primary"
      )}
    >
      {/* Video Element */}
      <video
        ref={videoRef}
        className="h-full w-full object-contain"
        muted={isMuted}
        playsInline
        autoPlay
      />

      {/* State: Connecting */}
      {playerState === "connecting" && (
        <div className="absolute inset-0 z-0 flex flex-col items-center justify-center bg-video-bg">
          <Skeleton className="absolute inset-0 bg-video-overlay/40" />
          <Spinner className="h-6 w-6 text-video-fg z-10" />
        </div>
      )}

      {/* State: Offline */}
      {playerState === "offline" && (
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
      {playerState === "error" && (
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
        state={playerState}
        isRecording={isRecording}
        isMuted={isMuted}
        isMaximized={isMaximized}
        stream={streamRole}
        viewMode={viewMode}
        onSnapshot={handleSnapshot}
        onToggleMute={handleToggleMute}
        onToggleMaximize={onToggleMaximize}
        channel={channel}
      />

      {actions && (
        <div className="absolute bottom-2 left-2 z-20 flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100">
          {actions}
        </div>
      )}
    </div>
  );

  if (!renderMenu) return tile;
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{tile}</ContextMenuTrigger>
      <ContextMenuContent aria-label={`${name} actions`}>
        {renderMenu({ snapshot: handleSnapshot, fullscreen: toggleFullscreen })}
      </ContextMenuContent>
    </ContextMenu>
  );
};
