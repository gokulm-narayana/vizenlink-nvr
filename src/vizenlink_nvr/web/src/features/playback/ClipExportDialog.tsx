import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { AlertCircle, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { formatTime } from "@/lib/time";
import { useExportClip } from "./api";
import { toDatetimeLocal, parseDatetimeLocal } from "./usePlaybackEngine";
import { PLAYBACK_COPY } from "./copy";

export interface ClipExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cameraSerial: string;
  cameraName?: string;
  inMarker: Date | null;
  outMarker: Date | null;
  zone: string;
  onExportSuccess?: () => void;
}

export function ClipExportDialog({
  open,
  onOpenChange,
  cameraSerial,
  cameraName,
  inMarker,
  outMarker,
  zone,
  onExportSuccess,
}: ClipExportDialogProps) {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [startTimeStr, setStartTimeStr] = useState("");
  const [endTimeStr, setEndTimeStr] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const { mutate: exportClip, isPending } = useExportClip();

  // Reset and prefill when opened
  useEffect(() => {
    if (open) {
      const s = inMarker || new Date(Date.now() - 60000);
      const e = outMarker || new Date();
      setStartTimeStr(toDatetimeLocal(s, zone));
      setEndTimeStr(toDatetimeLocal(e, zone));
      setTitle(`Clip ${cameraName || cameraSerial} ${formatTime(s, zone)}`);
      setFieldError(null);
      setApiError(null);
    }
  }, [open, inMarker, outMarker, zone, cameraSerial, cameraName]);

  const startDate = startTimeStr ? parseDatetimeLocal(startTimeStr, zone) : null;
  const endDate = endTimeStr ? parseDatetimeLocal(endTimeStr, zone) : null;

  const durationSec =
    startDate && endDate && endDate > startDate
      ? Math.round((endDate.getTime() - startDate.getTime()) / 1000)
      : 0;

  const durationCaption =
    durationSec < 60
      ? `${durationSec}s`
      : `${Math.floor(durationSec / 60)}m ${durationSec % 60}s`;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!startDate || !endDate || endDate <= startDate) {
      setFieldError("End time must be after start time");
      return;
    }

    setFieldError(null);
    setApiError(null);

    exportClip(
      {
        camera_serial: cameraSerial,
        start_time: startDate.toISOString(),
        end_time: endDate.toISOString(),
        title: title.trim() || undefined,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          onExportSuccess?.();
          toast.success(PLAYBACK_COPY.exportSuccessToast, {
            action: {
              label: PLAYBACK_COPY.openInGallery,
              onClick: () => {
                void navigate("/gallery?tab=clips");
              },
            },
          });
        },
        onError: () => {
          setApiError(PLAYBACK_COPY.exportError);
        },
      }
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!isPending) onOpenChange(next);
      }}
    >
      <DialogContent
        className="sm:max-w-[560px] p-6 gap-4"
        onPointerDownOutside={(e) => {
          if (isPending) e.preventDefault();
        }}
        onEscapeKeyDown={(e) => {
          if (isPending) e.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">
            {PLAYBACK_COPY.exportDialogTitle}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* Error Alert */}
          {apiError && (
            <Alert variant="destructive" role="alert">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs font-semibold">
                {apiError}
              </AlertDescription>
            </Alert>
          )}

          {/* Pending Progress */}
          {isPending && (
            <div className="flex flex-col gap-1">
              <Progress value={65} className="h-1.5 w-full" />
              <span className="text-xs text-muted-foreground">Exporting clip…</span>
            </div>
          )}

          {/* Title Field */}
          <div className="flex flex-col gap-1">
            <Label htmlFor="clip-title" className="text-xs font-semibold">
              Title
            </Label>
            <Input
              id="clip-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={isPending}
              className="text-xs"
              placeholder="Clip title (optional)"
            />
          </div>

          {/* Start Time Field */}
          <div className="flex flex-col gap-1">
            <Label htmlFor="clip-start" className="text-xs font-semibold">
              Start time
            </Label>
            <Input
              id="clip-start"
              type="text"
              value={startTimeStr}
              onChange={(e) => {
                setStartTimeStr(e.target.value);
                setFieldError(null);
              }}
              disabled={isPending}
              className="text-xs font-mono"
            />
          </div>

          {/* End Time Field */}
          <div className="flex flex-col gap-1">
            <Label htmlFor="clip-end" className="text-xs font-semibold">
              End time
            </Label>
            <Input
              id="clip-end"
              type="text"
              value={endTimeStr}
              onChange={(e) => {
                setEndTimeStr(e.target.value);
                setFieldError(null);
              }}
              disabled={isPending}
              className="text-xs font-mono"
            />
            {fieldError && (
              <span className="text-xs text-destructive font-semibold" role="alert">
                {fieldError}
              </span>
            )}
          </div>

          {/* Duration & Format Info */}
          <div className="flex items-center justify-between rounded-lg border border-border bg-muted/40 p-2 text-xs">
            <span className="text-muted-foreground">
              Duration:{" "}
              <span className="font-semibold text-foreground font-mono">
                {durationCaption}
              </span>
            </span>
            <span className="text-muted-foreground">
              {PLAYBACK_COPY.formatLabel}:{" "}
              <span className="font-semibold text-foreground">
                {PLAYBACK_COPY.formatMp4}
              </span>
            </span>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
              className="text-xs font-semibold"
            >
              {PLAYBACK_COPY.keepEditingClip}
            </Button>
            <Button
              type="submit"
              variant="default"
              disabled={isPending}
              className="text-xs font-semibold gap-1"
            >
              {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              <span>{apiError ? PLAYBACK_COPY.retryExportClip : PLAYBACK_COPY.exportClip}</span>
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
