import React, { useState } from "react";
import { Link } from "react-router";
import { Calendar as CalendarIcon, Bell } from "lucide-react";
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
  cameras: Array<{ serial: string; name: string; is_online?: boolean }>;
  selectedSerial: string;
  onSelectCamera: (serial: string) => void;
  selectedDay: string;
  onSelectDay: (day: string) => void;
  recordedDays: string[];
  currentTime: Date;
  onSeek: (target: Date) => void;
  zone: string;
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

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-card p-2 text-foreground">
      {/* Left controls: Camera, Date, Jump */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Camera Selector */}
        <div className="flex items-center gap-2">
          <label className="text-xs font-semibold text-muted-foreground">
            {PLAYBACK_COPY.cameraLabel}:
          </label>
          <Select value={selectedSerial} onValueChange={onSelectCamera}>
            <SelectTrigger className="h-8 min-w-[160px] text-xs font-semibold" aria-label="Select camera">
              <SelectValue placeholder="Select camera" />
            </SelectTrigger>
            <SelectContent>
              {cameras.map((c) => (
                <SelectItem key={c.serial} value={c.serial} className="text-xs">
                  <span className="flex items-center gap-2">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        c.is_online ? "bg-success" : "bg-muted-foreground"
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
          <label className="text-xs font-semibold text-muted-foreground">
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
                  {formatDateTime(selectedDateObj, zone, {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
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
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" asChild><Link to="/live">Back to Multiview</Link></Button>
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
