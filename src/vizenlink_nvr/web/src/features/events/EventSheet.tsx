import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { XIcon, Lock, Unlock, Info, TriangleAlert, Play } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetClose,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { InlineError } from "@/components/InlineError";
import { formatDateTime, zoneAbbreviation, useSiteTimeZone } from "@/lib/time";
import { useUiStore } from "@/stores/ui";
import type { EventItem } from "./api";
import { useLockEvent, useUnlockEvent } from "./api";
import { formatEventTypeLabel, getEventTypeIcon } from "./EventCard";
import { EVENTS_COPY } from "./copy";

export interface EventSheetProps {
  event: EventItem | null;
  cameraName?: string;
  isOpen: boolean;
  onClose: () => void;
  zone?: string;
}

export const EventSheet: React.FC<EventSheetProps> = ({
  event,
  cameraName,
  isOpen,
  onClose,
  zone: zoneProp,
}) => {
  const navigate = useNavigate();
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;
  const viewMode = useUiStore((s) => s.viewMode);

  const lockMutation = useLockEvent();
  const unlockMutation = useUnlockEvent();

  // Optimistic local locked state to allow revert on failure
  const [localLocked, setLocalLocked] = useState(false);
  const [mutationError, setMutationError] = useState<{
    message: string;
    actionLabel: "Retry lock event" | "Retry unlock event";
    action: () => void;
  } | null>(null);

  useEffect(() => {
    if (event) {
      setLocalLocked(event.is_locked);
      setMutationError(null);
    }
  }, [event]);

  if (!event) return null;

  const displayName = cameraName || event.camera_serial;
  const timeFormatted = `${formatDateTime(event.start_time, zone)} ${zoneAbbreviation(event.start_time, zone)}`;

  const handleToggleLock = async (nextChecked: boolean) => {
    setLocalLocked(nextChecked);
    setMutationError(null);

    if (nextChecked) {
      try {
        await lockMutation.mutateAsync(event.id);
      } catch {
        // Revert on failure
        setLocalLocked(false);
        setMutationError({
          message: EVENTS_COPY.LOCK_ERROR_MESSAGE,
          actionLabel: EVENTS_COPY.LOCK_ERROR_ACTION,
          action: () => handleToggleLock(true),
        });
      }
    } else {
      try {
        await unlockMutation.mutateAsync(event.id);
      } catch {
        // Revert on failure
        setLocalLocked(true);
        setMutationError({
          message: EVENTS_COPY.UNLOCK_ERROR_MESSAGE,
          actionLabel: EVENTS_COPY.UNLOCK_ERROR_ACTION,
          action: () => handleToggleLock(false),
        });
      }
    }
  };

  const handlePlayFootage = () => {
    onClose();
    void navigate(
      `/playback?camera=${encodeURIComponent(event.camera_serial)}&t=${encodeURIComponent(event.start_time)}`
    );
  };

  const isClockSynced = event.clock_sync_state === "synced";

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-full sm:max-w-[480px] flex flex-col p-0 overflow-y-auto"
      >
        {/* Custom Header with accessible close button */}
        <SheetHeader className="flex flex-row items-center justify-between border-b border-border p-4">
          <SheetTitle className="text-sm font-semibold">
            {EVENTS_COPY.DETAILS_TYPE}: {formatEventTypeLabel(event.event_type)}
          </SheetTitle>
          <SheetClose asChild>
            <Button
              aria-label={EVENTS_COPY.CLOSE_SHEET_LABEL}
              variant="ghost"
              size="icon"
              className="h-8 w-8"
            >
              <XIcon className="h-4 w-4" />
              <span className="sr-only">{EVENTS_COPY.CLOSE_SHEET_LABEL}</span>
            </Button>
          </SheetClose>
        </SheetHeader>

        {/* Mutation failure inline error at top of sheet */}
        {mutationError && (
          <div className="p-4 pb-0">
            <InlineError
              message={mutationError.message}
              actionLabel={mutationError.actionLabel}
              onAction={mutationError.action}
              pending={lockMutation.isPending || unlockMutation.isPending}
            />
          </div>
        )}

        {/* Snapshot Image */}
        <div className="relative aspect-video w-full bg-muted overflow-hidden border-b border-border flex items-center justify-center">
          {event.snapshot_path ? (
            <img
              src={`/api/v1/events/${event.id}/snapshot`}
              alt={`${formatEventTypeLabel(event.event_type)} at ${displayName}, ${timeFormatted}`}
              className="h-full w-full object-contain"
            />
          ) : (
            <span className="text-xs font-normal text-muted-foreground">
              {EVENTS_COPY.NO_SNAPSHOT}
            </span>
          )}

          <Badge
            variant="secondary"
            className="absolute top-2 left-2 flex items-center gap-1.5 px-2 py-0.5 text-xs font-semibold shadow-xs"
          >
            {getEventTypeIcon(event.event_type)}
            <span>{formatEventTypeLabel(event.event_type)}</span>
          </Badge>
        </div>

        {/* Sheet Body & Metadata */}
        <div className="flex flex-col gap-6 p-4 flex-1">
          {/* Metadata Section */}
          <div className="grid grid-cols-2 gap-4 rounded-md border border-border bg-card p-4 text-xs font-normal">
            <div className="flex flex-col gap-1">
              <span className="text-muted-foreground">{EVENTS_COPY.DETAILS_CAMERA}</span>
              <span className="font-semibold text-foreground truncate" title={displayName}>
                {displayName}
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-muted-foreground">{EVENTS_COPY.DETAILS_TIME}</span>
              <span className="font-semibold text-foreground">{timeFormatted}</span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-muted-foreground">{EVENTS_COPY.DETAILS_ID}</span>
              <span className="font-semibold text-foreground">{event.id}</span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-muted-foreground">Status</span>
              <span className="font-semibold text-foreground">
                {localLocked ? "Protected (Locked)" : "Standard retention"}
              </span>
            </div>
          </div>

          {/* Lock Switch */}
          <div className="flex items-center justify-between rounded-md border border-border bg-card p-4">
            <div className="flex items-center gap-2">
              {localLocked ? (
                <Lock className="h-4 w-4 text-foreground" />
              ) : (
                <Unlock className="h-4 w-4 text-muted-foreground" />
              )}
              <Label htmlFor="event-lock-switch" className="text-sm font-semibold cursor-pointer">
                {EVENTS_COPY.LOCK_LABEL}
              </Label>
            </div>
            <Switch
              id="event-lock-switch"
              checked={localLocked}
              disabled={lockMutation.isPending || unlockMutation.isPending}
              onCheckedChange={handleToggleLock}
            />
          </div>

          {/* Advanced Mode Details */}
          {viewMode === "advanced" && (
            <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-4 text-xs font-normal">
              <span className="font-semibold uppercase tracking-wider text-xs text-muted-foreground">
                Advanced Metadata
              </span>

              {/* Clock Sync Status */}
              <div className="flex items-center gap-2 mt-1">
                {isClockSynced ? (
                  <>
                    <Info className="h-4 w-4 text-info shrink-0" />
                    <span className="text-foreground">{EVENTS_COPY.CLOCK_SYNCED}</span>
                  </>
                ) : (
                  <>
                    <TriangleAlert className="h-4 w-4 text-warning shrink-0" />
                    <span className="text-warning font-semibold">
                      {EVENTS_COPY.CLOCK_UNCERTAIN}
                    </span>
                  </>
                )}
              </div>

              {/* Raw Topic */}
              <div className="flex flex-col gap-1 mt-2">
                <span className="text-muted-foreground">{EVENTS_COPY.DETAILS_RAW_TOPIC}</span>
                <code className="rounded bg-muted p-1 text-xs text-foreground break-all">
                  {event.raw_topic || "None"}
                </code>
              </div>

              {/* Key-Value Details */}
              {event.details && Object.keys(event.details).length > 0 && (
                <div className="flex flex-col gap-1 mt-2">
                  <span className="text-muted-foreground">Details</span>
                  <div className="flex flex-col gap-1 rounded bg-muted p-2 text-xs">
                    {Object.entries(event.details).map(([key, val]) => (
                      <div key={key} className="flex justify-between gap-2">
                        <span className="text-muted-foreground">{key}:</span>
                        <span className="font-mono text-foreground break-all">
                          {typeof val === "object" ? JSON.stringify(val) : String(val)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Primary Action Footer */}
        <div className="border-t border-border p-4 bg-card">
          <Button
            onClick={handlePlayFootage}
            className="w-full h-10 gap-2 font-semibold"
          >
            <Play className="h-4 w-4" />
            <span>{EVENTS_COPY.PLAY_FOOTAGE}</span>
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
};
