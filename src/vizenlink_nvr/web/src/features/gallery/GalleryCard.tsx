import React, { useState } from "react";
import { Play, ImageOff, Film } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import type { GalleryItem } from "./api";

export interface GalleryCardProps {
  item: GalleryItem;
  cameraName?: string;
  onClick: (item: GalleryItem) => void;
  zone?: string;
}

export function formatDuration(sec?: number | null): string {
  if (!sec || sec <= 0) return "0s";
  const s = Math.round(sec);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const remS = s % 60;
  return `${m}:${String(remS).padStart(2, "0")}`;
}

export const GalleryCard: React.FC<GalleryCardProps> = ({
  item,
  cameraName,
  onClick,
  zone: zoneProp,
}) => {
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;

  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  const isSnapshot = item.item_type === "snapshot";
  const mediaUrl = `/api/v1/gallery/${item.id}/download`;
  const formattedTime = formatDateTime(item.captured_at, zone);
  const displayName = cameraName || item.camera_serial;

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onClick(item)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(item);
        }
      }}
      className="group relative flex flex-col overflow-hidden border-border bg-card p-0 transition-all hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary cursor-pointer select-none"
    >
      {/* 16:9 Thumbnail Area */}
      <div className="relative aspect-video w-full bg-muted overflow-hidden flex items-center justify-center">
        {!loaded && !error && (
          <Skeleton className="absolute inset-0 h-full w-full rounded-none" />
        )}

        {error ? (
          <div className="flex flex-col items-center justify-center gap-1 text-muted-foreground">
            {isSnapshot ? (
              <ImageOff className="h-8 w-8" />
            ) : (
              <Film className="h-8 w-8" />
            )}
            <span className="text-xs font-normal">Preview unavailable</span>
          </div>
        ) : isSnapshot ? (
          <img
            src={mediaUrl}
            alt={item.title}
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
            className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
          />
        ) : (
          <div className="relative h-full w-full">
            <video
              src={`${mediaUrl}#t=0.5`}
              preload="metadata"
              onLoadedData={() => setLoaded(true)}
              onError={() => setError(true)}
              className="h-full w-full object-cover"
            />
            {/* Play overlay icon */}
            <div className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/20 transition-colors">
              <div className="flex items-center justify-center rounded-full bg-background/80 p-2 text-foreground shadow-sm">
                <Play className="h-4 w-4 fill-current ml-0.5" />
              </div>
            </div>
          </div>
        )}

        {/* Clip duration chip */}
        {!isSnapshot && item.duration_seconds && (
          <Badge
            variant="secondary"
            className="absolute bottom-2 right-2 px-1.5 py-0.5 text-xs font-semibold shadow-xs"
          >
            {formatDuration(item.duration_seconds)}
          </Badge>
        )}
      </div>

      {/* Card Content */}
      <div className="flex flex-col gap-1 p-4">
        <span
          title={item.title}
          className="truncate text-sm font-semibold text-foreground"
        >
          {item.title}
        </span>
        <div className="flex items-center justify-between gap-2 text-xs font-normal text-muted-foreground">
          <span className="truncate" title={displayName}>
            {displayName}
          </span>
          <span className="shrink-0 whitespace-nowrap">{formattedTime}</span>
        </div>
      </div>
    </Card>
  );
};
