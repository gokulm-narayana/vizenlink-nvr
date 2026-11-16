import React from "react";
import {
  Camera,
  Video,
  Square,
  Volume2,
  VolumeX,
  Maximize2,
  Minimize2,
  WifiOff,
} from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { PlayerState, StreamRole } from "@/services/player";
import type { ViewMode } from "@/stores/ui";
import { LIVE_COPY } from "./copy";

function formatClipSeconds(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

interface TileOverlayProps {
  name: string;
  serial: string;
  state: PlayerState;
  isRecording: boolean;
  isManualRecording?: boolean;
  manualRecordSeconds?: number;
  isMuted: boolean;
  isMaximized: boolean;
  stream: StreamRole;
  viewMode: ViewMode;
  onSnapshot: () => void;
  onToggleManualRecord?: () => void;
  onToggleMute: () => void;
  onToggleMaximize: () => void;
  /** The bottom-right button: real full screen for this camera. */
  onToggleFullscreen?: () => void;
  isFullscreenActive?: boolean;
  channel?: number;
  /** Leave the top-right corner free for a page-level button. */
  cornerInset?: boolean;
}

export const TileOverlay: React.FC<TileOverlayProps> = ({
  name,
  serial,
  state,
  isRecording,
  isManualRecording = false,
  manualRecordSeconds = 0,
  isMuted,
  isMaximized,
  stream,
  viewMode,
  onSnapshot,
  onToggleManualRecord,
  onToggleMute,
  onToggleMaximize,
  onToggleFullscreen,
  isFullscreenActive,
  channel,
  cornerInset = false,
}) => {
  const renderStateBadge = () => {
    switch (state) {
      case "live":
        return (
          <div className="flex items-center gap-1.5 rounded bg-video-overlay px-2 py-0.5 text-xs font-semibold text-video-fg">
            <span className="h-2 w-2 rounded-full bg-success" />
            <span>{LIVE_COPY.LIVE_BADGE}</span>
          </div>
        );
      case "connecting":
        return (
          <div className="flex items-center gap-1.5 rounded bg-video-overlay px-2 py-0.5 text-xs font-semibold text-video-fg">
            <Spinner className="h-3 w-3" />
            <span>{LIVE_COPY.CONNECTING_BADGE}</span>
          </div>
        );
      case "reconnecting":
      case "stalled":
        return (
          <div className="flex items-center gap-1.5 rounded bg-video-overlay px-2 py-0.5 text-xs font-semibold text-video-fg">
            <Spinner className="h-3 w-3" />
            <span>{LIVE_COPY.RECONNECTING_BADGE}</span>
          </div>
        );
      case "offline":
        return (
          <div className="flex items-center gap-1.5 rounded bg-video-overlay px-2 py-0.5 text-xs font-semibold text-video-fg">
            <WifiOff className="h-3.5 w-3.5 text-offline" />
            <span>{LIVE_COPY.OFFLINE_BADGE}</span>
          </div>
        );
      default:
        return null;
    }
  };

  // With a fullscreen handler the corner button means "full screen"; without one it keeps
  // the older "enlarge in grid" meaning.
  const fsActive = onToggleFullscreen ? Boolean(isFullscreenActive) : isMaximized;
  const fsLabel = onToggleFullscreen
    ? fsActive ? LIVE_COPY.EXIT_FULLSCREEN_LABEL : LIVE_COPY.FULLSCREEN_LABEL
    : isMaximized ? LIVE_COPY.MINIMIZE_LABEL : LIVE_COPY.MAXIMIZE_LABEL;

  return (
    <>
      {/* Top Left: Camera Name */}
      <div data-video-chrome className="absolute top-2 left-2 max-w-[55%] min-w-0 pointer-events-none z-10 flex items-center gap-1">
        {channel !== undefined && (
          <span className="shrink-0 rounded bg-primary px-2 py-0.5 text-xs font-semibold text-primary-foreground tabular-nums">
            CH {channel}
          </span>
        )}
        <div
          title={name}
          className="truncate rounded bg-video-overlay px-2 py-0.5 text-xs font-semibold text-video-fg"
        >
          {name}
        </div>
      </div>

      {/* Top Right: State & REC Badges */}
      <div data-video-chrome className={`absolute top-2 pointer-events-none z-10 flex items-center gap-1 ${cornerInset ? "right-12" : "right-2"}`}>
        {isManualRecording && (
          <div className="flex items-center gap-1 rounded bg-rec px-2 py-0.5 text-xs font-semibold text-video-fg tabular-nums">
            <span className="h-2 w-2 rounded-full bg-white animate-pulse motion-reduce:animate-none" />
            <span>CLIP {formatClipSeconds(manualRecordSeconds)}</span>
          </div>
        )}
        {isRecording && (
          <div className="flex items-center gap-1 rounded bg-video-overlay px-2 py-0.5 text-xs font-semibold text-video-fg">
            <span className="h-2 w-2 rounded-full bg-rec animate-pulse motion-reduce:animate-none" />
            <span>{LIVE_COPY.REC_BADGE}</span>
          </div>
        )}
        {renderStateBadge()}
      </div>

      {/* Bottom Centre: Stream details in Advanced view */}
      {viewMode === "advanced" && (
        <div data-video-chrome className="absolute bottom-2 left-1/2 -translate-x-1/2 max-w-[70%] pointer-events-none z-10 hidden sm:block">
          <div className="truncate whitespace-nowrap rounded bg-video-overlay px-2 py-0.5 text-xs font-normal text-video-fg">
            {stream.toUpperCase()} • WebRTC • {serial}
          </div>
        </div>
      )}

      {/* Bottom Right: Action Controls (Hover/focus or coarse pointer) */}
      <div
        data-video-chrome
        className={cn(
          "absolute bottom-2 right-2 z-20 flex items-center gap-1 transition-opacity duration-150",
          isManualRecording
            ? "opacity-100"
            : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100"
        )}
      >
        {onToggleManualRecord && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label={isManualRecording ? LIVE_COPY.STOP_CLIP_LABEL : LIVE_COPY.RECORD_CLIP_LABEL}
                aria-pressed={isManualRecording}
                variant="ghost"
                size="icon"
                className={cn(
                  "h-8 w-8 pointer-coarse:h-11 pointer-coarse:w-11 rounded text-video-fg",
                  isManualRecording
                    ? "bg-rec hover:bg-rec/90 hover:text-video-fg"
                    : "bg-video-overlay hover:bg-video-overlay/80 hover:text-video-fg"
                )}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleManualRecord();
                }}
              >
                {isManualRecording ? <Square className="h-4 w-4 fill-current" /> : <Video className="h-4 w-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {isManualRecording ? LIVE_COPY.STOP_CLIP_LABEL : LIVE_COPY.RECORD_CLIP_LABEL}
            </TooltipContent>
          </Tooltip>
        )}

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              aria-label={LIVE_COPY.SNAPSHOT_LABEL}
              variant="ghost"
              size="icon"
              className="h-8 w-8 pointer-coarse:h-11 pointer-coarse:w-11 rounded bg-video-overlay text-video-fg hover:bg-video-overlay/80 hover:text-video-fg"
              onClick={(e) => {
                e.stopPropagation();
                onSnapshot();
              }}
            >
              <Camera className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{LIVE_COPY.SNAPSHOT_LABEL}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              aria-label={isMuted ? LIVE_COPY.UNMUTE_LABEL : LIVE_COPY.MUTE_LABEL}
              variant="ghost"
              size="icon"
              className="h-8 w-8 pointer-coarse:h-11 pointer-coarse:w-11 rounded bg-video-overlay text-video-fg hover:bg-video-overlay/80 hover:text-video-fg"
              onClick={(e) => {
                e.stopPropagation();
                onToggleMute();
              }}
            >
              {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {isMuted ? LIVE_COPY.UNMUTE_LABEL : LIVE_COPY.MUTE_LABEL}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              aria-label={fsLabel}
              variant="ghost"
              size="icon"
              className="h-8 w-8 pointer-coarse:h-11 pointer-coarse:w-11 rounded bg-video-overlay text-video-fg hover:bg-video-overlay/80 hover:text-video-fg"
              onClick={(e) => {
                e.stopPropagation();
                (onToggleFullscreen ?? onToggleMaximize)();
              }}
            >
              {fsActive ? (
                <Minimize2 className="h-4 w-4" />
              ) : (
                <Maximize2 className="h-4 w-4" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {fsLabel}
          </TooltipContent>
        </Tooltip>
      </div>
    </>
  );
};