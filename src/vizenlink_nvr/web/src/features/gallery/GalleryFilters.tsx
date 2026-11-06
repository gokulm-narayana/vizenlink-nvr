import React, { useState } from "react";
import { CalendarIcon, User as UserIcon } from "lucide-react";
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
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import { useUiStore } from "@/stores/ui";
import { useCurrentUser } from "@/lib/queries";
import { useUsersList } from "./api";
import { GALLERY_COPY } from "./copy";

export interface GalleryFiltersProps {
  cameras: Array<{ serial: string; name: string }>;
  selectedCamera: string;
  dateRange?: DateRange;
  selectedUser: string;
  onCameraChange: (serial: string) => void;
  onDateRangeChange: (range: DateRange | undefined) => void;
  onUserChange: (userFilter: string) => void;
  onClearFilters: () => void;
  isFiltered: boolean;
  zone?: string;
}

export const GalleryFilters: React.FC<GalleryFiltersProps> = ({
  cameras,
  selectedCamera,
  dateRange,
  selectedUser,
  onCameraChange,
  onDateRangeChange,
  onUserChange,
  onClearFilters,
  isFiltered,
  zone: zoneProp,
}) => {
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;
  const viewMode = useUiStore((s) => s.viewMode);
  const user = useCurrentUser();
  const { data: users = [] } = useUsersList();
  const [popoverOpen, setPopoverOpen] = useState(false);

  const dateLabel =
    dateRange?.from && dateRange?.to
      ? `${formatDateTime(dateRange.from, zone, { month: "short", day: "numeric" })} - ${formatDateTime(dateRange.to, zone, { month: "short", day: "numeric" })}`
      : dateRange?.from
        ? formatDateTime(dateRange.from, zone, { month: "short", day: "numeric" })
        : GALLERY_COPY.FILTER_DATE_RANGE;

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-md border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-4">
        {/* Camera Select */}
        <Select
          value={selectedCamera || "all"}
          onValueChange={(val) => onCameraChange(val === "all" ? "" : val)}
        >
          <SelectTrigger className="h-9 min-w-[160px] text-xs">
            <SelectValue placeholder={GALLERY_COPY.FILTER_ALL_CAMERAS} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{GALLERY_COPY.FILTER_ALL_CAMERAS}</SelectItem>
            {cameras.map((cam) => (
              <SelectItem key={cam.serial} value={cam.serial}>
                {cam.name || cam.serial}
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

        {/* Advanced View: User Filter */}
        {viewMode === "advanced" && (
          <Select
            value={selectedUser || "all"}
            onValueChange={(val) => onUserChange(val === "all" ? "" : val)}
          >
            <SelectTrigger className="h-9 min-w-[140px] text-xs">
              <UserIcon className="h-4 w-4 text-muted-foreground mr-1.5" />
              <SelectValue placeholder={GALLERY_COPY.FILTER_USER} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{GALLERY_COPY.FILTER_USER_ANYONE}</SelectItem>
              <SelectItem value="me">{GALLERY_COPY.FILTER_USER_ME}</SelectItem>
              {user?.role === "owner" &&
                users
                  .filter((u) => u.id !== user.id)
                  .map((u) => (
                    <SelectItem key={u.id} value={u.id.toString()}>
                      {u.username}
                    </SelectItem>
                  ))}
            </SelectContent>
          </Select>
        )}

        {/* Clear Filters Button */}
        {isFiltered && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearFilters}
            className="h-9 text-xs font-normal text-muted-foreground hover:text-foreground"
          >
            {GALLERY_COPY.FILTER_CLEAR}
          </Button>
        )}
      </div>
    </div>
  );
};
