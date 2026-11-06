import React, { useMemo } from "react";
import { TriangleAlert, OctagonAlert } from "lucide-react";
import { useSidebar } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCameras, useRecordingStatus, useHealth } from "@/lib/queries";
import { cn } from "cn";

export type RecorderSeverity = "success" | "warning" | "critical";

export const RecorderStatusChip: React.FC<{ className?: string }> = ({ className }) => {
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

  const { data: cameras = [] } = useCameras();
  const { data: recList = [] } = useRecordingStatus();
  const { data: health } = useHealth();

  const { n, total, severity } = useMemo(() => {
    const totalCams = cameras.length;
    const activeModes = new Set(["continuous", "scheduled", "event"]);
    const activeSerials = new Set<string>();

    for (const item of recList) {
      if (activeModes.has(item.mode)) {
        activeSerials.add(item.camera_serial);
      }
    }

    const recordingCount = activeSerials.size;

    let sev: RecorderSeverity = "success";

    if (health?.storage_ok === false) {
      sev = "critical";
    } else if (
      recordingCount < totalCams ||
      health?.db_ok === false ||
      health?.mediamtx_ok === false ||
      (health?.status && health.status !== "healthy")
    ) {
      sev = "warning";
    } else {
      sev = "success";
    }

    return {
      n: recordingCount,
      total: totalCams,
      severity: sev,
    };
  }, [cameras, recList, health]);

  const label = `Recording ${n} of ${total}`;

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
      <span className="tabular-nums font-normal">{label}</span>
    </div>
  );
};

export default RecorderStatusChip;
