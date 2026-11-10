import React, { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArrowLeft, ImageOff, Play, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InlineError } from "@/components/InlineError";
import { useCameras } from "@/lib/queries";
import { formatDateTime, formatRelative, useSiteTimeZone, zoneAbbreviation } from "@/lib/time";
import { useEvent } from "./api";
import { AlertActions, ReviewBadge, SeverityBadge } from "./AlertActions";
import { formatEventTypeLabel, getEventTypeIcon } from "./EventCard";

/** Old VMS "alert details" page: big snapshot, facts, review actions, jump to live/playback. */
export const EventDetailPage: React.FC = () => {
  const { id } = useParams();
  const eventId = Number(id);
  const navigate = useNavigate();
  const zone = useSiteTimeZone();
  const { data: cameras = [] } = useCameras();
  const { data: event, isLoading, error, refetch } = useEvent(Number.isFinite(eventId) ? eventId : null);
  const [imgError, setImgError] = useState(false);

  if (isLoading) return <Skeleton className="aspect-video w-full max-w-4xl" />;
  if (error || !event)
    return (
      <div className="flex flex-col gap-4">
        <InlineError message="Couldn't load this alert. It may have been removed." actionLabel="Reload alert" onAction={() => void refetch()} />
        <Button variant="outline" className="self-start" asChild>
          <Link to="/events">
            <ArrowLeft className="size-4" />
            Back to alerts
          </Link>
        </Button>
      </div>
    );

  const camera = cameras.find((c) => c.serial === event.camera_serial);
  const playbackStart = new Date(new Date(event.start_time).getTime() - 10_000).toISOString();
  const playbackHref = `/playback?camera=${encodeURIComponent(event.camera_serial)}&t=${encodeURIComponent(playbackStart)}`;

  return (
    <div className="flex flex-col gap-4 lg:gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/events">
            <ArrowLeft className="size-4" />
            Back to alerts
          </Link>
        </Button>
        <h2 className="flex items-center gap-2 text-xl font-semibold">
          {getEventTypeIcon(event.event_type)}
          {formatEventTypeLabel(event.event_type)}
        </h2>
        <SeverityBadge severity={event.severity} />
        <ReviewBadge state={event.review_state} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:gap-6 xl:grid-cols-3">
        <Card className="overflow-hidden py-0 xl:col-span-2">
          <div className="dark flex aspect-video w-full items-center justify-center bg-video-bg">
            {event.snapshot_path && !imgError ? (
              <img
                src={`/api/v1/events/${event.id}/snapshot`}
                alt={`${formatEventTypeLabel(event.event_type)} at ${camera?.name ?? event.camera_serial}`}
                onError={() => setImgError(true)}
                className="h-full w-full object-contain"
              />
            ) : (
              <span className="flex flex-col items-center gap-2 text-sm text-video-fg">
                <ImageOff className="size-8" />
                No snapshot for this alert
              </span>
            )}
          </div>
        </Card>

        <Card className="py-0">
          <CardContent className="flex flex-col gap-4 p-4">
            <dl className="grid grid-cols-3 gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Time</dt>
              <dd className="col-span-2">
                {formatDateTime(event.start_time, zone)} {zoneAbbreviation(event.start_time, zone)}
                <span className="block text-xs text-muted-foreground">{formatRelative(event.start_time)}</span>
              </dd>
              <dt className="text-muted-foreground">Camera</dt>
              <dd className="col-span-2">{camera?.name ?? event.camera_serial}</dd>
              {camera?.location && (
                <>
                  <dt className="text-muted-foreground">Location</dt>
                  <dd className="col-span-2">{camera.location}</dd>
                </>
              )}
              <dt className="text-muted-foreground">Footage</dt>
              <dd className="col-span-2">{event.is_locked ? "Locked (kept past retention)" : "Normal retention"}</dd>
              {event.reviewed_at && (
                <>
                  <dt className="text-muted-foreground">Reviewed</dt>
                  <dd className="col-span-2">
                    {event.reviewed_by} · {formatDateTime(event.reviewed_at, zone)}
                  </dd>
                </>
              )}
            </dl>
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <Link to={playbackHref}>
                  <Play className="size-4" />
                  Play footage
                </Link>
              </Button>
              <Button variant="outline" asChild>
                <Link to="/live">
                  <Video className="size-4" />
                  Watch live
                </Link>
              </Button>
            </div>
            <AlertActions event={event} onRemoved={() => void navigate("/events")} className="border-t border-border pt-4" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default EventDetailPage;
