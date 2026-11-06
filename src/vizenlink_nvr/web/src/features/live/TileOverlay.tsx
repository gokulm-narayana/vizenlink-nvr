import React from "react";
import {
  Camera,
  Volume2,
  VolumeX,
  Maximize2,
  Minimize2,
  WifiOff,
} from "lucide-react";
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

interface TileOverlayProps {
  name: string;
  serial: string;
  state: PlayerState;
  isRecording: boolean;
  isMuted: boolean;
  isMaximized: boolean;
  stream: StreamRole;
  viewMode: ViewMode;
  onSnapshot: () => void;
  onToggleMute: () => void;
  onToggleMaximize: () => void;
}

export const TileOverlay: React.FC<TileOverlayProps> = ({
  name,
  serial,
  state,
  isRecording,
  isMuted,
  isMaximized,
  stream,
  viewMode,
  onSnapshot,
  onToggleMute,
  onToggleMaximize,
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

  return (
    <>
      {/* Top Left: Camera Name */}
      <div className="absolute top-2 left-2 max-w-[60%] pointer-events-none z-10">
        <div
          title={name}
          className="truncate rounded bg-video-overlay px-2 py-0.5 text-xs font-semibold text-video-fg"
        >
          {name}
        </div>
      </div>

      {/* Top Right: State Badge */}
      <div className="absolute top-2 right-2 pointer-events-none z-10">
        {renderStateBadge()}
      </div>

      {/* Bottom Left: REC Indicator */}
      {isRecording && (
        <div className="absolute bottom-2 left-2 pointer-events-none z-10">
          <div className="flex items-center gap-1.5 rounded bg-video-overlay px-2 py-0.5 text-xs font-semibold text-video-fg">
            <span className="h-2 w-2 rounded-full bg-rec animate-pulse motion-reduce:animate-none" />
            <span>{LIVE_COPY.REC_BADGE}</span>
          </div>
        </div>
      )}

      {/* Bottom Centre: Stream details in Advanced view */}
      {viewMode === "advanced" && (
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 pointer-events-none z-10 hidden sm:block">
          <div className="rounded bg-video-overlay px-2 py-0.5 text-xs font-normal text-video-fg">
            {stream.toUpperCase()} • WebRTC • {serial}
          </div>
        </div>
      )}

      {/* Bottom Right: Action Controls (Hover/focus or coarse pointer) */}
      <div className="absolute bottom-2 right-2 z-20 flex items-center gap-1 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100 transition-opacity duration-150">
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
              aria-label={isMaximized ? LIVE_COPY.MINIMIZE_LABEL : LIVE_COPY.MAXIMIZE_LABEL}
              variant="ghost"
              size="icon"
              className="h-8 w-8 pointer-coarse:h-11 pointer-coarse:w-11 rounded bg-video-overlay text-video-fg hover:bg-video-overlay/80 hover:text-video-fg"
              onClick={(e) => {
                e.stopPropagation();
                onToggleMaximize();
              }}
            >
              {isMaximized ? (
                <Minimize2 className="h-4 w-4" />
              ) : (
                <Maximize2 className="h-4 w-4" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {isMaximized ? LIVE_COPY.MINIMIZE_LABEL : LIVE_COPY.MAXIMIZE_LABEL}
          </TooltipContent>
        </Tooltip>
      </div>
    </>
  );
};
