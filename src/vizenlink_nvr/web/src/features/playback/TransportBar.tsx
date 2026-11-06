import React, { useEffect, useCallback } from "react";
import {
  Play,
  Pause,
  RotateCcw,
  RotateCw,
  Volume2,
  VolumeX,
  Camera,
  Maximize,
  MoreHorizontal,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Kbd } from "@/components/ui/kbd";
import { formatDateTime, zoneAbbreviation } from "@/lib/time";
import { PLAYBACK_COPY } from "./copy";

export interface TransportBarProps {
  isPlaying: boolean;
  onPlayPause: () => void;
  onSkip: (seconds: number) => void;
  playbackRate: number;
  onRateChange: (rate: number) => void;
  isMuted: boolean;
  onToggleMute: () => void;
  onTakeSnapshot: () => void;
  isSnapshotPending?: boolean;
  snapshotError?: string | null;
  onRetrySnapshot?: () => void;
  onDismissSnapshotError?: () => void;
  onMarkIn: () => void;
  onMarkOut: () => void;
  inMarker: Date | null;
  outMarker: Date | null;
  onOpenExport: () => void;
  currentTime: Date;
  zone: string;
  hasActiveSegment: boolean;
  containerRef?: React.RefObject<HTMLElement | null>;
}

export function TransportBar({
  isPlaying,
  onPlayPause,
  onSkip,
  playbackRate,
  onRateChange,
  isMuted,
  onToggleMute,
  onTakeSnapshot,
  isSnapshotPending = false,
  snapshotError,
  onRetrySnapshot,
  onDismissSnapshotError,
  onMarkIn,
  onMarkOut,
  inMarker,
  outMarker,
  onOpenExport,
  currentTime,
  zone,
  hasActiveSegment,
  containerRef,
}: TransportBarProps) {
  const handleFullscreen = useCallback(() => {
    const target = containerRef?.current || document.documentElement;
    if (!document.fullscreenElement) {
      target.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }, [containerRef]);

  // Global keyboard shortcuts (disabled when typing in an input/textarea/select)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || "").toLowerCase();
      if (
        activeTag === "input" ||
        activeTag === "textarea" ||
        activeTag === "select" ||
        (document.activeElement as HTMLElement)?.isContentEditable
      ) {
        return;
      }

      if (e.key === " " || e.key.toLowerCase() === "k") {
        e.preventDefault();
        onPlayPause();
      } else if (e.key.toLowerCase() === "j" || e.key === "ArrowLeft") {
        e.preventDefault();
        onSkip(-10);
      } else if (e.key.toLowerCase() === "l" || e.key === "ArrowRight") {
        e.preventDefault();
        onSkip(10);
      } else if (e.key.toLowerCase() === "m") {
        e.preventDefault();
        onToggleMute();
      } else if (e.key.toLowerCase() === "s") {
        e.preventDefault();
        onTakeSnapshot();
      } else if (e.key.toLowerCase() === "i") {
        e.preventDefault();
        onMarkIn();
      } else if (e.key.toLowerCase() === "o") {
        e.preventDefault();
        onMarkOut();
      } else if (e.key.toLowerCase() === "f") {
        e.preventDefault();
        handleFullscreen();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    onPlayPause,
    onSkip,
    onToggleMute,
    onTakeSnapshot,
    onMarkIn,
    onMarkOut,
    handleFullscreen,
  ]);

  const canExport = Boolean(inMarker && outMarker);

  return (
    <TooltipProvider>
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-2 text-foreground">
        {/* Snapshot Error Alert */}
        {snapshotError && (
          <Alert variant="destructive" role="alert" className="py-2">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between gap-4 text-xs font-semibold">
              <span>{PLAYBACK_COPY.snapshotError}</span>
              <div className="flex items-center gap-2">
                {onRetrySnapshot && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onRetrySnapshot}
                    className="h-7 text-xs font-semibold"
                  >
                    {PLAYBACK_COPY.retrySaveSnapshot}
                  </Button>
                )}
                {onDismissSnapshotError && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onDismissSnapshotError}
                    className="h-7 text-xs font-semibold"
                  >
                    Dismiss
                  </Button>
                )}
              </div>
            </AlertDescription>
          </Alert>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          {/* Left: Transport buttons */}
          <div className="flex items-center gap-2">
            <ButtonGroup>
              {/* Skip Back 10s */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    aria-label={PLAYBACK_COPY.back10s}
                    className="size-8"
                    onClick={() => onSkip(-10)}
                  >
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="flex items-center gap-1 text-xs">
                  <span>{PLAYBACK_COPY.back10s}</span>
                  <Kbd>J</Kbd>
                </TooltipContent>
              </Tooltip>

              {/* Play / Pause */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    aria-label={isPlaying ? PLAYBACK_COPY.pause : PLAYBACK_COPY.play}
                    className="size-8"
                    onClick={onPlayPause}
                    disabled={!hasActiveSegment}
                  >
                    {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="flex items-center gap-1 text-xs">
                  <span>{isPlaying ? PLAYBACK_COPY.pause : PLAYBACK_COPY.play}</span>
                  <Kbd>Space</Kbd>
                </TooltipContent>
              </Tooltip>

              {/* Skip Forward 10s */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    aria-label={PLAYBACK_COPY.forward10s}
                    className="size-8"
                    onClick={() => onSkip(10)}
                  >
                    <RotateCw className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="flex items-center gap-1 text-xs">
                  <span>{PLAYBACK_COPY.forward10s}</span>
                  <Kbd>L</Kbd>
                </TooltipContent>
              </Tooltip>
            </ButtonGroup>

            {/* Speed select */}
            <div className="flex items-center gap-1">
              <span className="text-xs font-semibold text-muted-foreground hidden sm:inline">
                {PLAYBACK_COPY.speed}:
              </span>
              <Select
                value={String(playbackRate)}
                onValueChange={(val) => onRateChange(Number(val))}
              >
                <SelectTrigger
                  className="h-8 w-16 text-xs font-semibold"
                  aria-label="Playback speed"
                >
                  <SelectValue>{playbackRate}x</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0.5" className="text-xs">0.5x</SelectItem>
                  <SelectItem value="1" className="text-xs">1x</SelectItem>
                  <SelectItem value="2" className="text-xs">2x</SelectItem>
                  <SelectItem value="4" className="text-xs">4x</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Center: Current Playhead timestamp */}
          <div className="text-xs font-mono tabular-nums text-muted-foreground">
            <span>{formatDateTime(currentTime, zone)}</span>{" "}
            <span>{zoneAbbreviation(currentTime, zone)}</span>
          </div>

          {/* Right: Actions */}
          <div className="flex items-center gap-2">
            {/* Desktop toolbar controls */}
            <div className="hidden md:flex items-center gap-2">
              {/* Mute */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={isMuted ? PLAYBACK_COPY.unmute : PLAYBACK_COPY.mute}
                    className="size-8"
                    onClick={onToggleMute}
                  >
                    {isMuted ? (
                      <VolumeX className="h-4 w-4 text-destructive" />
                    ) : (
                      <Volume2 className="h-4 w-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="flex items-center gap-1 text-xs">
                  <span>{isMuted ? PLAYBACK_COPY.unmute : PLAYBACK_COPY.mute}</span>
                  <Kbd>M</Kbd>
                </TooltipContent>
              </Tooltip>

              {/* Snapshot */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    aria-label={PLAYBACK_COPY.snapshot}
                    className="size-8"
                    onClick={onTakeSnapshot}
                    disabled={isSnapshotPending}
                  >
                    {isSnapshotPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Camera className="h-4 w-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="flex items-center gap-1 text-xs">
                  <span>{PLAYBACK_COPY.snapshot}</span>
                  <Kbd>S</Kbd>
                </TooltipContent>
              </Tooltip>

              {/* Mark In */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={inMarker ? "secondary" : "outline"}
                    size="sm"
                    onClick={onMarkIn}
                    className="h-8 text-xs font-semibold"
                  >
                    {PLAYBACK_COPY.markIn}
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="flex items-center gap-1 text-xs">
                  <span>{PLAYBACK_COPY.markIn}</span>
                  <Kbd>I</Kbd>
                </TooltipContent>
              </Tooltip>

              {/* Mark Out */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={outMarker ? "secondary" : "outline"}
                    size="sm"
                    onClick={onMarkOut}
                    className="h-8 text-xs font-semibold"
                  >
                    {PLAYBACK_COPY.markOut}
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="flex items-center gap-1 text-xs">
                  <span>{PLAYBACK_COPY.markOut}</span>
                  <Kbd>O</Kbd>
                </TooltipContent>
              </Tooltip>

              {/* Fullscreen */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={PLAYBACK_COPY.fullscreen}
                    className="size-8"
                    onClick={handleFullscreen}
                  >
                    <Maximize className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="flex items-center gap-1 text-xs">
                  <span>{PLAYBACK_COPY.fullscreen}</span>
                  <Kbd>F</Kbd>
                </TooltipContent>
              </Tooltip>
            </div>

            {/* Mobile Dropdown for additional controls */}
            <div className="md:hidden">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    className="size-8"
                    aria-label={PLAYBACK_COPY.moreControls}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={onToggleMute} className="text-xs">
                    {isMuted ? PLAYBACK_COPY.unmute : PLAYBACK_COPY.mute}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onTakeSnapshot} className="text-xs">
                    {PLAYBACK_COPY.snapshot}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onMarkIn} className="text-xs">
                    {PLAYBACK_COPY.markIn}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onMarkOut} className="text-xs">
                    {PLAYBACK_COPY.markOut}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleFullscreen} className="text-xs">
                    {PLAYBACK_COPY.fullscreen}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Primary Export Clip CTA */}
            <Button
              variant="default"
              size="sm"
              onClick={onOpenExport}
              disabled={!canExport}
              className="h-8 text-xs font-semibold"
            >
              {PLAYBACK_COPY.exportClip}
            </Button>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
