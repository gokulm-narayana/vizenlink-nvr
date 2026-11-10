import React, { useMemo } from "react";
import { TriangleAlert, OctagonAlert } from "lucide-react";
import { useSidebar } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCameras, useRecordingStatus, useHealth } from "@/lib/queries";
import { evaluateRecorderStatus } from "@/lib/recorder-status";
import { useStorageStatus } from "@/features/dashboard/api";
import { cn } from "cn";

export type RecorderSeverity = "success" | "warning" | "critical";

export const RecorderStatusChip: React.FC<{ className?: string }> = ({ className }) => {
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

  const { data: rawCameras } = useCameras();
  const { data: rawRecList } = useRecordingStatus();
  const cameras = Array.isArray(rawCameras) ? rawCameras : [];
  const recList = Array.isArray(rawRecList) ? rawRecList : [];
  const { data: health } = useHealth();
  const { data: storage } = useStorageStatus();

  const status = useMemo(
    () =>
      evaluateRecorderStatus({
        health,
        storageState: storage?.health_state,
        cameras,
        recList,
      }),
    [health, storage?.health_state, cameras, recList]
  );
  const severity: RecorderSeverity =
    status.level === "critical" ? "critical" : status.level === "warning" ? "warning" : "success";
  const n = status.recordingCount;
  const total = status.cameraCount;

  // Never show a calm "Recording 0 of 0" when nothing can be saved.
  const label = status.label === "Not recording" ? `Not recording: ${status.detail}` : `Recording ${n} of ${total}`;
  const shortLabel = status.label === "Not recording" ? "Not recording" : label;

  const dot = (
    <span
      data-slot="recorder-dot"
      className={cn(
        "h-2 w-2 rounded-full shrink-0",
        severity === "success" && "bg-success",
        severity === "warning" && "bg-warning",
        severity === "critical" && "bg-critical animate-pulse"
      )}
    />
  );

  const icon =
    severity === "critical" ? (
      <OctagonAlert className="h-3.5 w-3.5 text-critical shrink-0" />
    ) : severity === "warning" ? (
      <TriangleAlert className="h-3.5 w-3.5 text-warning shrink-0" />
    ) : null;

  if (isCollapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            data-slot="recorder-status-chip"
            aria-label={label}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-md hover:bg-sidebar-accent cursor-default",
              className
            )}
          >
            {dot}
          </div>
        </TooltipTrigger>
        <TooltipContent side="right" className="text-xs font-semibold tabular-nums">
          {label}
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <div
      data-slot="recorder-status-chip"
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs font-normal text-sidebar-foreground/80 hover:bg-sidebar-accent transition-colors",
        className
      )}
    >
      {dot}
      {icon}
      <span
        className={cn(
          "tabular-nums",
          severity === "critical" ? "font-semibold text-critical" : "font-normal"
        )}
        title={label}
      >
        {shortLabel}
      </span>
    </div>
  );
};

export default RecorderStatusChip;