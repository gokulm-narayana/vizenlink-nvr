import React, { useState } from "react";
import {
  Footprints,
  Spline,
  ShieldAlert,
  User,
  Car,
  Bell,
  Lock,
  ImageOff,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatRelative, useSiteTimeZone } from "@/lib/time";
import type { EventItem } from "./api";
import { EVENTS_COPY } from "./copy";

export interface EventCardProps {
  event: EventItem;
  cameraName?: string;
  isRead: boolean;
  onClick: (event: EventItem) => void;
  zone?: string;
}

export function getEventTypeIcon(type: string) {
  switch (type.toLowerCase()) {
    case "motion":
      return <Footprints className="h-3.5 w-3.5" />;
    case "line_crossing":
      return <Spline className="h-3.5 w-3.5" />;
    case "tamper":
      return <ShieldAlert className="h-3.5 w-3.5 text-warning" />;
    case "person":
      return <User className="h-3.5 w-3.5" />;
    case "vehicle":
      return <Car className="h-3.5 w-3.5" />;
    default:
      return <Bell className="h-3.5 w-3.5" />;
  }
}

export function formatEventTypeLabel(type: string): string {
  switch (type.toLowerCase()) {
    case "motion":
      return "Motion";
    case "line_crossing":
      return "Line Crossing";
    case "tamper":
      return "Tamper";
    case "person":
      return "Person";
    case "vehicle":
      return "Vehicle";
    default:
      return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

export const EventCard: React.FC<EventCardProps> = ({
  event,
  cameraName,
  isRead,
  onClick,
  zone: zoneProp,
}) => {
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;

  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgError, setImgError] = useState(false);

  const absTime = formatDateTime(event.start_time, zone);
  const relTime = formatRelative(event.start_time);
  const displayName = cameraName || event.camera_serial;

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onClick(event)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(event);
        }
      }}
      className="group relative flex flex-col overflow-hidden border-border bg-card p-0 transition-all hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary cursor-pointer select-none"
    >
      {/* 16:9 Snapshot Thumbnail Area */}
      <div className="relative aspect-video w-full bg-muted overflow-hidden flex items-center justify-center">
        {event.snapshot_path && !imgError ? (
          <>
            {!imgLoaded && (
              <Skeleton className="absolute inset-0 h-full w-full rounded-none" />
            )}
            <img
              src={`/api/v1/events/${event.id}/snapshot`}
              alt={`${formatEventTypeLabel(event.event_type)} at ${displayName}, ${absTime}`}
              onLoad={() => setImgLoaded(true)}
              onError={() => setImgError(true)}
              className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
            />
          </>
        ) : (
          <div className="flex flex-col items-center justify-center gap-1 text-muted-foreground">
            <ImageOff className="h-8 w-8" />
            <span className="text-xs font-normal">{EVENTS_COPY.NO_SNAPSHOT}</span>
          </div>
        )}

        {/* Type Badge */}
        <Badge
          variant="secondary"
          className="absolute top-2 left-2 flex items-center gap-1.5 px-2 py-0.5 text-xs font-semibold shadow-xs backdrop-blur-xs"
        >
          {getEventTypeIcon(event.event_type)}
          <span>{formatEventTypeLabel(event.event_type)}</span>
        </Badge>

        {/* Lock Pill / Icon */}
        {event.is_locked && (
          <div
            title="Locked"
            className="absolute top-2 right-2 flex items-center justify-center rounded bg-background/80 p-1 text-foreground shadow-xs"
          >
            <Lock className="h-3.5 w-3.5" />
          </div>
        )}
      </div>

      {/* Card Body */}
      <div className="flex flex-col gap-2 p-4">
        <div className="flex items-center justify-between gap-2 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            {/* 8px Accent Unread Dot */}
            {!isRead && (
              <span className="flex shrink-0 items-center">
                <span className="h-2 w-2 rounded-full bg-primary" />
                <span className="sr-only">{EVENTS_COPY.UNREAD_LABEL}</span>
              </span>
            )}
            <span className="truncate text-sm font-semibold text-foreground">
              {displayName}
            </span>
          </div>

          <span
            title={absTime}
            className="shrink-0 text-xs font-normal text-muted-foreground whitespace-nowrap"
          >
            {relTime}
          </span>
        </div>
      </div>
    </Card>
  );
};
