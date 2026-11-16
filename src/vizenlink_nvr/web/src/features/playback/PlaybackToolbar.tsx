import React, { useState } from "react";
import { Link } from "react-router";
import { Calendar as CalendarIcon, Bell, Columns2, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { toIsoDate } from "@/lib/timeline";
import { formatDateTime } from "@/lib/time";
import { PLAYBACK_COPY } from "./copy";
import { parseTimeToDate } from "./usePlaybackEngine";

export interface PlaybackToolbarProps {
  cameras: Array<{ serial: string; name: string; is_online?: boolean; state?: string }>;
  selectedSerial: string;
  onSelectCamera: (serial: string) => void;
  selectedDay: string;
  onSelectDay: (day: string) => void;
  recordedDays: string[];
  currentTime: Date;
  onSeek: (target: Date) => void;
  zone: string;
  viewMode?: "single" | "sync";
  onViewModeChange?: (mode: "single" | "sync") => void;
  syncGridSize?: 4 | 6;
  onSyncGridSizeChange?: (size: 4 | 6) => void;
}

export function PlaybackToolbar({
  cameras,
  selectedSerial,
  onSelectCamera,
  selectedDay,
  onSelectDay,
  recordedDays,
  currentTime,
  onSeek,
  zone,
  viewMode = "single",
  onViewModeChange,
  syncGridSize = 4,
  onSyncGridSizeChange,
}: PlaybackToolbarProps) {
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [timeInput, setTimeInput] = useState("");

  const handleJump = () => {
    if (!timeInput.trim()) return;
    const target = parseTimeToDate(selectedDay, timeInput, zone);
    if (target) {
      onSeek(target);
      setTimeInput("");
    }
  };

  const selectedDateObj = new Date(`${selectedDay}T12:00:00Z`);
  const compareParams = new URLSearchParams();
  const orderedSerials = [
    selectedSerial,
    ...cameras.filter((c) => c.serial !== selectedSerial && c.is_online !== false).map((c) => c.serial),
    ...cameras.filter((c) => c.serial !== selectedSerial && c.is_online === false).map((c) => c.serial),
  ].filter(Boolean);
  for (const serial of [...new Set(orderedSerials)].slice(0, 4)) {
    compareParams.append("camera", serial);
  }
  compareParams.set("t", currentTime.toISOString());

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-card p-2 text-foreground max-sm:justify-start">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1">
          <Button
            type="button"
            variant={viewMode === "single" ? "secondary" : "ghost"}
            size="sm"
            className="h-8 px-2 text-xs font-semibold"
            aria-pressed={viewMode === "single"}
            onClick={() => onViewModeChange?.("single")}
          >
            <Video className="size-4" />
            <span>Single view</span>
          </Button>
          {onViewModeChange ? (
            <Button
              type="button"
              variant={viewMode === "sync" ? "secondary" : "ghost"}
              size="sm"
              className="h-8 px-2 text-xs font-semibold"
              aria-pressed={viewMode === "sync"}
              onClick={() => onViewModeChange("sync")}
            >
              <Columns2 className="size-4" />
              <span>Multi-view sync</span>
            </Button>
          ) : (
            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs font-semibold" asChild>
              <Link to={`/playback/compare?${compareParams.toString()}`} title="Compare up to 4 cameras with synchronized playback">
                <Columns2 className="size-4" />
                <span>Multi-view sync</span>
              </Link>
            </Button>
          )}
        </div>
        {viewMode === "sync" && onSyncGridSizeChange && (
          <div className="flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1">
            <Button
              type="button"
              variant={syncGridSize === 4 ? "secondary" : "ghost"}
              size="sm"
              className="h-8 px-2 text-xs font-semibold"
              aria-pressed={syncGridSize === 4}
              onClick={() => onSyncGridSizeChange(4)}
            >
              2×2
            </Button>
            <Button
              type="button"
              variant={syncGridSize === 6 ? "secondary" : "ghost"}
              size="sm"
              className="h-8 px-2 text-xs font-semibold"
              aria-pressed={syncGridSize === 6}
              onClick={() => onSyncGridSizeChange(6)}
            >
              All ({cameras.length})
            </Button>
          </div>
        )}
      </div>
      {/* Left controls: Camera, Date, Jump. On phones the groups dissolve (contents) so every
          control flows into two rows instead of one row per group. */}
      <div className="flex flex-wrap items-center gap-2 max-sm:contents">
        {/* Camera Selector */}
        <div className="flex items-center gap-2">
          <label className="hidden text-xs font-semibold text-muted-foreground sm:inline">
            {PLAYBACK_COPY.cameraLabel}:
          </label>
          <Select value={selectedSerial} onValueChange={onSelectCamera}>
            <SelectTrigger className="h-8 min-w-[130px] text-xs font-semibold sm:min-w-[160px]" aria-label="Select camera">
              <SelectValue placeholder="Select camera" />
            </SelectTrigger>
            <SelectContent>
              {cameras.map((c) => (
                <SelectItem key={c.serial} value={c.serial} className="text-xs">
                  <span className="flex items-center gap-2">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        c.is_online !== false && (!c.state || c.state === "active" || c.state === "online")
                          ? "bg-success"
                          : "bg-muted-foreground"
                      }`}
                    />
                    <span>{c.name}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Date Picker */}
        <div className="flex items-center gap-2">
          <label className="hidden text-xs font-semibold text-muted-foreground sm:inline">
            {PLAYBACK_COPY.dateLabel}:
          </label>
          <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-2 text-xs font-semibold"
                aria-label="Pick date"
              >
                <CalendarIcon className="h-3.5 w-3.5 text-muted-foreground" />
                <span>
                  {formatDateTime(selectedDateObj, "UTC", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                    hour: undefined,
                    minute: undefined,
                    second: undefined,
                  })}
                </span>
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="single"
                selected={selectedDateObj}
                onSelect={(date) => {
                  if (date) {
                    onSelectDay(toIsoDate(date, zone));
                    setCalendarOpen(false);
                  }
                }}
                modifiers={{
                  hasFootage: (date) => recordedDays.includes(toIsoDate(date, zone)),
                  noFootage: (date) => !recordedDays.includes(toIsoDate(date, zone)),
                }}
                modifiersClassNames={{
                  hasFootage:
                    "relative after:absolute after:bottom-1 after:left-1/2 after:-translate-x-1/2 after:h-1 after:w-1 after:rounded-full after:bg-primary",
                  noFootage: "text-muted-foreground opacity-60",
                }}
              />
            </PopoverContent>
          </Popover>
        </div>

        {/* Jump to Time */}
        <div className="flex items-center gap-1">
          <Input
            type="text"
            placeholder="HH:MM:SS"
            aria-label="Jump to time"
            value={timeInput}
            onChange={(e) => setTimeInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleJump();
            }}
            className="h-8 w-24 text-xs font-mono"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={handleJump}
            className="h-8 text-xs font-semibold"
          >
            Jump
          </Button>
        </div>
      </div>

      {/* Right controls: Events Link */}
      <div className="flex items-center gap-2 max-sm:contents">
        <Button variant="ghost" size="sm" asChild className="hidden sm:inline-flex"><Link to="/live">Back to Live View</Link></Button>
        <Button variant="outline" size="sm" asChild className="h-8 gap-2 text-xs font-semibold">
          <Link to={`/events?camera=${encodeURIComponent(selectedSerial)}`} className="flex items-center gap-1">
            <Bell className="h-3.5 w-3.5 text-muted-foreground" />
            <span>{PLAYBACK_COPY.eventsLink}</span>
          </Link>
        </Button>
      </div>
    </div>
  );
}
