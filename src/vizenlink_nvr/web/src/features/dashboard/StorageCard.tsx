import React, { useState, useRef } from "react";
import { Copy, HardDrive } from "lucide-react";
import { toast } from "sonner";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/StatusBadge";
import type { StorageStatusResponse } from "./api";
import { DASHBOARD_COPY } from "./copy";

export interface StorageCardProps {
  storage: StorageStatusResponse | null;
}

export function middleEllipsis(str: string, maxLen = 32): string {
  if (!str || str.length <= maxLen) return str;
  const half = Math.floor((maxLen - 3) / 2);
  return `${str.slice(0, half)}...${str.slice(-half)}`;
}

export function bytesToGiB(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "0.0 GiB";
  const gib = bytes / (1024 * 1024 * 1024);
  return `${gib.toFixed(1)} GiB`;
}

export const StorageCard: React.FC<StorageCardProps> = ({ storage }) => {
  const [showFallback, setShowFallback] = useState(false);
  const pathRef = useRef<HTMLSpanElement>(null);

  const handleCopy = async () => {
    if (!storage?.storage_path) return;
    if (navigator?.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(storage.storage_path);
        toast(DASHBOARD_COPY.STORAGE_PATH_COPIED_TOAST);
        setShowFallback(false);
        return;
      } catch {
        // fallback on insecure context
      }
    }
    // Fallback for plain HTTP LAN environments
    setShowFallback(true);
    if (pathRef.current && window.getSelection) {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(pathRef.current);
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
  };

  const path = storage?.storage_path || "/var/lib/vizenlink-nvr/recordings";
  const isHealthy = storage?.health_state === "ok" || storage?.health_state === "healthy";
  const freeBytes = storage?.telemetry?.free_bytes ?? 0;
  const reserveBytes = storage?.reserve_bytes ?? storage?.telemetry?.reserve_bytes ?? 0;
  const retentionDays = storage?.estimated_retention_days;

  return (
    <Card className="flex flex-col justify-between border-border bg-card">
      <CardHeader className="flex flex-row items-center justify-between border-b border-border p-4">
        <div className="flex items-center gap-2">
          <HardDrive className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm font-semibold text-foreground">
            {DASHBOARD_COPY.STORAGE_TITLE}
          </CardTitle>
        </div>

        {!isHealthy && storage?.health_state && (
          <StatusBadge kind="critical" label={storage.health_state} />
        )}
      </CardHeader>

      <CardContent className="flex flex-col gap-4 p-4 text-xs font-normal">
        {/* Storage Failure Notice if unhealthy */}
        {!isHealthy && storage?.health_reason && (
          <div className="rounded-md border border-critical/30 bg-critical-subtle p-2 text-foreground font-semibold">
            {storage.health_reason}
          </div>
        )}

        {/* Path with Middle Ellipsis & Copy Button */}
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground">Path</span>
          <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-muted/40 px-2 py-1">
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    ref={pathRef}
                    className="font-mono text-xs font-semibold text-foreground truncate cursor-help"
                  >
                    {middleEllipsis(path)}
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="font-mono text-xs">{path}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    aria-label={DASHBOARD_COPY.STORAGE_PATH_COPY_LABEL}
                    variant="ghost"
                    size="icon"
                    onClick={handleCopy}
                    className="h-6 w-6 text-muted-foreground hover:text-foreground"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    <span className="sr-only">{DASHBOARD_COPY.STORAGE_PATH_COPY_LABEL}</span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">{DASHBOARD_COPY.STORAGE_PATH_COPY_LABEL}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          {showFallback && (
            <span className="text-xs text-muted-foreground italic">
              {DASHBOARD_COPY.STORAGE_PATH_FALLBACK_CAPTION}
            </span>
          )}
        </div>

        {/* Telemetry Metrics */}
        <div className="grid grid-cols-3 gap-2 border-t border-border pt-4">
          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{DASHBOARD_COPY.STORAGE_FREE}</span>
            <span className="text-sm font-semibold tabular-nums text-foreground">
              {bytesToGiB(freeBytes)}
            </span>
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">
              {DASHBOARD_COPY.STORAGE_ESTIMATED_RETENTION}
            </span>
            <span className="text-sm font-semibold tabular-nums text-foreground">
              {retentionDays !== null && retentionDays !== undefined
                ? `${retentionDays} days`
                : "N/A"}
            </span>
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{DASHBOARD_COPY.STORAGE_RESERVE}</span>
            <span className="text-sm font-semibold tabular-nums text-foreground">
              {bytesToGiB(reserveBytes)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
