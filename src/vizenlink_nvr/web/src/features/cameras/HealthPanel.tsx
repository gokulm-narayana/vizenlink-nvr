import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InlineError } from "@/components/InlineError";
import { StatusBadge } from "@/components/StatusBadge";
import { useCameraHealth } from "./api";
import { CAMERAS_COPY } from "./copy";
import { formatUptime } from "./capabilities";

export interface HealthPanelProps {
  serial: string;
}

export function HealthPanel({ serial }: HealthPanelProps) {
  const { data: health, isLoading, isError, refetch } = useCameraHealth(serial);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (isError || !health) {
    return (
      <InlineError
        message={CAMERAS_COPY.HEALTH_LOAD_ERROR}
        actionLabel={CAMERAS_COPY.RETRY_LOAD_HEALTH}
        onAction={() => void refetch()}
      />
    );
  }

  const isSynced = health.clock_sync_status?.toLowerCase() === "synced";

  return (
    <Card className="p-4 gap-4">
      <CardHeader className="p-0">
        <CardTitle className="text-sm font-semibold">
          {CAMERAS_COPY.HEALTH_HEADING}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
        {/* Uptime */}
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground">{CAMERAS_COPY.UPTIME_LABEL}</span>
          <span className="font-semibold text-foreground font-mono">
            {formatUptime(health.uptime_seconds)}
          </span>
        </div>

        {/* Last reboot reason */}
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground">{CAMERAS_COPY.REBOOT_REASON_LABEL}</span>
          <span className="font-semibold text-foreground">
            {health.reboot_reason || "Normal boot"}
          </span>
        </div>

        {/* Clock sync */}
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground">{CAMERAS_COPY.CLOCK_SYNC_LABEL}</span>
          <div>
            <StatusBadge
              kind={isSynced ? "online" : "degraded"}
              label={isSynced ? "Synced" : "Uncertain"}
            />
          </div>
        </div>

        {/* Firmware */}
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground">{CAMERAS_COPY.FIRMWARE_LABEL}</span>
          <span className="font-semibold text-foreground font-mono">
            {health.firmware_version || "Unknown"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}