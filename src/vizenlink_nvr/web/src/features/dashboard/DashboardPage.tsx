import React, { useState, useMemo } from "react";
import { History, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { InlineError } from "@/components/InlineError";
import { StatusBadge } from "@/components/StatusBadge";
import {
  useHealth,
  useAlerts,
  useCameras,
  useRecordingStatus,
} from "@/lib/queries";
import { useSiteTimeZone } from "@/lib/time";
import { useUiStore } from "@/stores/ui";
import { cn } from "cn";
import { useStorageStatus, useOutages } from "./api";
import { MetricCard } from "./MetricCard";
import { StorageCard } from "./StorageCard";
import { AlertsCard } from "./AlertsCard";
import { CamerasTable } from "./CamerasTable";
import { OutageHistoryDialog } from "./OutageHistoryDialog";
import { DASHBOARD_COPY } from "./copy";

export function formatUptime(seconds?: number): string {
  if (!seconds || seconds <= 0) return "0s";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

export const DashboardPage: React.FC = () => {
  const siteZone = useSiteTimeZone();
  const viewMode = useUiStore((s) => s.viewMode);
  const dismissedAlertIds = useUiStore((s) => s.dismissedAlertIds);

  const {
    data: health,
    error: healthError,
    isLoading: healthLoading,
    refetch: refetchHealth,
  } = useHealth();

  const {
    data: storage,
    error: storageError,
    isLoading: storageLoading,
    refetch: refetchStorage,
  } = useStorageStatus();

  const {
    data: allAlerts = [],
    error: alertsError,
    refetch: refetchAlerts,
  } = useAlerts();

  const {
    data: rawCameras = [],
    isLoading: camerasLoading,
    refetch: refetchCameras,
  } = useCameras();

  const {
    data: recList = [],
    refetch: refetchRecording,
  } = useRecordingStatus();

  const {
    data: outages = [],
  } = useOutages();

  // Outage Dialog state
  const [outageDialogOpen, setOutageDialogOpen] = useState(false);
  const [filterCamera, setFilterCamera] = useState<{ serial: string; name: string } | null>(null);

  // Advanced raw details collapsible
  const [rawOpen, setRawOpen] = useState(false);

  // Active outages map: serial -> started_at for open outages
  const openOutageMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const o of outages) {
      if (o.ended_at === null) {
        map.set(o.camera_serial, o.started_at);
      }
    }
    return map;
  }, [outages]);

  // Recording cameras calculation
  const recordingSerials = useMemo(() => {
    const activeModes = new Set(["continuous", "scheduled", "event"]);
    const serials = new Set<string>();
    for (const r of recList) {
      if (activeModes.has(r.mode)) {
        serials.add(r.camera_serial);
      }
    }
    return serials;
  }, [recList]);

  // Overall recorder status
  const recorderStatus = useMemo(() => {
    if (health?.storage_ok === false || storage?.health_state === "critical") {
      return { label: "Critical", kind: "critical" as const };
    }
    if (
      health?.db_ok === false ||
      health?.mediamtx_ok === false ||
      (health?.status && health.status !== "healthy") ||
      storage?.health_state === "degraded"
    ) {
      return { label: "Degraded", kind: "degraded" as const };
    }
    return { label: "Healthy", kind: "online" as const };
  }, [health, storage]);

  // Online count
  const totalCameras = rawCameras.length;
  const onlineCount = useMemo(() => {
    return rawCameras.filter((c) => !openOutageMap.has(c.serial)).length;
  }, [rawCameras, openOutageMap]);

  // Storage calculation
  const totalBytes = storage?.telemetry?.total_bytes || 1;
  const usedBytes = storage?.telemetry?.used_bytes || 0;
  const usedPercent = Math.min(100, Math.round((usedBytes / totalBytes) * 100));

  const progressColor =
    usedPercent > 90
      ? "[&_[data-slot=progress-indicator]]:bg-critical"
      : usedPercent >= 80
        ? "[&_[data-slot=progress-indicator]]:bg-warning"
        : "[&_[data-slot=progress-indicator]]:bg-success";

  // Active alerts count
  const activeAlertsCount = allAlerts.filter((a) => !dismissedAlertIds.has(a.id)).length;

  const isLoading = healthLoading || storageLoading || camerasLoading;
  const hasError = healthError || storageError || alertsError;

  const handleOpenGlobalOutages = () => {
    setFilterCamera(null);
    setOutageDialogOpen(true);
  };

  const handleOpenCameraOutage = (serial: string, name: string) => {
    setFilterCamera({ serial, name });
    setOutageDialogOpen(true);
  };

  const handleRefetchAll = () => {
    void refetchHealth();
    void refetchStorage();
    void refetchAlerts();
    void refetchCameras();
    void refetchRecording();
  };

  return (
    <div className="flex flex-col gap-6 p-6 min-h-full">
      {/* Top Header Row with Outage History Button */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground tracking-tight">
            {DASHBOARD_COPY.SUBTITLE}
          </h2>
          <span className="text-xs font-normal text-muted-foreground">
            {viewMode === "advanced"
              ? "Advanced Diagnostic Mode"
              : "Operational telemetry"}
          </span>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={handleOpenGlobalOutages}
          className="gap-2 text-xs font-semibold"
        >
          <History className="h-4 w-4" />
          <span>{DASHBOARD_COPY.GLOBAL_OUTAGES}</span>
        </Button>
      </div>

      {/* Load Error */}
      {hasError && (
        <InlineError
          message={DASHBOARD_COPY.LOAD_ERROR_MESSAGE}
          actionLabel={DASHBOARD_COPY.LOAD_ERROR_ACTION}
          onAction={handleRefetchAll}
        />
      )}

      {/* Row 1: Metric Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i} className="p-4 bg-card border-border min-h-[110px] flex flex-col justify-between">
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-8 w-3/4" />
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {/* Recorder Status Anchor */}
          <MetricCard
            label={DASHBOARD_COPY.METRIC_RECORDER_STATUS}
            value={
              <div className="flex items-center gap-2">
                <StatusBadge kind={recorderStatus.kind} label={recorderStatus.label} />
                <span className="text-display font-semibold text-foreground">
                  {recorderStatus.label}
                </span>
              </div>
            }
          />

          {/* Cameras Online */}
          <MetricCard
            label={DASHBOARD_COPY.METRIC_CAMERAS_ONLINE}
            value={
              <span className="text-xl font-semibold tabular-nums text-foreground">
                {onlineCount} / {totalCameras}
              </span>
            }
          />

          {/* Recording Now */}
          <MetricCard
            label={DASHBOARD_COPY.METRIC_RECORDING_NOW}
            value={
              <span className="text-xl font-semibold tabular-nums text-foreground">
                {recordingSerials.size}
              </span>
            }
          />

          {/* Storage Used */}
          <MetricCard
            label={DASHBOARD_COPY.METRIC_STORAGE_USED}
            value={
              <span className="text-xl font-semibold tabular-nums text-foreground">
                {usedPercent}%
              </span>
            }
            footer={
              <Progress
                value={usedPercent}
                className={cn("h-1.5 w-full bg-muted", progressColor)}
              />
            }
          />

          {/* Active Alerts */}
          <MetricCard
            label={DASHBOARD_COPY.METRIC_ACTIVE_ALERTS}
            value={
              <span
                className={cn(
                  "text-xl font-semibold tabular-nums",
                  activeAlertsCount > 0 ? "text-critical" : "text-foreground"
                )}
              >
                {activeAlertsCount}
              </span>
            }
          />
        </div>
      )}

      {/* Row 2: Storage Card & Alerts Card */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <StorageCard storage={storage ?? null} />
        <AlertsCard />
      </div>

      {/* Row 3: Cameras Table */}
      <CamerasTable
        cameras={rawCameras}
        recordingSerials={recordingSerials}
        openOutageMap={openOutageMap}
        onViewOutage={handleOpenCameraOutage}
        zone={siteZone}
      />

      {/* Advanced Diagnostics Section */}
      {viewMode === "advanced" && health && (
        <Card className="flex flex-col gap-4 border-border bg-card p-4">
          <CardHeader className="p-0 pb-2 border-b border-border">
            <CardTitle className="text-sm font-semibold text-foreground">
              {DASHBOARD_COPY.ADVANCED_SUBSYSTEMS}
            </CardTitle>
          </CardHeader>

          {/* Subsystem Health Rows */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 p-2">
              <span className="text-xs font-semibold text-foreground">MediaMTX</span>
              <StatusBadge
                kind={health.mediamtx_ok ? "online" : "critical"}
                label={health.mediamtx_ok ? "Operational" : "Failed"}
              />
            </div>

            <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 p-2">
              <span className="text-xs font-semibold text-foreground">Database</span>
              <StatusBadge
                kind={health.db_ok ? "online" : "critical"}
                label={health.db_ok ? "Operational" : "Failed"}
              />
            </div>

            <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 p-2">
              <span className="text-xs font-semibold text-foreground">Storage</span>
              <StatusBadge
                kind={health.storage_ok ? "online" : "critical"}
                label={health.storage_ok ? "Operational" : "Failed"}
              />
            </div>
          </div>

          {/* Uptime */}
          {health.details?.uptime_seconds && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">{DASHBOARD_COPY.ADVANCED_UPTIME}:</span>
              <span className="font-semibold text-foreground font-mono">
                {formatUptime(Number(health.details.uptime_seconds))}
              </span>
            </div>
          )}

          {/* Collapsible for Raw Health Details */}
          {health.details && Object.keys(health.details).length > 0 && (
            <Collapsible open={rawOpen} onOpenChange={setRawOpen} className="flex flex-col gap-2 pt-2 border-t border-border">
              <CollapsibleTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 justify-between px-2 text-xs font-semibold text-muted-foreground hover:text-foreground"
                >
                  <span>{DASHBOARD_COPY.ADVANCED_RAW_DETAILS}</span>
                  <ChevronDown
                    className={cn("h-4 w-4 transition-transform duration-200", rawOpen && "rotate-180")}
                  />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="rounded-md bg-muted/40 p-4 font-mono text-xs text-foreground overflow-x-auto max-h-[200px]">
                  {Object.entries(health.details).map(([key, val]) => (
                    <div key={key} className="flex justify-between gap-4 py-0.5 border-b border-border/40 last:border-0">
                      <span className="text-muted-foreground">{key}:</span>
                      <span className="text-foreground break-all">
                        {typeof val === "object" ? JSON.stringify(val) : String(val)}
                      </span>
                    </div>
                  ))}
                </div>
              </CollapsibleContent>
            </Collapsible>
          )}
        </Card>
      )}

      {/* Outage History Dialog */}
      <OutageHistoryDialog
        isOpen={outageDialogOpen}
        onClose={() => setOutageDialogOpen(false)}
        filterCameraSerial={filterCamera?.serial ?? null}
        cameraName={filterCamera?.name ?? null}
        zone={siteZone}
      />
    </div>
  );
};

export default DashboardPage;
