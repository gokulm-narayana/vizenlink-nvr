import React, { useMemo, useState } from "react";
import { Link } from "react-router";
import {
  Settings2,
  Cctv,
  HardDrive,
  Cpu,
  MemoryStick,
  Server,
  CircleCheck,
  WifiOff,
  CircleOff,
  TriangleAlert,
  OctagonAlert,
  Bell,
  History,
  ArrowUpRight,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { InlineError } from "@/components/InlineError";
import {
  useAlerts,
  useCameras,
  useCurrentUser,
  useHealth,
  useRecordingStatus,
  useUnreadCount,
  type CameraInfo,
} from "@/lib/queries";
import { formatDateTime, formatRelative, useSiteTimeZone } from "@/lib/time";
import { evaluateRecorderStatus, isCameraOffline, recordingSerials as toRecordingSerials } from "@/lib/recorder-status";
import { useUiStore } from "@/stores/ui";
import { cn } from "cn";
import { useOutages, useStorageStatus, useSystemMetrics } from "./api";
import { bytesToGiB, storageSummary } from "./StorageCard";
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

/* ------------------------------------------------------------------------- */
/* Widget configuration (old VMS "Configure zone" parity), saved per browser */
/* ------------------------------------------------------------------------- */

export const WIDGET_LABELS = {
  zone1: { total: "Total cameras", online: "Online", offline: "Offline", recording: "Recording" },
  zone2: { storage: "Storage usage", cpu: "CPU load", memory: "Memory", server: "Server status" },
  zone3: { issues: "Camera issues list" },
  zone4: { alerts: "System alerts", events: "Latest camera alerts" },
} as const;

type ZoneId = keyof typeof WIDGET_LABELS;
type WidgetConfig = { [Z in ZoneId]: Record<keyof (typeof WIDGET_LABELS)[Z], boolean> };

const WIDGET_STORAGE_KEY = "vizenlink_dashboard_widgets_v1";

function defaultWidgets(): WidgetConfig {
  const out = {} as Record<string, Record<string, boolean>>;
  for (const [zone, widgets] of Object.entries(WIDGET_LABELS)) {
    out[zone] = Object.fromEntries(Object.keys(widgets).map((k) => [k, true]));
  }
  return out as WidgetConfig;
}

function loadWidgets(): WidgetConfig {
  const base = defaultWidgets();
  try {
    const saved = JSON.parse(localStorage.getItem(WIDGET_STORAGE_KEY) || "{}");
    for (const zone of Object.keys(base) as ZoneId[]) {
      for (const key of Object.keys(base[zone])) {
        const v = saved?.[zone]?.[key];
        if (typeof v === "boolean") (base[zone] as Record<string, boolean>)[key] = v;
      }
    }
  } catch {
    // Unreadable storage: show every widget.
  }
  return base;
}

/* ------------------------------------------------------------------------- */
/* Small building blocks                                                      */
/* ------------------------------------------------------------------------- */

const ZONE_TITLES: Record<ZoneId, string> = {
  zone1: "Camera Summary",
  zone2: "System & Storage",
  zone3: "Camera Issues",
  zone4: "Active Alerts",
};

function Zone({
  zone,
  icon: Icon,
  extra,
  onConfigure,
  children,
}: {
  zone: ZoneId;
  icon: React.ComponentType<{ className?: string }>;
  extra?: React.ReactNode;
  onConfigure: (zone: ZoneId) => void;
  children: React.ReactNode;
}) {
  const title = ZONE_TITLES[zone];
  return (
    <Card data-zone={zone} className="flex min-h-80 min-w-0 flex-col gap-0 py-0">
      <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-border px-4 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="size-4 shrink-0 text-primary-text" />
          <CardTitle className="truncate text-sm font-semibold">{title}</CardTitle>
        </div>
        <div className="flex items-center gap-1">
          {extra}
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Configure ${title}`}
            onClick={() => onConfigure(zone)}
          >
            <Settings2 className="size-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 p-4">{children}</CardContent>
    </Card>
  );
}

function StatTile({
  label,
  value,
  tone,
  to,
}: {
  label: string;
  value: React.ReactNode;
  tone: "primary" | "success" | "offline" | "neutral";
  to?: string;
}) {
  const body = (
    <>
      {/* Size kept outside cn(): tailwind-merge treats the custom "text-display" size as a colour and drops it. */}
      <span
        className={
          "text-display font-semibold tabular-nums " +
          (tone === "primary"
            ? "text-primary-text"
            : tone === "success"
              ? "text-success"
              : tone === "offline"
                ? "text-offline"
                : "text-foreground")
        }
      >
        {value}
      </span>
      <span className="text-sm text-muted-foreground">{label}</span>
    </>
  );
  const cls =
    "flex flex-col items-start justify-center gap-1 rounded-lg border border-border bg-background p-4 transition-colors";
  return to ? (
    <Link to={to} className={cn(cls, "hover:border-primary")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function Meter({
  icon: Icon,
  label,
  percent,
  caption,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  percent: number | null;
  caption?: string;
}) {
  const p = percent == null ? 0 : Math.max(0, Math.min(100, Math.round(percent)));
  const color =
    p > 90
      ? "[&_[data-slot=progress-indicator]]:bg-critical"
      : p >= 75
        ? "[&_[data-slot=progress-indicator]]:bg-warning"
        : "[&_[data-slot=progress-indicator]]:bg-primary";
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-background p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon className="size-4" />
          {label}
        </span>
        <span className="text-sm font-semibold tabular-nums">{percent == null ? "–" : `${p}%`}</span>
      </div>
      <Progress value={p} aria-label={`${label} ${p}%`} className={cn("h-2 w-full bg-muted", color)} />
      {caption && <span className="text-xs text-muted-foreground">{caption}</span>}
    </div>
  );
}

function ServiceRow({ name, ok }: { name: string; ok: boolean | undefined }) {
  const state = ok === undefined ? "Checking…" : ok ? "Running" : "Failed";
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-muted-foreground">{name}</span>
      <span className={cn("flex items-center gap-2 font-semibold", ok === false && "text-critical")}>
        <span
          className={cn(
            "size-2 rounded-full",
            ok === undefined ? "bg-muted-foreground" : ok ? "bg-success" : "bg-critical"
          )}
        />
        {state}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Camera issues                                                              */
/* ------------------------------------------------------------------------- */

export interface CameraIssue {
  camera: CameraInfo;
  kind: "offline" | "not_recording" | "error";
  text: string;
  since?: string | null;
}

export function deriveCameraIssues(
  cameras: CameraInfo[],
  recording: Set<string>,
  openOutages: Map<string, string>,
  storageBroken: boolean
): CameraIssue[] {
  const issues: CameraIssue[] = [];
  for (const cam of cameras) {
    const outageStart = openOutages.get(cam.serial);
    if (isCameraOffline(cam) || outageStart) {
      const text =
        cam.state === "auth_failed"
          ? "Camera rejected the saved password"
          : cam.state === "tls_changed"
            ? "Camera security certificate changed"
            : "Camera offline";
      issues.push({ camera: cam, kind: "offline", text, since: outageStart ?? cam.last_seen_at ?? null });
    } else if (storageBroken || !recording.has(cam.serial)) {
      issues.push({
        camera: cam,
        kind: "not_recording",
        text: storageBroken ? "Not recording: storage unavailable" : "Not recording",
      });
    } else if (cam.last_error) {
      issues.push({ camera: cam, kind: "error", text: String(cam.last_error) });
    }
  }
  return issues;
}

/* ------------------------------------------------------------------------- */
/* Page                                                                       */
/* ------------------------------------------------------------------------- */

export const DashboardPage: React.FC = () => {
  const siteZone = useSiteTimeZone();
  const user = useCurrentUser();
  const isManager = user?.role === "owner" || user?.role === "operator";
  const dismissedAlertIds = useUiStore((s) => s.dismissedAlertIds);

  const { data: health, error: healthError, isLoading: healthLoading, refetch: refetchHealth } = useHealth();
  const { data: storage, error: storageError, isLoading: storageLoading, refetch: refetchStorage } = useStorageStatus();
  const { data: allAlerts = [], refetch: refetchAlerts } = useAlerts();
  const { data: rawCameras, isLoading: camerasLoading, refetch: refetchCameras } = useCameras();
  const { data: rawRecList, refetch: refetchRecording } = useRecordingStatus();
  const cameras = Array.isArray(rawCameras) ? rawCameras : [];
  const recList = Array.isArray(rawRecList) ? rawRecList : [];
  const { data: outages = [] } = useOutages();
  const { data: metrics } = useSystemMetrics();
  const { data: recentEvents } = useUnreadCount();

  const [widgets, setWidgets] = useState<WidgetConfig>(loadWidgets);
  const [configZone, setConfigZone] = useState<ZoneId | null>(null);
  const [draft, setDraft] = useState<Record<string, boolean>>({});
  const [outageDialogOpen, setOutageDialogOpen] = useState(false);
  const [filterCamera, setFilterCamera] = useState<{ serial: string; name: string } | null>(null);

  const openOutageMap = useMemo(() => {
    const map = new Map<string, string>();
    // Defensive: never let a malformed response blank the whole Dashboard.
    for (const o of Array.isArray(outages) ? outages : []) {
      if (o.ended_at === null) map.set(o.camera_serial, o.started_at);
    }
    return map;
  }, [outages]);

  const recordingSet = useMemo(() => toRecordingSerials(recList), [recList]);
  const status = evaluateRecorderStatus({
    health,
    storageState: storage?.health_state,
    cameras,
    recList,
    openOutageSerials: new Set(openOutageMap.keys()),
  });

  const offlineCount = cameras.filter((c) => isCameraOffline(c, new Set(openOutageMap.keys()))).length;
  const issues = deriveCameraIssues(cameras, recordingSet, openOutageMap, status.storageBroken);
  const systemAlerts = (Array.isArray(allAlerts) ? allAlerts : []).filter((a) => !dismissedAlertIds.has(a.id));
  const latestEvents = (Array.isArray(recentEvents?.items) ? recentEvents.items : []).slice(0, 5);
  const cameraName = (serial?: string) => cameras.find((c) => c.serial === serial)?.name ?? serial ?? "Camera";

  const total = storage?.telemetry?.total_bytes ?? 0;
  const used = storage?.telemetry?.used_bytes ?? 0;
  const storagePercent = total > 0 ? (used / total) * 100 : null;

  const isLoading = healthLoading || storageLoading || camerasLoading;
  const hasError = healthError || storageError;

  const openConfig = (zone: ZoneId) => {
    setDraft({ ...(widgets[zone] as Record<string, boolean>) });
    setConfigZone(zone);
  };
  const saveConfig = () => {
    if (!configZone) return;
    const next = { ...widgets, [configZone]: draft } as WidgetConfig;
    setWidgets(next);
    try {
      localStorage.setItem(WIDGET_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Not persisted; still applies for this visit.
    }
    setConfigZone(null);
  };
  const refetchAll = () => {
    void refetchHealth();
    void refetchStorage();
    void refetchAlerts();
    void refetchCameras();
    void refetchRecording();
  };

  const w1 = widgets.zone1;
  const w2 = widgets.zone2;

  return (
    <div className="flex min-h-full flex-col gap-6">
      {/* Recorder status banner: the one thing that must never be wrong. */}
      <div
        role="status"
        data-level={status.level}
        className={cn(
          "flex flex-wrap items-center justify-between gap-4 rounded-lg border p-4",
          status.level === "critical" && "border-critical bg-critical-subtle",
          status.level === "warning" && "border-warning bg-warning-subtle",
          status.level === "ok" && "border-success bg-success-subtle"
        )}
      >
        <div className="flex min-w-0 items-center gap-4">
          {status.level === "critical" ? (
            <OctagonAlert className="size-6 shrink-0 text-critical" />
          ) : status.level === "warning" ? (
            <TriangleAlert className="size-6 shrink-0 text-warning" />
          ) : (
            <CircleCheck className="size-6 shrink-0 text-success" />
          )}
          <div className="min-w-0">
            <p
              className={cn(
                "text-xl font-semibold",
                status.level === "critical" && "text-critical",
                status.level === "warning" && "text-warning",
                status.level === "ok" && "text-success"
              )}
            >
              {status.label}
            </p>
            <p className="text-sm text-foreground">
              {status.storageBroken && storage ? storageSummary(storage) : status.detail}
            </p>
          </div>
        </div>
        {status.storageBroken && isManager && (
          <Button asChild>
            <Link to="/settings/recording">
              Review storage settings
              <ArrowUpRight className="size-4" />
            </Link>
          </Button>
        )}
      </div>

      {hasError && (
        <InlineError
          message={DASHBOARD_COPY.LOAD_ERROR_MESSAGE}
          actionLabel={DASHBOARD_COPY.LOAD_ERROR_ACTION}
          onAction={refetchAll}
        />
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-80 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Zone 1: Camera Summary */}
          <Zone zone="zone1" icon={Cctv} onConfigure={openConfig}>
            <div className="grid flex-1 grid-cols-2 gap-4">
              {w1.total && <StatTile label="Total cameras" value={cameras.length} tone="primary" to={isManager ? "/cameras" : undefined} />}
              {w1.online && <StatTile label="Online" value={cameras.length - offlineCount} tone="success" />}
              {w1.offline && <StatTile label="Offline" value={offlineCount} tone={offlineCount > 0 ? "offline" : "neutral"} />}
              {w1.recording && (
                <StatTile
                  label="Recording"
                  value={`${status.recordingCount} / ${cameras.length}`}
                  tone={status.storageBroken ? "offline" : "neutral"}
                />
              )}
            </div>
            {cameras.length === 0 && isManager && (
              <Button asChild variant="outline" className="self-start">
                <Link to="/cameras/add">{DASHBOARD_COPY.CAMERAS_ADD_BUTTON}</Link>
              </Button>
            )}
          </Zone>

          {/* Zone 2: System & Storage */}
          <Zone zone="zone2" icon={Server} onConfigure={openConfig}>
            {w2.storage && (
              <div className="flex flex-col gap-2 rounded-lg border border-border bg-background p-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-sm text-muted-foreground">
                    <HardDrive className="size-4" />
                    Storage usage
                  </span>
                  <span
                    className={cn("text-sm font-semibold", status.storageBroken ? "text-critical" : "text-success")}
                  >
                    {status.storageBroken ? "Unavailable" : "Ready to record"}
                  </span>
                </div>
                <Progress
                  value={storagePercent ?? 0}
                  aria-label={`Storage used ${Math.round(storagePercent ?? 0)}%`}
                  className={cn(
                    "h-2 w-full bg-muted",
                    (storagePercent ?? 0) > 90
                      ? "[&_[data-slot=progress-indicator]]:bg-critical"
                      : (storagePercent ?? 0) >= 80
                        ? "[&_[data-slot=progress-indicator]]:bg-warning"
                        : "[&_[data-slot=progress-indicator]]:bg-primary"
                  )}
                />
                <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
                  <span>
                    {storage?.telemetry
                      ? `${bytesToGiB(used)} used of ${bytesToGiB(total)} · ${bytesToGiB(storage.telemetry.free_bytes)} free`
                      : "Disk size unknown"}
                  </span>
                  <span>
                    {status.storageBroken
                      ? "0 days retention (not saving)"
                      : storage?.estimated_retention_days != null
                        ? `${storage.estimated_retention_days} days retention remaining`
                        : "Retention not estimated yet"}
                  </span>
                </div>
              </div>
            )}
            {(w2.cpu || w2.memory) && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {w2.cpu && (
                  <Meter
                    icon={Cpu}
                    label="CPU load"
                    percent={metrics?.cpu_percent ?? null}
                    caption={metrics ? `${metrics.cpu_count} cores` : undefined}
                  />
                )}
                {w2.memory && (
                  <Meter
                    icon={MemoryStick}
                    label="Memory"
                    percent={metrics?.memory_percent ?? null}
                    caption={
                      metrics
                        ? `${bytesToGiB(metrics.memory_used_bytes)} of ${bytesToGiB(metrics.memory_total_bytes)}`
                        : undefined
                    }
                  />
                )}
              </div>
            )}
            {w2.server && (
              <div className="flex flex-col gap-2 rounded-lg border border-border bg-background p-4">
                <ServiceRow name="Database" ok={health?.db_ok} />
                <ServiceRow name="Video service" ok={health?.mediamtx_ok} />
                <ServiceRow name="Recording storage" ok={health ? !status.storageBroken : undefined} />
                <div className="flex flex-wrap justify-between gap-2 border-t border-border pt-2 text-xs text-muted-foreground">
                  <span>Uptime: {metrics ? formatUptime(metrics.nvr_uptime_seconds) : "–"}</span>
                  <span>{metrics ? `v${metrics.version} · ${metrics.platform}` : ""}</span>
                </div>
              </div>
            )}
          </Zone>

          {/* Zone 3: Camera Issues */}
          <Zone
            zone="zone3"
            icon={TriangleAlert}
            onConfigure={openConfig}
            extra={
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setFilterCamera(null);
                  setOutageDialogOpen(true);
                }}
              >
                <History className="size-4" />
                {DASHBOARD_COPY.GLOBAL_OUTAGES}
              </Button>
            }
          >
            {widgets.zone3.issues &&
              (issues.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
                  <CircleCheck className="size-8 text-success" />
                  {cameras.length === 0 ? "No cameras added yet." : "No issues found. Every camera is online and recording."}
                </div>
              ) : (
                <ul className="flex flex-col gap-2" aria-label="Camera issues">
                  {issues.map((issue) => (
                    <li key={issue.camera.serial}>
                      <Link
                        to={`/cameras/${encodeURIComponent(issue.camera.serial)}/health`}
                        className="flex items-center gap-4 rounded-lg border border-border bg-background p-4 transition-colors hover:border-primary"
                      >
                        {issue.kind === "offline" ? (
                          <WifiOff className="size-5 shrink-0 text-offline" />
                        ) : issue.kind === "not_recording" ? (
                          <CircleOff className="size-5 shrink-0 text-critical" />
                        ) : (
                          <TriangleAlert className="size-5 shrink-0 text-warning" />
                        )}
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-semibold">{issue.camera.name}</span>
                          <span className="block truncate text-sm text-muted-foreground">
                            {issue.text}
                            {issue.since ? ` · since ${formatRelative(issue.since)}` : ""}
                            {issue.camera.location ? ` · ${issue.camera.location}` : ""}
                          </span>
                        </span>
                        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                      </Link>
                    </li>
                  ))}
                </ul>
              ))}
          </Zone>

          {/* Zone 4: Active Alerts */}
          <Zone
            zone="zone4"
            icon={Bell}
            onConfigure={openConfig}
            extra={
              <Button variant="ghost" size="sm" asChild>
                <Link to="/events">View all alerts</Link>
              </Button>
            }
          >
            {widgets.zone4.alerts && systemAlerts.length > 0 && (
              <ul className="flex flex-col gap-2" aria-label="System alerts">
                {systemAlerts.map((a) => (
                  <li
                    key={a.id}
                    className={cn(
                      "flex items-start gap-2 rounded-lg border p-4 text-sm",
                      a.severity === "critical" ? "border-critical bg-critical-subtle" : "border-warning bg-warning-subtle"
                    )}
                  >
                    {a.severity === "critical" ? (
                      <OctagonAlert className="mt-1 size-4 shrink-0 text-critical" />
                    ) : (
                      <TriangleAlert className="mt-1 size-4 shrink-0 text-warning" />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold">{a.title ?? a.message}</span>
                      {a.title && <span className="block text-muted-foreground">{a.message}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {widgets.zone4.events && latestEvents.length > 0 && (
              <ul className="flex flex-col gap-2" aria-label="Latest camera alerts">
                {latestEvents.map((evt) => (
                  <li key={evt.id}>
                    <Link
                      to={`/events?camera=${encodeURIComponent(String(evt.camera_serial ?? ""))}`}
                      className="flex items-center gap-4 rounded-lg border border-border bg-background p-4 text-sm transition-colors hover:border-primary"
                    >
                      <Bell className="size-4 shrink-0 text-info" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-semibold capitalize">
                          {String(evt.event_type ?? "event").replace(/_/g, " ")}
                        </span>
                        <span className="block truncate text-muted-foreground">
                          {cameraName(evt.camera_serial)}
                          {evt.start_time ? ` · ${formatDateTime(evt.start_time, siteZone)}` : ""}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {systemAlerts.length === 0 && latestEvents.length === 0 && (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
                <CircleCheck className="size-8 text-success" />
                No active alerts. All clear.
              </div>
            )}
          </Zone>
        </div>
      )}

      {/* Camera list (status per camera) */}
      {cameras.length > 0 && (
        <CamerasTable
          cameras={cameras}
          recordingSerials={recordingSet}
          openOutageMap={openOutageMap}
          onViewOutage={(serial, name) => {
            setFilterCamera({ serial, name });
            setOutageDialogOpen(true);
          }}
          zone={siteZone}
        />
      )}

      <OutageHistoryDialog
        isOpen={outageDialogOpen}
        onClose={() => setOutageDialogOpen(false)}
        filterCameraSerial={filterCamera?.serial ?? null}
        cameraName={filterCamera?.name ?? null}
        zone={siteZone}
      />

      <Dialog open={configZone !== null} onOpenChange={(open) => !open && setConfigZone(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Configure {configZone ? ZONE_TITLES[configZone] : ""}</DialogTitle>
            <DialogDescription>Choose which widgets this zone shows. Saved on this browser.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            {configZone &&
              Object.entries(WIDGET_LABELS[configZone]).map(([key, label]) => (
                <label key={key} className="flex items-center justify-between gap-4 text-sm">
                  {label}
                  <Switch
                    checked={draft[key] ?? true}
                    onCheckedChange={(v) => setDraft((d) => ({ ...d, [key]: Boolean(v) }))}
                    aria-label={`Show ${label}`}
                  />
                </label>
              ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfigZone(null)}>
              Discard changes
            </Button>
            <Button onClick={saveConfig}>Save widgets</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DashboardPage;
