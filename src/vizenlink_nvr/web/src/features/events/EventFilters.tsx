import React, { useState } from "react";
import { CalendarIcon } from "lucide-react";
import type { DateRange } from "react-day-picker";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import { useUiStore } from "@/stores/ui";
import { EVENTS_COPY } from "./copy";

export interface EventFiltersProps {
  cameras: Array<{ serial: string; name: string }>;
  selectedCamera: string;
  selectedType: string;
  dateRange?: DateRange;
  unreadOnly: boolean;
  onCameraChange: (serial: string) => void;
  onTypeChange: (type: string) => void;
  onDateRangeChange: (range: DateRange | undefined) => void;
  onUnreadOnlyChange: (unread: boolean) => void;
  onClearFilters: () => void;
  isFiltered: boolean;
  zone?: string;
}

const EVENT_TYPES = [
  { value: "motion", label: "Motion" },
  { value: "line_crossing", label: "Line Crossing" },
  { value: "tamper", label: "Tamper" },
  { value: "person", label: "Person" },
  { value: "vehicle", label: "Vehicle" },
];

export const EventFilters: React.FC<EventFiltersProps> = ({
  cameras,
  selectedCamera,
  selectedType,
  dateRange,
  unreadOnly,
  onCameraChange,
  onTypeChange,
  onDateRangeChange,
  onUnreadOnlyChange,
  onClearFilters,
  isFiltered,
  zone: zoneProp,
}) => {
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;
  const viewMode = useUiStore((s) => s.viewMode);
  const [popoverOpen, setPopoverOpen] = useState(false);

  const dateLabel =
    dateRange?.from && dateRange?.to
      ? `${formatDateTime(dateRange.from, zone, { month: "short", day: "numeric" })} - ${formatDateTime(dateRange.to, zone, { month: "short", day: "numeric" })}`
      : dateRange?.from
        ? formatDateTime(dateRange.from, zone, { month: "short", day: "numeric" })
        : EVENTS_COPY.FILTER_DATE_RANGE;

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-md border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-4">
        {/* Camera Select */}
        <Select
          value={selectedCamera || "all"}
          onValueChange={(val) => onCameraChange(val === "all" ? "" : val)}
        >
          <SelectTrigger className="h-9 min-w-[160px] text-xs">
            <SelectValue placeholder={EVENTS_COPY.FILTER_ALL_CAMERAS} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{EVENTS_COPY.FILTER_ALL_CAMERAS}</SelectItem>
            {cameras.map((cam) => (
              <SelectItem key={cam.serial} value={cam.serial}>
                {cam.name || cam.serial}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Event Type Select */}
        <Select
          value={selectedType || "all"}
          onValueChange={(val) => onTypeChange(val === "all" ? "" : val)}
        >
          <SelectTrigger className="h-9 min-w-[150px] text-xs">
            <SelectValue placeholder={EVENTS_COPY.FILTER_ALL_TYPES} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{EVENTS_COPY.FILTER_ALL_TYPES}</SelectItem>
            {EVENT_TYPES.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Date Range Popover + Calendar */}
        <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="h-9 justify-start gap-2 text-xs font-normal"
            >
              <CalendarIcon className="h-4 w-4 text-muted-foreground" />
              <span>{dateLabel}</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="range"
              selected={dateRange}
              onSelect={(range) => {
                onDateRangeChange(range);
                if (range?.from && range?.to) {
                  setPopoverOpen(false);
                }
              }}
              numberOfMonths={1}
            />
          </PopoverContent>
        </Popover>

        {/* Clear Filters Button */}
        {isFiltered && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearFilters}
            className="h-9 text-xs font-normal text-muted-foreground hover:text-foreground"
          >
            {EVENTS_COPY.FILTER_CLEAR}
          </Button>
        )}
      </div>

      {/* Advanced View: Unread Only Switch */}
      {viewMode === "advanced" && (
        <div className="flex items-center gap-2">
          <Switch
            id="unread-only-switch"
            checked={unreadOnly}
            onCheckedChange={onUnreadOnlyChange}
          />
          <Label
            htmlFor="unread-only-switch"
            className="text-xs font-semibold cursor-pointer text-muted-foreground hover:text-foreground"
          >
            {EVENTS_COPY.FILTER_UNREAD_ONLY}
          </Label>
        </div>
      )}
    </div>
  );
};
