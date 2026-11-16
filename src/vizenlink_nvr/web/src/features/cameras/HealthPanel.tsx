import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
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

  const role = useCurrentUser()?.role;
  const client = useQueryClient();
  const check = useMutation({
    mutationFn: () => apiFetch<{ reprobed: boolean; status: string; kind: string | null; warnings: string[] }>(
      `/api/v1/cameras/${encodeURIComponent(serial)}/reprobe`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries(),
  });
  const action = (role === "owner" || role === "operator") && <div className="flex flex-wrap items-center gap-2">
    <Button variant="outline" size="sm" disabled={check.isPending} onClick={() => check.mutate()}>
      {check.isPending ? "Checking…" : "Re-check camera"}
    </Button>
    {check.data && <span role="status" className="text-sm">{check.data.reprobed
      ? [check.data.kind ?? check.data.status, ...check.data.warnings].join(" · ")
      : "Live camera check unavailable."}</span>}
    {check.error && <span role="alert" className="text-sm text-critical">{check.error.message}</span>}
  </div>;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (isError || !health) {
    return (
      <div className="flex flex-col gap-2">{action}<InlineError
        message={CAMERAS_COPY.HEALTH_LOAD_ERROR}
        actionLabel={CAMERAS_COPY.RETRY_LOAD_HEALTH}
        onAction={() => void refetch()}
      /></div>
    );
  }

  const isSynced = health.clock_sync_status?.toLowerCase() === "synced";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{CAMERAS_COPY.HEALTH_HEADING}</h2>
          <p className="mt-1 text-sm text-muted-foreground">Camera uptime, clock synchronization, firmware version, and live reachability.</p>
        </div>
        {action}
      </div>
      <Card className="rounded-xl border-border bg-card p-6 gap-4">
        <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          {/* Uptime */}
          <div className="flex flex-col gap-1 rounded-lg border border-border bg-background p-4">
            <span className="text-xs text-muted-foreground">{CAMERAS_COPY.UPTIME_LABEL}</span>
            <span className="font-semibold text-foreground font-mono">
              {formatUptime(health.uptime_seconds)}
            </span>
          </div>

          {/* Last reboot reason */}
          <div className="flex flex-col gap-1 rounded-lg border border-border bg-background p-4">
            <span className="text-xs text-muted-foreground">{CAMERAS_COPY.REBOOT_REASON_LABEL}</span>
            <span className="font-semibold text-foreground">
              {health.reboot_reason || "Not reported"}
            </span>
          </div>

          {/* Clock sync */}
          <div className="flex flex-col gap-1 rounded-lg border border-border bg-background p-4">
            <span className="text-xs text-muted-foreground">{CAMERAS_COPY.CLOCK_SYNC_LABEL}</span>
            <div>
              <StatusBadge
                kind={isSynced ? "online" : "degraded"}
                label={isSynced ? "Synced" : "Uncertain"}
              />
            </div>
          </div>

          {/* Firmware */}
          <div className="flex flex-col gap-1 rounded-lg border border-border bg-background p-4">
            <span className="text-xs text-muted-foreground">{CAMERAS_COPY.FIRMWARE_LABEL}</span>
            <span className="font-semibold text-foreground font-mono">
              {health.firmware_version || "Unknown"}
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}